import sys
import os
import numpy as np
import shutil

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from onboard.input.camera import Camera
from onboard.input.id_manager import IDManager
from onboard.preprocess.image_validator import ImageValidator
from onboard.preprocess.image_quality import ImageQuality
from onboard.preprocess.image_preprocess import ImagePreprocess


def test_image_preprocess():
    print("===== image_preprocess 테스트 =====")

    preprocessor = ImagePreprocess()
    normal_image = np.random.randint(50, 200, (2464, 3280, 3), dtype=np.uint8)

    # 1. 반환값 타입 확인
    result = preprocessor.process(normal_image)
    assert result is not None, "❌ 전처리 실패"
    assert isinstance(result, np.ndarray), f"❌ 타입 오류: {type(result)}"
    print(f"✅ 반환값 타입 확인: np.ndarray")

    # 2. 출력 shape 확인 (640×640×3)
    assert result.shape == (640, 640, 3), f"❌ shape 오류: {result.shape}"
    print(f"✅ 출력 shape 확인: {result.shape}")

    # 3. dtype 확인 (float32)
    assert result.dtype == np.float32, f"❌ dtype 오류: {result.dtype}"
    print(f"✅ dtype 확인: float32")

    # 4. 정규화 범위 확인 (0~1)
    assert result.min() >= 0.0, f"❌ 최솟값 오류: {result.min()}"
    assert result.max() <= 1.0, f"❌ 최댓값 오류: {result.max()}"
    print(f"✅ 정규화 범위 확인: min={result.min():.3f}, max={result.max():.3f}")

    # 5. 다양한 입력 크기 테스트
    for h, w in [(480, 640), (1080, 1920), (100, 100)]:
        test_image = np.random.randint(50, 200, (h, w, 3), dtype=np.uint8)
        result = preprocessor.process(test_image)
        assert result.shape == (640, 640, 3), f"❌ shape 오류 ({h}×{w}): {result.shape}"
    print(f"✅ 다양한 입력 크기 테스트 통과")

    # 6. camera → validator → quality → preprocess 연결 테스트
    print("\n--- camera → validator → quality → preprocess 연결 테스트 ---")
    save_dir = "test/test_output/images"
    camera = Camera(save_dir=save_dir, mock=True)
    validator = ImageValidator()
    quality_checker = ImageQuality()
    id_manager = IDManager()
    normal_imu = {'roll': 2.0, 'pitch': 1.0, 'yaw': 90.0}

    try:
        image_id = id_manager.get_image_id()
        image, timestamp, save_path = camera.capture(image_id)

        validated_image, valid = validator.validate(image)
        assert valid == True, "❌ validator 통과 실패"

        quality, score = quality_checker.check(validated_image, normal_imu)
        assert quality == True, "❌ quality 통과 실패"

        preprocessed = preprocessor.process(validated_image)
        assert preprocessed is not None, "❌ 전처리 실패"
        assert preprocessed.shape == (640, 640, 3), f"❌ shape 오류: {preprocessed.shape}"
        assert preprocessed.dtype == np.float32, f"❌ dtype 오류: {preprocessed.dtype}"
        print(f"✅ camera → validator → quality → preprocess 연결 확인: shape={preprocessed.shape}")

    finally:
        camera.close()
        if os.path.exists(save_dir):
            shutil.rmtree(save_dir)
            print(f"🗑️ 테스트 파일 정리 완료: {save_dir}")

    print("\n✅ image_preprocess 모든 테스트 통과!")


if __name__ == "__main__":
    test_image_preprocess()