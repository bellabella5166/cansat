import sys
import os
import csv
import shutil

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from onboard.input.sensor import Sensor
from onboard.input.id_manager import IDManager
from onboard.preprocess.sensor_preprocess import SensorPreprocess
from onboard.preprocess.sensor_logger import SensorLogger


def test_sensor_logger():
    print("===== sensor_logger 테스트 =====")

    save_dir = "test/test_output/sensors"
    logger = SensorLogger(save_dir=save_dir)
    preprocessor = SensorPreprocess()
    sensor = Sensor(mock=True)
    id_manager = IDManager()

    try:
        # 1. 정상 데이터 저장 확인
        sensor_id = id_manager.get_sensor_id()
        data, timestamp = sensor.read(sensor_id)
        processed = preprocessor.process(data, timestamp)

        result = logger.log(processed)
        assert result == True, "❌ 저장 실패"
        print(f"✅ 저장 성공 확인: {result}")

        # 2. CSV 파일 존재 확인
        assert os.path.exists(logger.csv_path), f"❌ CSV 파일 없음: {logger.csv_path}"
        print(f"✅ CSV 파일 존재 확인: {logger.csv_path}")

        # 3. CSV 헤더 확인
        with open(logger.csv_path, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
        expected_header = ['timestamp', 'lat', 'lon', 'gps_altitude', 'roll', 'pitch', 'yaw', 'pressure', 'temp', 'baro_altitude']
        assert header == expected_header, f"❌ 헤더 오류: {header}"
        print(f"✅ CSV 헤더 확인")

        # 4. CSV 데이터 행 확인
        with open(logger.csv_path, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # 헤더 건너뜀
            row = next(reader)
        assert len(row) == 10, f"❌ 컬럼 수 오류: {len(row)}"
        print(f"✅ CSV 데이터 행 확인: {row}")

        # 5. None 입력 처리 확인
        result_none = logger.log(None)
        assert result_none == False, "❌ None 입력 처리 실패"
        print(f"✅ None 입력 처리 확인")

        # 6. 헤더 중복 방지 확인 (재생성해도 헤더 1개만)
        logger2 = SensorLogger(save_dir=save_dir)
        with open(logger.csv_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
        header_count = sum(1 for row in rows if row == expected_header)
        assert header_count == 1, f"❌ 헤더 중복: {header_count}개"
        print(f"✅ 헤더 중복 방지 확인")

        # 7. sensor → sensor_preprocess → sensor_logger 연결 테스트
        print("\n--- sensor → sensor_preprocess → sensor_logger 연결 테스트 ---")
        preprocessor.reset()
        for i in range(3):
            sid = id_manager.get_sensor_id()
            raw_data, ts = sensor.read(sid)
            processed = preprocessor.process(raw_data, ts)
            result = logger.log(processed)
            assert result == True, f"❌ {i+1}번째 저장 실패"
        print(f"✅ sensor → sensor_preprocess → sensor_logger 연결 확인 (3회 연속)")

        print("\n✅ sensor_logger 모든 테스트 통과!")

    finally:
        sensor.close()
        if os.path.exists(save_dir):
            shutil.rmtree(save_dir)
            print(f"🗑️ 테스트 파일 정리 완료: {save_dir}")


if __name__ == "__main__":
    test_sensor_logger()