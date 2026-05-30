import numpy as np


class ImageValidator:
    """
    손상된 이미지를 감지하고 유효성을 검사한다.
    None 이미지, shape 오류, 디코딩 실패 등을 처리한다.
    """

    def validate(self, image: np.ndarray) -> tuple:
        """
        이미지 유효성을 검사한다.

        Args:
            image (np.ndarray): 입력 이미지 (H×W×3)

        Returns:
            tuple: (np.ndarray or None, valid: bool)
                   유효하면 (image, True), 무효면 (None, False)
        """
        # 1. None 체크
        if image is None:
            print("[ImageValidator] ❌ None 이미지 감지")
            return None, False

        # 2. ndarray 타입 체크
        if not isinstance(image, np.ndarray):
            print(f"[ImageValidator] ❌ 타입 오류: {type(image)}")
            return None, False

        # 3. shape 체크 (3채널 이미지인지)
        if len(image.shape) != 3 or image.shape[2] != 3:
            print(f"[ImageValidator] ❌ shape 오류: {image.shape}")
            return None, False

        # 4. 크기 체크 (너무 작은 이미지 제외)
        if image.shape[0] < 10 or image.shape[1] < 10:
            print(f"[ImageValidator] ❌ 크기 오류: {image.shape}")
            return None, False

        # 5. 데이터 타입 체크
        if image.dtype not in [np.uint8, np.float32, np.float64]:
            print(f"[ImageValidator] ❌ dtype 오류: {image.dtype}")
            return None, False

        # 6. 빈 이미지 체크 (모든 픽셀이 동일한 값)
        if np.all(image == image[0, 0, 0]):
            print("[ImageValidator] ❌ 빈 이미지 감지")
            return None, False

        return image, True