import os
import csv
from onboard.config import SENSOR_SAVE_DIR


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
                    'lat', 'lon', 'gps_altitude',
                    'roll', 'pitch', 'yaw',
                    'pressure', 'temp', 'baro_altitude'
                ])

    def log(self, data: dict) -> bool:
        """
        전처리된 센서 데이터를 CSV에 저장한다.

        Args:
            data (dict): 전처리된 센서 데이터 (timestamp 포함)

        Returns:
            bool: 저장 성공 시 True, 실패 시 False
        """
        if data is None:
            print("[SensorLogger] ❌ 입력 데이터 None")
            return False

        try:
            with open(self.csv_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    data['timestamp'],
                    data['lat'], data['lon'], data['gps_altitude'],
                    data['roll'], data['pitch'], data['yaw'],
                    data['pressure'], data['temp'], data['baro_altitude']
                ])
            return True

        except Exception as e:
            print(f"[SensorLogger] ❌ 저장 오류: {e}")
            return False