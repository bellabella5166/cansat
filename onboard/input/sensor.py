import os
import csv
import numpy as np
from onboard.input.timestamp_manager import get_timestamp, format_timestamp
from onboard.config import (
    MOCK_MODE,
    SENSOR_SAVE_DIR,
    GPS_PORT,
    GPS_BAUDRATE,
)

# Pi4 환경에서만 import
try:
    import board
    import adafruit_bno055
    BNO055_AVAILABLE = True
except ImportError:
    BNO055_AVAILABLE = False

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

    def __init__(self, save_dir: str = SENSOR_SAVE_DIR, mock: bool = MOCK_MODE):
        """
        Args:
            save_dir (str): 센서 데이터 저장 경로
            mock (bool): True면 Mock 모드 (로컬 테스트용)
        """
        self.save_dir = save_dir
        self.mock = mock or not (BNO055_AVAILABLE and BMP388_AVAILABLE and GPS_AVAILABLE)
        self.imu = None
        self.baro = None
        self.gps = None

        os.makedirs(self.save_dir, exist_ok=True)

        # raw CSV 파일 초기화
        self.raw_csv_path = os.path.join(self.save_dir, "raw_sensor_log.csv")
        self._init_csv()

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
                    'pressure', 'temp', 'baro_altitude'
                ])

    def _init_sensors(self):
        """실제 센서 초기화 (Pi4 전용)"""
        # BNO055 IMU 초기화
        i2c = board.I2C()
        self.imu = adafruit_bno055.BNO055_I2C(i2c)

        # BMP388 Barometer 초기화
        self.baro = adafruit_bmp3xx.BMP3XX_I2C(i2c)
        self.baro.pressure_oversampling = 8
        self.baro.temperature_oversampling = 2

        # GPS 초기화
        self.gps = serial.Serial(GPS_PORT, baudrate=GPS_BAUDRATE, timeout=1)

    def _read_imu(self) -> dict:
        """BNO055에서 roll, pitch, yaw 읽기"""
        euler = self.imu.euler
        return {
            'roll': euler[2] if euler[2] is not None else 0.0,
            'pitch': euler[1] if euler[1] is not None else 0.0,
            'yaw': euler[0] if euler[0] is not None else 0.0,
        }

    def _read_baro(self) -> dict:
        """BMP388에서 pressure, temp, altitude 읽기"""
        return {
            'pressure': self.baro.pressure,
            'temp': self.baro.temperature,
            'baro_altitude': self.baro.altitude,
        }

    def _read_gps(self) -> dict:
        """GPS에서 lat, lon, altitude 읽기"""
        try:
            line = self.gps.readline().decode('ascii', errors='replace')
            if line.startswith('$GPGGA'):
                msg = pynmea2.parse(line)
                return {
                    'lat': float(msg.latitude),
                    'lon': float(msg.longitude),
                    'gps_altitude': float(msg.altitude),
                }
        except Exception:
            pass
        return {'lat': 0.0, 'lon': 0.0, 'gps_altitude': 0.0}

    def _mock_data(self) -> dict:
        """Mock 센서 데이터 생성 (로컬 테스트용)"""
        return {
            'lat': 37.5 + np.random.uniform(-0.001, 0.001),
            'lon': 127.0 + np.random.uniform(-0.001, 0.001),
            'gps_altitude': 350.0 + np.random.uniform(-5.0, 5.0),
            'roll': np.random.uniform(-5.0, 5.0),
            'pitch': np.random.uniform(-5.0, 5.0),
            'yaw': np.random.uniform(0.0, 360.0),
            'pressure': 1013.25 + np.random.uniform(-1.0, 1.0),
            'temp': 25.0 + np.random.uniform(-1.0, 1.0),
            'baro_altitude': 350.0 + np.random.uniform(-5.0, 5.0),
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
                    data['pressure'], data['temp'], data['baro_altitude']
                ])

            return data, timestamp

        except Exception as e:
            print(f"[Sensor] 수집 오류: {e}")
            return None, timestamp

    def close(self):
        """센서 자원 해제"""
        if self.gps is not None:
            self.gps.close()