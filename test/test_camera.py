import sys
import os
import numpy as np
import shutil

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from onboard.input.camera import Camera
from onboard.input.id_manager import IDManager


def test_camera():
    print("===== camera 테스트 =====")

    save_dir = "test/test_output/images"
    camera = Camera(save_dir=save_dir, mock=True)
    id_manager = IDManager()

    try:
        # 1. 캡처 반환값 타입 확인
        image_id = id_manager.get_image_id()
        image, timestamp, save_path = camera.capture(image_id)

        assert image is not None, "❌ 이미지 캡처 실패"
        assert isinstance(image, np.ndarray), f"❌ 이미지 타입 오류: {type(image)}"
        print(f"✅ 이미지 타입 확인: np.ndarray")

        # 2. 이미지 shape 확인
        assert len(image.shape) == 3, f"❌ shape 오류: {image.shape}"
        assert image.shape[2] == 3, f"❌ 채널 오류: {image.shape}"
        print(f"✅ 이미지 shape 확인: {image.shape}")

        # 3. timestamp 타입 확인
        assert isinstance(timestamp, float), f"❌ timestamp 타입 오류: {type(timestamp)}"
        print(f"✅ timestamp 타입 확인: float ({timestamp})")

        # 4. 파일 저장 확인
        assert save_path is not None, "❌ 저장 경로 없음"
        assert os.path.exists(save_path), f"❌ 파일 저장 실패: {save_path}"
        print(f"✅ 파일 저장 확인: {save_path}")

        # 5. 파일명 형식 확인 (image_id 포함)
        filename = os.path.basename(save_path)
        assert image_id in filename, f"❌ 파일명에 image_id 없음: {filename}"
        print(f"✅ 파일명 형식 확인: {filename}")

        print("✅ camera 모든 테스트 통과!\n")

    finally:
        camera.close()
        # 테스트 후 생성된 파일 정리
        if os.path.exists(save_dir):
            shutil.rmtree(save_dir)
            print(f"🗑️ 테스트 파일 정리 완료: {save_dir}")


if __name__ == "__main__":
    test_camera()