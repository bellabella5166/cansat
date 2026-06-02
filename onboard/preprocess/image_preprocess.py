import cv2
import numpy as np
from onboard.config import PREPROCESS_SIZE


class ImagePreprocess:
    """
    이미지를 YOLOv8n 입력 형식으로 전처리한다.
    letterbox 방식으로 640×640 리사이징 및 0~1 정규화를 수행한다.
    """

    def __init__(self, size: int = PREPROCESS_SIZE):
        """
        Args:
            size (int): 리사이징 목표 크기 (정사각형)
        """
        self.size = size

    def process(self, image: np.ndarray) -> np.ndarray:
        """
        이미지를 letterbox 방식으로 리사이징하고 정규화한다.

        Args:
            image (np.ndarray): 입력 이미지 (H×W×3, RGB, uint8)

        Returns:
            np.ndarray: 전처리된 이미지 (640×640×3, float32, 0~1)
                        실패 시 None 반환
        """
        try:
            h, w = image.shape[:2]

            # letterbox 리사이징
            scale = self.size / max(h, w)
            new_h, new_w = int(h * scale), int(w * scale)
            resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

            # 패딩 추가 (640×640 맞추기)
            pad_top = (self.size - new_h) // 2
            pad_bottom = self.size - new_h - pad_top
            pad_left = (self.size - new_w) // 2
            pad_right = self.size - new_w - pad_left

            padded = cv2.copyMakeBorder(
                resized,
                pad_top, pad_bottom, pad_left, pad_right,
                cv2.BORDER_CONSTANT, value=(114, 114, 114)
            )

            # 0~1 정규화
            normalized = padded.astype(np.float32) / 255.0

            return normalized

        except Exception as e:
            print(f"[ImagePreprocess] ❌ preprocess error: {e}")
            return None