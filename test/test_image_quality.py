import sys
import os
import numpy as np
import shutil

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from onboard.input.camera import Camera
from onboard.input.id_manager import IDManager
from onboard.preprocess.image_validator import ImageValidator
from onboard.preprocess.image_quality import ImageQuality


def test_image_quality():
    print("===== image_quality 테스트 =====")

    quality_checker = ImageQuality()

    # 정상 IMU 데이터
    normal_imu = {'roll': 2.0, 'pitch': 1.0, 'yaw': 90.0}

    # 1. 정상 이미지 통과 확인
    normal_image = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    quality, score = quality_checker.check(normal_image, normal_imu)
    assert isinstance(quality, bool), f"❌ quality 타입 오류: {type(quality)}"
    assert isinstance(score, float), f"❌ score 타입 오류: {type(score)}"
    print(f"✅ 반환값 타입 확인: quality={quality}, score={score:.2f}")

    # 2. 블러 이미지 감지 확인
    blurry_image = np.ones((100, 100, 3), dtype=np.uint8) * 128
    quality, score = quality_checker.check(blurry_image, normal_imu)
    assert quality == False, "❌ 블러 이미지 감지 실패"
    print(f"✅ 블러 이미지 감지 확인: score={score:.2f}")

    # 3. 노출 부족 감지 확인
    dark_image = np.ones((100, 100, 3), dtype=np.uint8) * 10
    quality, score = quality_checker.check(dark_image, normal_imu)
    assert quality == False, "❌ 노출 부족 감지 실패"
    print(f"✅ 노출 부족 감지 확인")

    # 4. 노출 과다 감지 확인
    bright_image = np.ones((100, 100, 3), dtype=np.uint8) * 240
    quality, score = quality_checker.check(bright_image, normal_imu)
    assert quality == False, "❌ 노출 과다 감지 실패"
    print(f"✅ 노출 과다 감지 확인")

    # 5. 자세각 초과 감지 확인
    bad_imu = {'roll': 45.0, 'pitch': 1.0, 'yaw': 90.0}
    normal_image2 = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    quality, score = quality_checker.check(normal_image2, bad_imu)
    assert quality == False, "❌ 자세각 초과 감지 실패"
    print(f"✅ 자세각 초과 감지 확인")

    # 6. camera → validator → quality 연결 테스트
    print("\n--- camera → validator → quality 연결 테스트 ---")
    save_dir = "test/test_output/images"
    camera = Camera(save_dir=save_dir, mock=True)
    validator = ImageValidator()
    id_manager = IDManager()

    try:
        image_id = id_manager.get_image_id()
        image, timestamp, save_path = camera.capture(image_id)

        validated_image, valid = validator.validate(image)
        assert valid == True, "❌ validator 통과 실패"

        quality, score = quality_checker.check(validated_image, normal_imu)
        assert isinstance(quality, bool), "❌ quality 타입 오류"
        assert isinstance(score, float), "❌ score 타입 오류"
        print(f"✅ camera → validator → quality 연결 확인: quality={quality}, score={score:.2f}")

    finally:
        camera.close()
        if os.path.exists(save_dir):
            shutil.rmtree(save_dir)
            print(f"🗑️ 테스트 파일 정리 완료: {save_dir}")

    print("\n✅ image_quality 모든 테스트 통과!")


if __name__ == "__main__":
    test_image_quality()