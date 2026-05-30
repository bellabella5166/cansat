import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from onboard.input.id_manager import IDManager


def test_id_manager():
    print("===== id_manager 테스트 =====")

    id_manager = IDManager()

    # 1. image_id 타입 확인
    image_id = id_manager.get_image_id()
    assert isinstance(image_id, str), f"❌ 타입 오류: {type(image_id)}"
    print(f"✅ image_id 타입 확인: str")

    # 2. image_id 형식 확인 (IMG_00000001)
    assert image_id == "IMG_00000001", f"❌ 형식 오류: {image_id}"
    print(f"✅ image_id 형식 확인: {image_id}")

    # 3. image_id 순서대로 증가하는지 확인
    image_id2 = id_manager.get_image_id()
    assert image_id2 == "IMG_00000002", f"❌ 증가 오류: {image_id2}"
    print(f"✅ image_id 증가 확인: {image_id2}")

    # 4. sensor_id 타입 및 형식 확인
    sensor_id = id_manager.get_sensor_id()
    assert isinstance(sensor_id, str), f"❌ 타입 오류: {type(sensor_id)}"
    assert sensor_id == "SEN_00000001", f"❌ 형식 오류: {sensor_id}"
    print(f"✅ sensor_id 형식 확인: {sensor_id}")

    # 5. image_id와 sensor_id 카운터 독립적인지 확인
    sensor_id2 = id_manager.get_sensor_id()
    image_id3 = id_manager.get_image_id()
    assert sensor_id2 == "SEN_00000002", f"❌ sensor 카운터 오류: {sensor_id2}"
    assert image_id3 == "IMG_00000003", f"❌ image 카운터 오류: {image_id3}"
    print(f"✅ 카운터 독립성 확인: image={image_id3}, sensor={sensor_id2}")

    # 6. reset() 확인
    id_manager.reset()
    image_id_reset = id_manager.get_image_id()
    assert image_id_reset == "IMG_00000001", f"❌ reset 오류: {image_id_reset}"
    print(f"✅ reset 확인: {image_id_reset}")

    print("✅ id_manager 모든 테스트 통과!\n")


if __name__ == "__main__":
    test_id_manager()