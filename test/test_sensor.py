import sys
import os
import csv
import shutil

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from onboard.input.sensor import Sensor
from onboard.input.id_manager import IDManager


def test_sensor():
    print("===== sensor 테스트 =====")

    save_dir = "test/test_output/sensors"
    sensor = Sensor(save_dir=save_dir, mock=True)
    id_manager = IDManager()

    try:
        # 1. 반환값 타입 확인
        sensor_id = id_manager.get_sensor_id()
        data, timestamp = sensor.read(sensor_id)

        assert data is not None, "❌ 센서 데이터 수집 실패"
        assert isinstance(data, dict), f"❌ data 타입 오류: {type(data)}"
        print(f"✅ data 타입 확인: dict")

        # 2. timestamp 타입 확인
        assert isinstance(timestamp, float), f"❌ timestamp 타입 오류: {type(timestamp)}"
        print(f"✅ timestamp 타입 확인: float ({timestamp})")

        # 3. 필수 키 확인
        required_keys = ['lat', 'lon', 'gps_altitude', 'roll', 'pitch', 'yaw', 'pressure', 'temp', 'baro_altitude']
        for key in required_keys:
            assert key in data, f"❌ 키 누락: {key}"
        print(f"✅ 필수 키 확인: {list(data.keys())}")

        # 4. 데이터 타입 확인 (모두 float)
        for key, value in data.items():
            assert isinstance(value, float), f"❌ {key} 타입 오류: {type(value)}"
        print(f"✅ 데이터 타입 확인: 모두 float")

        # 5. 데이터 범위 확인
        assert -90 <= data['lat'] <= 90, f"❌ lat 범위 오류: {data['lat']}"
        assert -180 <= data['lon'] <= 180, f"❌ lon 범위 오류: {data['lon']}"
        assert -180 <= data['roll'] <= 180, f"❌ roll 범위 오류: {data['roll']}"
        assert -90 <= data['pitch'] <= 90, f"❌ pitch 범위 오류: {data['pitch']}"
        assert 0 <= data['yaw'] <= 360, f"❌ yaw 범위 오류: {data['yaw']}"
        print(f"✅ 데이터 범위 확인")

        # 6. CSV 파일 저장 확인
        raw_csv_path = os.path.join(save_dir, "raw_sensor_log.csv")
        assert os.path.exists(raw_csv_path), f"❌ CSV 파일 없음: {raw_csv_path}"
        print(f"✅ CSV 파일 저장 확인: {raw_csv_path}")

        # 7. CSV 헤더 확인
        with open(raw_csv_path, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
        expected_header = ['sensor_id', 'timestamp', 'lat', 'lon', 'gps_altitude', 'roll', 'pitch', 'yaw', 'pressure', 'temp', 'baro_altitude']
        assert header == expected_header, f"❌ 헤더 오류: {header}"
        print(f"✅ CSV 헤더 확인")

        # 8. CSV 데이터 행 확인
        with open(raw_csv_path, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # 헤더 건너뜀
            row = next(reader)
        assert row[0] == sensor_id, f"❌ sensor_id 불일치: {row[0]}"
        print(f"✅ CSV 데이터 행 확인: {row}")

        print("✅ sensor 모든 테스트 통과!\n")

    finally:
        sensor.close()
        if os.path.exists(save_dir):
            shutil.rmtree(save_dir)
            print(f"🗑️ 테스트 파일 정리 완료: {save_dir}")


if __name__ == "__main__":
    test_sensor()