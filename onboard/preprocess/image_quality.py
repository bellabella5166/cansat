import cv2
import numpy as np
from onboard.system.config import (
    LAPLACIAN_THRESHOLD,
    EXPOSURE_LOW,
    EXPOSURE_HIGH,
    ATTITUDE_THRESHOLD,
)


class ImageQuality:
    """
    이미지 품질을 판별한다.
    라플라시안 분산(블러), 노출 이상, IMU 자세각 융합으로 품질을 판단한다.
    """

    def check(self, image: np.ndarray, imu: dict) -> tuple:
        """
        이미지 품질을 판별한다.

        Args:
            image (np.ndarray): 입력 이미지 (H×W×3, RGB)
            imu (dict): IMU 데이터 (roll, pitch, yaw 포함)

        Returns:
            tuple: (quality: bool, laplacian_score: float)
                   통과하면 (True, score), 실패하면 (False, score)
        """
        # 1. 블러 감지 (라플라시안 분산)
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        laplacian_score = cv2.Laplacian(gray, cv2.CV_64F).var()

        if laplacian_score < LAPLACIAN_THRESHOLD:
            print(f"[ImageQuality] ❌ blur detection: laplacian_score={laplacian_score:.2f}")
            return False, laplacian_score

        # 2. 노출 이상 감지
        mean_brightness = gray.mean()
        if mean_brightness < EXPOSURE_LOW:
            print(f"[ImageQuality] ❌ brightness lack: brightness={mean_brightness:.2f}")
            return False, laplacian_score

        if mean_brightness > EXPOSURE_HIGH:
            print(f"[ImageQuality] ❌ brightness excess : brightness={mean_brightness:.2f}")
            return False, laplacian_score