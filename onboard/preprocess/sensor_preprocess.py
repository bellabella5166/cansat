import numpy as np
from onboard.config import SENSOR_LOWPASS_ALPHA


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
            print("[SensorPreprocess] ❌ 입력 데이터 None")
            return None

        try:
            # 1. 이상치 제거
            cleaned = self._remove_outliers(data)

            # 2. low-pass filter 적용
            filtered = self._low_pass_filter(cleaned)

            return filtered

        except Exception as e:
            print(f"[SensorPreprocess] ❌ 전처리 오류: {e}")
            return None
        

    def _remove_outliers(self, data: dict) -> dict:
        """
        센서 데이터 이상치를 제거한다.
        각 센서값의 물리적 범위를 벗어난 값을 클리핑한다.
        """
        cleaned = data.copy()
        cleaned['lat'] = float(np.clip(data['lat'], -90.0, 90.0))
        cleaned['lon'] = float(np.clip(data['lon'], -180.0, 180.0))
        cleaned['gps_altitude'] = float(np.clip(data['gps_altitude'], -500.0, 50000.0))
        cleaned['roll'] = float(np.clip(data['roll'], -180.0, 180.0))
        cleaned['pitch'] = float(np.clip(data['pitch'], -90.0, 90.0))
        cleaned['yaw'] = float(np.clip(data['yaw'], 0.0, 360.0))
        cleaned['pressure'] = float(np.clip(data['pressure'], 300.0, 1100.0))
        cleaned['temp'] = float(np.clip(data['temp'], -40.0, 85.0))
        cleaned['baro_altitude'] = float(np.clip(data['baro_altitude'], -500.0, 50000.0))
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
        for key, value in data.items():
            if isinstance(value, (int, float)):
                filtered[key] = self.alpha * value + (1 - self.alpha) * self._prev.get(key, value)
            else:
                filtered[key] = value

        self._prev = filtered.copy()
        return filtered

    def reset(self):
        """필터 상태 초기화 (테스트 용도)"""
        self._prev = None