import sys
import os
import numpy as np
import shutil

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from onboard.input.camera import Camera
from onboard.input.id_manager import IDManager
from onboard.preprocess.image_validator import ImageValidator


def test_image_validator():
    print("===== image_validator 테스트 =====")

    validator = ImageValidator()

    # 1. 정상 이미지 통과 확인
    normal_image = np.random.randint(0, 255, (2464, 3280, 3), dtype=np.uint8)
    result, valid = validator.validate(normal_image)
    assert valid == True, "❌ 정상 이미지 통과 실패"
    assert result is not None, "❌ 정상 이미지 결과 None"
    print("✅ 정상 이미지 통과 확인")

    # 2. None 이미지 감지 확인
    result, valid = validator.validate(None)
    assert valid == False, "❌ None 이미지 감지 실패"
    assert result is None, "❌ None 이미지 결과 None 아님"
    print("✅ None 이미지 감지 확인")

    # 3. shape 오류 감지 확인
    bad_shape = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
    result, valid = validator.validate(bad_shape)
    assert valid == False, "❌ shape 오류 감지 실패"
    print("✅ shape 오류 감지 확인")

    # 4. 너무 작은 이미지 감지 확인
    small_image = np.random.randint(0, 255, (5, 5, 3), dtype=np.uint8)
    result, valid = validator.validate(small_image)
    assert valid == False, "❌ 작은 이미지 감지 실패"
    print("✅ 작은 이미지 감지 확인")

    # 5. 빈 이미지 감지 확인
    empty_image = np.zeros((100, 100, 3), dtype=np.uint8)
    result, valid = validator.validate(empty_image)
    assert valid == False, "❌ 빈 이미지 감지 실패"
    print("✅ 빈 이미지 감지 확인")

    # 6. camera.py 연결 테스트
    print("\n--- camera.py 연결 테스트 ---")
    save_dir = "test/test_output/images"
    camera = Camera(save_dir=save_dir, mock=True)
    id_manager = IDManager()

    try:
        image_id = id_manager.get_image_id()
        image, timestamp, save_path = camera.capture(image_id)

        result, valid = validator.validate(image)
        assert valid == True, "❌ camera 출력 이미지 검증 실패"
        assert result is not None, "❌ camera 출력 이미지 결과 None"
        print(f"✅ camera.py → image_validator.py 연결 확인")

    finally:
        camera.close()
        if os.path.exists(save_dir):
            shutil.rmtree(save_dir)
            print(f"🗑️ 테스트 파일 정리 완료: {save_dir}")

    print("\n✅ image_validator 모든 테스트 통과!")


if __name__ == "__main__":
    test_image_validator()