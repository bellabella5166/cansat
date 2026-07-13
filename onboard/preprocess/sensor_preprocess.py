import numpy as np
import math
from onboard.system.config import SENSOR_LOWPASS_ALPHA, GPS_MAX_SPEED, GPS_MAX_HDOP


class SensorPreprocess:
    """
    센서 데이터 이상치 제거, low-pass filter 적용, 정규화를 수행한다.
    """

    def __init__(self, alpha: float = SENSOR_LOWPASS_ALPHA):
        """
        Args:
            alpha (float): low-pass filter 계수 (0~1, 낮을수록 더 많이 필터링)
        """
        self.alpha = alpha
        self._prev = None  # 이전 필터링 결과 저장
        self._prev_gps = None  # 이전 GPS 좌표 저장

    def process(self, data: dict, timestamp: float) -> dict:
        """
        센서 데이터를 전처리한다.

        Args:
            data (dict): 원시 센서 데이터
            timestamp (float): 타임스탬프

        Returns:
            dict: 전처리된 센서 데이터 + timestamp
                실패 시 None 반환
        """
    
        if data is None:
            print("[SensorPreprocess] ❌ input data None")
            return None

        try:
            # 1. 이상치 제거
            cleaned = self._remove_outliers(data)
            if cleaned is None:
                return None

            # 2. low-pass filter 적용
            filtered = self._low_pass_filter(cleaned)

            # 3. timestamp 추가
            filtered['timestamp'] = timestamp

            return filtered

        except Exception as e:
            print(f"[SensorPreprocess] ❌ preprocess error: {e}")
            return None
        

    def _remove_outliers(self, data: dict) -> dict:
        cleaned = data.copy()
        # GPS fix_quality/hdop 기반 필터링
        if data.get('fix_quality', 0) == 0:
            print("[SensorPreprocess] GPS fix not available, skipping GPS")
            cleaned['lat'] = self._prev_gps[0] if self._prev_gps else 0.0
            cleaned['lon'] = self._prev_gps[1] if self._prev_gps else 0.0
            cleaned['gps_altitude'] = data['gps_altitude']
        elif data.get('hdop', 99.0) > GPS_MAX_HDOP:
            print("[SensorPreprocess] GPS hdop too high, skipping GPS")
            cleaned['lat'] = self._prev_gps[0] if self._prev_gps else 0.0
            cleaned['lon'] = self._prev_gps[1] if self._prev_gps else 0.0
            cleaned['gps_altitude'] = data['gps_altitude']
        else:
            lat = float(np.clip(data['lat'], -90.0, 90.0))
            lon = float(np.clip(data['lon'], -180.0, 180.0))
            if self._prev_gps is not None:
                dlat = (lat - self._prev_gps[0]) * 111320.0
                dlon = (lon - self._prev_gps[1]) * 111320.0 * math.cos(math.radians(lat))
                dist = math.sqrt(dlat**2 + dlon**2)
                if dist > GPS_MAX_SPEED * 1.0:
                    print(f"[SensorPreprocess] GPS jump detected: {dist:.2f}m, skipping")
                    cleaned['lat'] = self._prev_gps[0]
                    cleaned['lon'] = self._prev_gps[1]
                else:
                    cleaned['lat'] = lat
                    cleaned['lon'] = lon
                    self._prev_gps = (lat, lon)
            else:
                cleaned['lat'] = lat
                cleaned['lon'] = lon
                self._prev_gps = (lat, lon)
            cleaned['gps_altitude'] = float(np.clip(data['gps_altitude'], -500.0, 50000.0))
        # IMU
        cleaned['roll'] = float(np.clip(data['roll'], -180.0, 180.0))
        cleaned['pitch'] = float(np.clip(data['pitch'], -90.0, 90.0))
        cleaned['yaw'] = float(np.clip(data['yaw'], 0.0, 360.0))
        cleaned['accel_x'] = float(np.clip(data['accel_x'], -156.9, 156.9))
        cleaned['accel_y'] = float(np.clip(data['accel_y'], -156.9, 156.9))
        cleaned['accel_z'] = float(np.clip(data['accel_z'], -156.9, 156.9))
        cleaned['gyro_x'] = float(np.clip(data['gyro_x'], -2000.0, 2000.0))
        cleaned['gyro_y'] = float(np.clip(data['gyro_y'], -2000.0, 2000.0))
        cleaned['gyro_z'] = float(np.clip(data['gyro_z'], -2000.0, 2000.0))
        # Barometer
        cleaned['pressure'] = float(np.clip(data['pressure'], 300.0, 1100.0))
        cleaned['temp'] = float(np.clip(data['temp'], -40.0, 85.0))
        cleaned['baro_altitude'] = float(np.clip(data['baro_altitude'], -500.0, 50000.0))
        # GPS 품질
        cleaned['satellites'] = int(data.get('satellites', 0))
        cleaned['fix_quality'] = int(data.get('fix_quality', 0))
        cleaned['hdop'] = float(np.clip(data.get('hdop', 0.0), 0.0, 99.9))
        return cleaned
    
    def _low_pass_filter(self, data: dict) -> dict:
        """
        low-pass filter를 적용한다.
        y[n] = alpha * x[n] + (1 - alpha) * y[n-1]
        """
        if self._prev is None:
            self._prev = data.copy()
            return data.copy()

        filtered = {}
        int_keys = ['satellites', 'fix_quality']
        skip_keys = ['lat', 'lon', 'gps_altitude']

        for key, value in data.items():
            if key in skip_keys:
                filtered[key] = value  # 필터 미적용, 원본 그대로
            elif isinstance(value, (int, float)):
                new_val = self.alpha * value + (1 - self.alpha) * self._prev.get(key, value)
                filtered[key] = int(round(new_val)) if key in int_keys else new_val
            else:
                filtered[key] = value

        self._prev = filtered.copy()
        return filtered

    def reset(self):
        """필터 상태 초기화 (테스트 용도)"""
        self._prev = None