import cv2
import numpy as np
import os
from onboard.input.timestamp_manager import get_timestamp, format_timestamp
from onboard.system.config import MOCK_MODE, CAMERA_RESOLUTION, IMAGE_SAVE_DIR
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
            self._init_camera_with_retry()

    def _init_camera_with_retry(self, retry_count: int = 3, retry_delay_s: float = 1.5) -> None:
        """카메라 초기화를 몇 번 재시도하고, 그래도 실패하면 mock으로 폴백한다.

        여기서 예외가 그냥 새어나가면 Camera() 생성자가 죽고, main()이
        스레드를 하나도 못 띄운 채 프로그램 전체가 시작도 못 한다.
        리본 케이블이 살짝 흔들린 정도의 일시적 문제는 재시도로 풀리는
        경우가 많고, 그래도 안 되면 mock으로 내려가서 센서/통신 등
        나머지 파이프라인은 계속 돌게 한다.
        """
        last_exc = None
        for attempt in range(1, retry_count + 1):
            try:
                self._init_camera()
                return
            except Exception as e:
                last_exc = e
                print(f"[Camera] init failed (attempt {attempt}/{retry_count}): {e}")
                self.camera = None
                if attempt < retry_count:
                    time.sleep(retry_delay_s)
        print(f"[Camera] init failed after {retry_count} attempts, falling back to mock mode: {last_exc}")
        self.mock = True

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