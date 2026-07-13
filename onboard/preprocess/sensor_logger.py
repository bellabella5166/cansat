import os
import csv
from onboard.system.config import SENSOR_SAVE_DIR


class SensorLogger:
    """
    전처리된 센서 데이터를 sensor_log.csv로 저장한다.
    """

    def __init__(self, save_dir: str = SENSOR_SAVE_DIR):
        """
        Args:
            save_dir (str): CSV 저장 경로
        """
        self.save_dir = save_dir
        self.csv_path = os.path.join(self.save_dir, "sensor_log.csv")
        os.makedirs(self.save_dir, exist_ok=True)
        self._init_csv()

    def _init_csv(self):
        """CSV 파일 헤더 작성 (파일이 없을 때만)"""
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'lat', 'lon', 'gps_altitude', 'baro_altitude',
                    'roll', 'pitch', 'yaw',
                    'accel_x', 'accel_y', 'accel_z',
                    'gyro_x', 'gyro_y', 'gyro_z',
                    'pressure', 'temp',
                    'satellites', 'fix_quality', 'hdop'
                ])

    def log(self, data: dict) -> bool:
        if data is None:
            print("[SensorLogger] ❌ input data None")
            return False

        try:
            with open(self.csv_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    data['timestamp'],
                    data['lat'], data['lon'], data['gps_altitude'], data['baro_altitude'],
                    data['roll'], data['pitch'], data['yaw'],
                    data['accel_x'], data['accel_y'], data['accel_z'],
                    data['gyro_x'], data['gyro_y'], data['gyro_z'],
                    data['pressure'], data['temp'],
                    data['satellites'], data['fix_quality'], data['hdop']
                ])
            return True

        except Exception as e:
            print(f"[SensorLogger] ❌ save error: {e}")
            return False