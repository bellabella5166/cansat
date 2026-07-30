import os
import csv
import numpy as np
import time
import threading
from onboard.input.timestamp_manager import get_timestamp, format_timestamp
from onboard.input.i2c_utils import I2CRetryHelper
from onboard.system.config import (
    MOCK_MODE,
    SENSOR_SAVE_DIR,
    GPS_PORT,
    GPS_BAUDRATE,
    BARO_SENTINEL,
    I2C_RETRY_COUNT,
    I2C_RETRY_DELAY_S,
    I2C_LOCKUP_THRESHOLD,
    SENSOR_FAILURE_TIMEOUT_S,
)
import math

# Pi4 환경에서만 import
try:
    from mpu6050 import mpu6050
    MPU6050_AVAILABLE = True
except ImportError:
    MPU6050_AVAILABLE = False

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
                gimbal_thread도 같은 버스의 IMU를 직접 읽으므로, 스레드 간
                충돌을 막으려면 main.py에서 만든 락을 공유해서 넘겨야 한다.
                넘기지 않으면(예: 테스트) 이 인스턴스 전용 락을 새로 만든다.
        """
        self.save_dir = save_dir
        self.mock = mock or not (MPU6050_AVAILABLE and BMP388_AVAILABLE and GPS_AVAILABLE)
        self._i2c_lock = i2c_lock or threading.Lock()
        self.imu = None
        self._last_gyro_time = None
        self._yaw = 0.0
        self.baro = None
        self.gps = None
        self._last_gps = {...}
        self.ground_altitude = 0.0
        self.ground_altitude_ready = False  # 안정화 완료 여부

        # I2C 재시도 + 버스 락업 감지/리셋 (IMU/Baro 각각 독립적으로 연속 실패 카운트)
        self._imu_retry = I2CRetryHelper(I2C_RETRY_COUNT, I2C_RETRY_DELAY_S,
                                          I2C_LOCKUP_THRESHOLD, name="imu")
        self._baro_retry = I2CRetryHelper(I2C_RETRY_COUNT, I2C_RETRY_DELAY_S,
                                           I2C_LOCKUP_THRESHOLD, name="baro")
        # 읽기 실패 시 짧게 버틸 마지막 유효값 (fallback, SENSOR_FAILURE_TIMEOUT_S까지만 유지)
        self._last_imu_data = None
        self._last_imu_time = None
        self._last_baro_data = None
        self._last_baro_time = None

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
                    'satellites', 'fix_quality', 'hdop',
                ])

    def _init_sensors(self):
        """실제 센서 초기화 (Pi4 전용)"""
        # BNO055 IMU 초기화
        import adafruit_bmp3xx
        import board
        self.imu = mpu6050(0x68)
        i2c = board.I2C()

        # BMP388 Barometer 초기화
        self.baro = adafruit_bmp3xx.BMP3XX_I2C(i2c)
        self.baro.pressure_oversampling = 8
        self.baro.temperature_oversampling = 2

        # GPS 초기화
        self.gps = serial.Serial(GPS_PORT, baudrate=GPS_BAUDRATE, timeout=1)

    def _read_imu_raw(self) -> dict:
        """MPU6050 레지스터 실제 읽기 (Lock/재시도 없이 1회 시도만)"""
        accel_data = self.imu.get_accel_data()
        gyro_data  = self.imu.get_gyro_data()

        ax = accel_data['x']
        ay = accel_data['y']
        az = accel_data['z']
        roll  = math.degrees(math.atan2(ay, az))
        pitch = math.degrees(math.atan2(-ax, math.sqrt(ay**2 + az**2)))

        now = time.monotonic()
        if self._last_gyro_time is None:
            self._last_gyro_time = now
        dt = now - self._last_gyro_time
        self._last_gyro_time = now
        self._yaw += gyro_data['z'] * dt
        self._yaw %= 360.0

        return {
            'roll':    roll,
            'pitch':   pitch,
            'yaw':     self._yaw,
            'accel_x': ax,
            'accel_y': ay,
            'accel_z': az,
            'gyro_x':  gyro_data['x'],
            'gyro_y':  gyro_data['y'],
            'gyro_z':  gyro_data['z'],
        }

    def _read_imu(self) -> dict:
        """IMU 읽기: 공유 I2C Lock + 재시도, 실패 시 마지막 유효값으로 짧게 fallback."""
        now = time.monotonic()
        try:
            with self._i2c_lock:
                data = self._imu_retry.call(self._read_imu_raw)
            self._last_imu_data = data
            self._last_imu_time = now
            return data
        except OSError as e:
            age = now - self._last_imu_time if self._last_imu_time is not None else None
            if self._last_imu_data is not None and age is not None and age < SENSOR_FAILURE_TIMEOUT_S:
                print(f"[Sensor] IMU read failed, using fallback ({age:.1f}s old): {e}")
                return self._last_imu_data
            print(f"[Sensor] IMU read failed, fallback expired or unavailable (age={age}): {e}")
            raise

    def _read_baro_raw(self) -> dict:
        """BMP388 레지스터 실제 읽기 (Lock/재시도 없이 1회 시도만)"""
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

    def _read_baro(self) -> dict:
        """Baro 읽기: 공유 I2C Lock + 재시도, 실패 시 마지막 유효값으로 짧게 fallback."""
        now = time.monotonic()
        try:
            with self._i2c_lock:
                data = self._baro_retry.call(self._read_baro_raw)
            self._last_baro_data = data
            self._last_baro_time = now
            return data
        except OSError as e:
            age = now - self._last_baro_time if self._last_baro_time is not None else None
            if self._last_baro_data is not None and age is not None and age < SENSOR_FAILURE_TIMEOUT_S:
                print(f"[Sensor] Baro read failed, using fallback ({age:.1f}s old): {e}")
                return self._last_baro_data
            print(f"[Sensor] Baro read failed, fallback expired or unavailable (age={age}): {e}")
            raise

    def calibrate_ground_altitude(self, wait_sec: int = 90) -> None:
        """별도 스레드에서 호출. 안정화 대기 후 ground_altitude 설정."""
        import numpy as np
        print(f"[Sensor] Waiting for barometer stabilization ({wait_sec}s)...")
        time.sleep(wait_sec)
        samples = [self.baro.altitude for _ in range(50)]
        self.ground_altitude = sum(samples) / len(samples)
        std = np.std(samples)
        self.ground_altitude_ready = True
        print(f"[Sensor] Ground altitude set: {self.ground_altitude:.2f} m (std={std:.3f}m)")

    def _read_gps(self) -> dict:
        """GPS에서 lat, lon, altitude 읽기"""
        try:
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
                return self._last_gps
        except Exception:
            pass
        return self._last_gps

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
                    data['satellites'], data['fix_quality'], data['hdop'],])
            return data, timestamp

        except Exception as e:
            print(f"[Sensor] collection error: {e}")
            return None, timestamp

    def close(self):
        """센서 자원 해제"""
        if self.gps is not None:
            self.gps.close()

            