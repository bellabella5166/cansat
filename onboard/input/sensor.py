import os
import csv
import numpy as np
import time
import math
import threading
from onboard.input.timestamp_manager import get_timestamp, format_timestamp
from onboard.system.config import (
    MOCK_MODE,
    SENSOR_SAVE_DIR,
    GPS_PORT,
    GPS_BAUDRATE,
    BARO_SENTINEL,
)

# Pi4 환경에서만 import
try:
    import adafruit_bno055
    BNO055_AVAILABLE = True
except ImportError:
    BNO055_AVAILABLE =False

try:
    import adafruit_bmp3xx
    BMP388_AVAILABLE = True
except ImportError:
    BMP388_AVAILABLE = False

try:
    import serial
    import pynmea2
    GPS_AVAILABLE = True
except ImportError:
    GPS_AVAILABLE = False


class Sensor:
    """
    GPS, IMU, Barometer 센서 데이터를 수집하고 SD카드에 원시 저장한다.
    Pi4 환경에서는 실제 센서, 로컬 환경에서는 Mock 데이터를 사용한다.
    """

    def __init__(self, save_dir: str = SENSOR_SAVE_DIR, mock: bool = MOCK_MODE,
                 i2c_lock: threading.Lock = None):
        """
        Args:
            save_dir (str): 센서 데이터 저장 경로
            mock (bool): True면 Mock 모드 (로컬 테스트용)
            i2c_lock (threading.Lock): IMU/Baro가 공유하는 물리 I2C 버스용 락.
                calibrate_ground_altitude()가 별도 스레드에서 90초 뒤 self.baro를
                50회 연속 읽는 동안, sensor_thread도 동시에 같은 I2C 버스를
                10Hz로 읽고 있어 락 없이는 버스 락업을 유발할 수 있다.
        """
        self.save_dir = save_dir
        self.mock = mock or not (BNO055_AVAILABLE and BMP388_AVAILABLE and GPS_AVAILABLE)
        self._i2c_lock = i2c_lock or threading.Lock()
        # GPS는 I2C가 아니라 시리얼 포트라 _i2c_lock과는 별개 락이 필요하다 —
        # calibrate_ground_altitude()가 GPS 기준고도 샘플링을 위해 별도 스레드에서
        # self.gps를 읽는 동안, sensor_thread도 동시에 같은 시리얼 포트를 읽을 수 있다.
        self._gps_lock = threading.Lock()
        self.imu = None
        self.baro = None
        self.gps = None
        self._last_gps = {
            'lat': 0.0,
            'lon': 0.0,
            'gps_altitude': 0.0,
            'satellites': 0,
            'fix_quality': 0,
            'hdop': 99.9,
        }
        self.ground_altitude = 0.0
        self.ground_altitude_ready = False  # 안정화 완료 여부
        self.ground_gps_altitude = 0.0
        self.ground_gps_altitude_ready = False  # GPS 지상 기준고도 보정 완료 여부

        os.makedirs(self.save_dir, exist_ok=True)

        # raw CSV 파일 초기화
        self.raw_csv_path = os.path.join(self.save_dir, "raw_sensor_log.csv")
        self._init_csv()

        self._mock_start_time = time.monotonic()
        if not self.mock:
            self._init_sensors()

    def _init_csv(self):
        """raw CSV 파일 헤더 작성"""
        if not os.path.exists(self.raw_csv_path):
            with open(self.raw_csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'sensor_id', 'timestamp',
                    'lat', 'lon', 'gps_altitude',
                    'roll', 'pitch', 'yaw',
                    'pressure', 'temp', 'baro_altitude',
                    'accel_x', 'accel_y', 'accel_z',
                    'gyro_x', 'gyro_y', 'gyro_z',
                    'calib_sys', 'calib_gyro', 'calib_accel', 'calib_mag',
                    'satellites', 'fix_quality', 'hdop',
                ])

    def _init_sensors(self):
        """실제 센서 초기화 (Pi4 전용).

        부품 하나(예: GPS 커넥터 헐거움, BNO055 순간 미응답)가 초기화에
        실패해도 나머지 부품은 계속 시도한다 — 여기서 예외가 그냥 새어
        나가면 Sensor() 생성자 자체가 죽고, main()이 스레드를 하나도
        못 띄운 채로 프로그램 전체가 시작도 못 하고 종료된다.
        실패한 부품은 self.imu/self.baro/self.gps가 None으로 남고,
        _read_imu()/_read_baro()/_read_gps()가 각자 안전한 기본값으로
        대응한다.
        """
        import adafruit_bmp3xx
        import board

        try:
            i2c = board.I2C()
        except Exception as e:
            print(f"[Sensor] I2C bus init failed, IMU/Baro unavailable: {e}")
            i2c = None

        if i2c is not None:
            try:
                self.imu = adafruit_bno055.BNO055_I2C(i2c)
                # 기본값(NDOF_MODE)은 지자기계까지 퓨전에 써서 절대방위(yaw)를
                # 잡아주지만, 짐벌 서보 모터가 IMU 바로 옆에 붙어있어 서보가
                # 움직일 때마다 지자기계가 전류/자석 간섭을 받아 roll/pitch까지
                # 같이 흔들리는 원인이 됐다 — 서보 진동 실측 비교로 확인됨.
                # IMUPLUS_MODE는 가속도+자이로만 써서 이 간섭 경로를 없앤다.
                # yaw는 텔레메트리 로깅에만 쓰이고 온보드 판단(짐벌 포함)에는
                # 전혀 안 쓰이므로, 자이로 적분만으로 드리프트되는 대가는 감수 가능.
                self.imu.mode = adafruit_bno055.IMUPLUS_MODE
            except Exception as e:
                print(f"[Sensor] BNO055 init failed, IMU will report defaults: {e}")
                self.imu = None

            try:
                self.baro = adafruit_bmp3xx.BMP3XX_I2C(i2c)
                self.baro.pressure_oversampling = 8
                self.baro.temperature_oversampling = 2
            except Exception as e:
                print(f"[Sensor] BMP388 init failed, baro will report defaults: {e}")
                self.baro = None

        # GPS 초기화
        try:
            self.gps = serial.Serial(GPS_PORT, baudrate=GPS_BAUDRATE, timeout=1)
        except Exception as e:
            print(f"[Sensor] GPS init failed, GPS will report defaults: {e}")
            self.gps = None

    def _read_imu(self) -> dict:
        if self.imu is None:
            # 초기화 실패로 IMU가 없으면, 예외를 던져서 read() 전체를 실패시키는
            # 대신 안전한 기본값을 반환 — GPS/Baro가 살아있으면 그쪽 데이터라도
            # 계속 전송되게 한다 (한 부품 고장이 전체 SENSOR 송신을 막으면 안 됨).
            return {
                'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0,
                'accel_x': 0.0, 'accel_y': 0.0, 'accel_z': 0.0,
                'gyro_x': 0.0, 'gyro_y': 0.0, 'gyro_z': 0.0,
                'calib_sys': 0, 'calib_gyro': 0, 'calib_accel': 0, 'calib_mag': 0,
            }
        with self._i2c_lock:
            heading, roll, pitch = self.imu.euler
            ax, ay, az = self.imu.linear_acceleration
            gx, gy, gz = self.imu.gyro  # BNO055는 rad/s로 반환 → deg/s로 변환
            calib_sys, calib_gyro, calib_accel, calib_mag = self.imu.calibration_status
        gx, gy, gz = math.degrees(gx), math.degrees(gy), math.degrees(gz)

        return {
            'roll':        roll,
            'pitch':       pitch,
            'yaw':         heading,
            'accel_x':     ax,
            'accel_y':     ay,
            'accel_z':     az,
            'gyro_x':      gx,
            'gyro_y':      gy,
            'gyro_z':      gz,
            'calib_sys':   calib_sys,
            'calib_gyro':  calib_gyro,
            'calib_accel': calib_accel,
            'calib_mag':   calib_mag,
        }

    def _read_baro(self) -> dict:
        if self.baro is None:
            # 초기화 실패로 Baro가 없으면 안전한 기본값 반환 (IMU/GPS는 계속 살림)
            return {'pressure': 0.0, 'temp': 0.0, 'baro_altitude': BARO_SENTINEL}
        with self._i2c_lock:
            if not self.ground_altitude_ready:
                return {
                    'pressure': self.baro.pressure,
                    'temp': self.baro.temperature,
                    'baro_altitude': BARO_SENTINEL,
                }
            return {
                'pressure': self.baro.pressure,
                'temp': self.baro.temperature,
                'baro_altitude': self.baro.altitude - self.ground_altitude,
            }

    def calibrate_ground_altitude(self, wait_sec: int = 90) -> None:
        """별도 스레드에서 호출. 안정화 대기 후 ground_altitude(baro)와
        ground_gps_altitude(GPS)를 함께 설정한다 — baro가 발사 지점을 0m로
        잡는 것과 동일한 기준으로 GPS 고도(원래 해발고도)도 상대고도화해서,
        AltitudeArbiter가 baro↔GPS를 전환해도 같은 기준선을 쓰게 한다.

        - 샘플 중 일부가 I2C 읽기 실패로 예외를 던져도 전체 보정이 죽지
          않도록, 실패한 샘플은 건너뛰고 성공한 것만으로 평균을 낸다.
          (예전엔 1개만 실패해도 통째로 죽어서 ground_altitude_ready가
          영원히 False로 남는 버그가 있었음)
        - lock을 샘플 전체 구간 동안 붙잡지 않고, 샘플 하나 읽을 때만
          짧게 쥐었다 놓는다 — sensor_thread의 10Hz 읽기와 자연스럽게
          번갈아 실행되어 이 함수가 도는 동안에도 SENSOR 데이터 전송에
          공백이 생기지 않는다. (평균은 샘플이 연속이든 띄엄띄엄이든
          통계적으로 동일하므로 정확도 손해 없음)
        - GPS는 이 시점까지 fix가 아예 안 잡혀있을 수 있다 — baro와 달리
          실패해도 baro 보정 자체를 막지 않고, GPS만 계속 미보정(사용 안 함)
          상태로 남는다 (fix 없이 fallback으로 쓰면 더 위험하므로).
        """
        import numpy as np
        SAMPLE_COUNT = 20
        MIN_VALID = 8
        print(f"[Sensor] Waiting for barometer/GPS stabilization ({wait_sec}s)...")
        time.sleep(wait_sec)
        baro_samples = []
        gps_samples = []
        for _ in range(SAMPLE_COUNT):
            try:
                with self._i2c_lock:
                    baro_samples.append(self.baro.altitude)
            except Exception as e:
                print(f"[Sensor] baro calibration sample read failed, skipping: {e}")

            gps_raw = self._read_gps_raw()
            if gps_raw.get('fix_quality', 0) > 0:
                gps_samples.append(gps_raw['gps_altitude'])

        if len(baro_samples) < MIN_VALID:
            print(f"[Sensor] Ground baro altitude calibration failed: only {len(baro_samples)}/{SAMPLE_COUNT} samples succeeded")
        else:
            self.ground_altitude = sum(baro_samples) / len(baro_samples)
            std = np.std(baro_samples)
            self.ground_altitude_ready = True
            print(f"[Sensor] Ground baro altitude set: {self.ground_altitude:.2f} m (std={std:.3f}m, {len(baro_samples)}/{SAMPLE_COUNT} samples)")

        if len(gps_samples) < MIN_VALID:
            print(f"[Sensor] Ground GPS altitude calibration failed: only {len(gps_samples)}/{SAMPLE_COUNT} valid fixes — GPS altitude fallback disabled this flight")
        else:
            self.ground_gps_altitude = sum(gps_samples) / len(gps_samples)
            gps_std = np.std(gps_samples)
            self.ground_gps_altitude_ready = True
            print(f"[Sensor] Ground GPS altitude set: {self.ground_gps_altitude:.2f} m (std={gps_std:.3f}m, {len(gps_samples)}/{SAMPLE_COUNT} fixes)")

    def _read_gps_raw(self) -> dict:
        """GPS NMEA를 파싱해 lat/lon/altitude(해발, 보정 전 원시값)를 갱신하고 반환한다.
        calibrate_ground_altitude()의 기준점 산출과 _read_gps()의 상대고도 변환이
        공통으로 쓰는 원시 읽기 — 여기서는 지상 기준고도 보정 여부를 따지지 않는다."""
        try:
            with self._gps_lock:
                line = self.gps.readline().decode('ascii', errors='replace')
            if line.startswith('$GPGGA') or line.startswith('$GNGGA'):
                msg = pynmea2.parse(line)
                self._last_gps = {
                    'lat': float(msg.latitude),
                    'lon': float(msg.longitude),
                    'gps_altitude': float(msg.altitude) if msg.altitude else self._last_gps['gps_altitude'],
                    'satellites': int(msg.num_sats),
                    'fix_quality': int(msg.gps_qual),
                    'hdop': float(msg.horizontal_dil) if msg.horizontal_dil else 99.9,
                }
        except Exception:
            pass
        return self._last_gps

    def _read_gps(self) -> dict:
        """GPS에서 lat, lon, altitude 읽기.

        baro(발사 지점=0m 기준)와 동일한 기준을 맞추기 위해, gps_altitude는
        calibrate_ground_altitude()에서 잡은 ground_gps_altitude를 뺀 상대고도로
        반환한다. 보정 전(ground_gps_altitude_ready=False)에는 baro의
        BARO_SENTINEL과 같은 취지로 fix_quality를 0으로 강제해, AltitudeArbiter/
        AltitudeAnchor가 기준 없는 해발고도를 baro와 혼용해 쓰지 않게 한다.
        """
        data = dict(self._read_gps_raw())
        if not self.ground_gps_altitude_ready:
            data['fix_quality'] = 0
        else:
            data['gps_altitude'] = data['gps_altitude'] - self.ground_gps_altitude
        return data

    def _mock_data(self) -> dict:
        """Mock 센서 데이터 생성 (로컬 테스트용)"""
        elapsed  = time.monotonic() - self._mock_start_time
        baro_alt = max(0.0, 350.0 - elapsed * 5.0)
        return {
            'lat': 37.5 + np.random.uniform(-0.001, 0.001),
            'lon': 127.0 + np.random.uniform(-0.001, 0.001),
            'gps_altitude': baro_alt + np.random.uniform(-2.0, 2.0),
            'roll': np.random.uniform(-5.0, 5.0),
            'pitch': np.random.uniform(-5.0, 5.0),
            'yaw': np.random.uniform(0.0, 360.0),
            'pressure': 1013.25 + np.random.uniform(-1.0, 1.0),
            'temp': 25.0 + np.random.uniform(-1.0, 1.0),
            'baro_altitude': baro_alt + np.random.uniform(-1.0, 1.0),
            'accel_x': np.random.uniform(-1.0, 1.0),
            'accel_y': np.random.uniform(-1.0, 1.0),
            'accel_z': np.random.uniform(9.7, 9.9),
            'gyro_x': np.random.uniform(-1.0, 1.0),
            'gyro_y': np.random.uniform(-1.0, 1.0),
            'gyro_z': np.random.uniform(-1.0, 1.0),
            'calib_sys': 3,
            'calib_gyro': 3,
            'calib_accel': 3,
            'calib_mag': 3,
            'satellites': int(np.random.randint(4, 12)),
            'fix_quality': 1,
            'hdop': float(np.random.uniform(0.8, 2.0)),
        }

    def read(self, sensor_id: str) -> tuple:
        """
        센서 데이터를 수집하고 raw CSV에 저장한다.

        Args:
            sensor_id (str): 센서 데이터 고유 식별자

        Returns:
            tuple: (dict (센서 데이터), timestamp: float)
                   수집 실패 시 (None, timestamp) 반환
        """
        timestamp = get_timestamp()

        try:
            if self.mock:
                data = self._mock_data()
            else:
                imu_data = self._read_imu()
                baro_data = self._read_baro()
                gps_data = self._read_gps()
                data = {**gps_data, **imu_data, **baro_data}

            # raw CSV 저장
            with open(self.raw_csv_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    sensor_id, timestamp,
                    data['lat'], data['lon'], data['gps_altitude'],
                    data['roll'], data['pitch'], data['yaw'],
                    data['pressure'], data['temp'], data['baro_altitude'],
                    data['accel_x'], data['accel_y'], data['accel_z'],
                    data['gyro_x'], data['gyro_y'], data['gyro_z'],
                    data['calib_sys'], data['calib_gyro'], data['calib_accel'], data['calib_mag'],
                    data['satellites'], data['fix_quality'], data['hdop'],])
            return data, timestamp

        except Exception as e:
            print(f"[Sensor] collection error: {e}")
            return None, timestamp

    def close(self):
        """센서 자원 해제"""
        if self.gps is not None:
            self.gps.close()

            