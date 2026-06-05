import cv2
import numpy as np
import os
from onboard.input.timestamp_manager import get_timestamp, format_timestamp
from onboard.config import MOCK_MODE, CAMERA_RESOLUTION, IMAGE_SAVE_DIR
import time

# Pi4 환경에서만 picamera2 import 가능함.
try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False


class Camera:
    """
    카메라 이미지를 캡처하고 SD카드에 저장한다.
    Pi4 환경에서는 Picamera2, 로컬 환경에서는 Mock 이미지를 사용한다.
    """

    def __init__(self, save_dir: str = IMAGE_SAVE_DIR, mock: bool = MOCK_MODE):
        """
        Args:
            save_dir (str): 이미지 저장 경로
            mock (bool): True면 Mock 모드 (로컬 테스트용)
        """
        self.save_dir = save_dir
        self.mock = mock or not PICAMERA_AVAILABLE
        self.camera = None

        os.makedirs(self.save_dir, exist_ok=True)

        if not self.mock:
            self._init_camera()

    def _init_camera(self):
        """Picamera2 초기화"""
        self.camera = Picamera2()
        config = self.camera.create_still_configuration(
            main={"size": CAMERA_RESOLUTION, "format": "RGB888"}
        )
        self.camera.configure(config)
        self.camera.start()
        time.sleep(2)

    def capture(self, image_id: str) -> tuple:
        """
        이미지를 캡처하고 SD카드에 저장한다.

        Args:
            image_id (str): 이미지 고유 식별자

        Returns:
            tuple: (np.ndarray (H×W×3), timestamp: float, save_path: str)
                   캡처 실패 시 (None, timestamp, None) 반환
        """
        timestamp = get_timestamp()

        try:
            if self.mock:
                # Mock: 랜덤 이미지 생성 (로컬 테스트용)
                image = np.random.randint(0, 255, (CAMERA_RESOLUTION[1], CAMERA_RESOLUTION[0], 3), dtype=np.uint8)
            else:
                # 실제 Pi4 카메라 캡처
                image = self.camera.capture_array()

            # SD카드에 저장
            filename = f"{image_id}_{format_timestamp(timestamp)}.jpg"
            save_path = os.path.join(self.save_dir, filename)
            cv2.imwrite(save_path, image)

            return image, timestamp, save_path

        except Exception as e:
            print(f"[Camera] capture error: {e}")
            return None, timestamp, None

    def close(self):
        """카메라 자원 해제"""
        if self.camera is not None:
            self.camera.stop()
            self.camera = None