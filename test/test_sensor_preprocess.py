import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from onboard.input.sensor import Sensor
from onboard.input.id_manager import IDManager
from onboard.preprocess.sensor_preprocess import SensorPreprocess


def test_sensor_preprocess():
    print("===== sensor_preprocess 테스트 =====")

    preprocessor = SensorPreprocess()
    id_manager = IDManager()
    sensor = Sensor(mock=True)

    try:
        # 1. 정상 데이터 전처리 확인
        sensor_id = id_manager.get_sensor_id()
        data, timestamp = sensor.read(sensor_id)

        result = preprocessor.process(data, timestamp)
        assert result is not None, "❌ 전처리 실패"
        assert isinstance(result, dict), f"❌ 타입 오류: {type(result)}"
        print(f"✅ 반환값 타입 확인: dict")

        # 2. 필수 키 확인 (timestamp 포함)
        required_keys = ['lat', 'lon', 'gps_altitude', 'roll', 'pitch', 'yaw', 'pressure', 'temp', 'baro_altitude', 'timestamp']
        for key in required_keys:
            assert key in result, f"❌ 키 누락: {key}"
        print(f"✅ 필수 키 확인 (timestamp 포함)")

        # 3. 데이터 타입 확인
        for key, value in result.items():
            assert isinstance(value, float), f"❌ {key} 타입 오류: {type(value)}"
        print(f"✅ 데이터 타입 확인: 모두 float")

        # 4. 범위 확인
        assert -90 <= result['lat'] <= 90, f"❌ lat 범위 오류: {result['lat']}"
        assert -180 <= result['lon'] <= 180, f"❌ lon 범위 오류: {result['lon']}"
        assert 300 <= result['pressure'] <= 1100, f"❌ pressure 범위 오류: {result['pressure']}"
        print(f"✅ 범위 확인")

        # 5. None 입력 처리 확인
        result_none = preprocessor.process(None, timestamp)
        assert result_none is None, "❌ None 입력 처리 실패"
        print(f"✅ None 입력 처리 확인")

        # 6. low-pass filter 동작 확인 (두 번 호출 시 값이 달라야 함)
        preprocessor.reset()
        data2, timestamp2 = sensor.read(id_manager.get_sensor_id())
        result1 = preprocessor.process(data, timestamp)
        result2 = preprocessor.process(data2, timestamp2)
        assert result1 != result2, "❌ low-pass filter 동작 실패"
        print(f"✅ low-pass filter 동작 확인")

        # 7. sensor → sensor_preprocess 연결 테스트
        print("\n--- sensor → sensor_preprocess 연결 테스트 ---")
        preprocessor.reset()
        for i in range(3):
            sid = id_manager.get_sensor_id()
            raw_data, ts = sensor.read(sid)
            processed = preprocessor.process(raw_data, ts)
            assert processed is not None, f"❌ {i+1}번째 전처리 실패"
        print(f"✅ sensor → sensor_preprocess 연결 확인 (3회 연속)")

        print("\n✅ sensor_preprocess 모든 테스트 통과!")

    finally:
        sensor.close()


if __name__ == "__main__":
    test_sensor_preprocess()