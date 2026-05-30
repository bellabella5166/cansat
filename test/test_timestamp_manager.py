# test_timestamp_manager.py

import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from onboard.input.timestamp_manager import get_timestamp, format_timestamp


def test_get_timestamp():
    """get_timestamp() 테스트"""
    print("===== test_get_timestamp =====")

    ts = get_timestamp()

    # 1. float 타입인지 확인
    assert isinstance(ts, float), f"❌ 타입 오류: {type(ts)}"
    print(f"✅ 타입 확인: float")

    # 2. 현재 시각과 오차 1초 이내인지 확인
    now = time.time()
    assert abs(ts - now) < 1.0, f"❌ 시각 오류: {ts} vs {now}"
    print(f"✅ 현재 시각과 오차 1초 이내: {ts}")

    # 3. 연속 호출 시 시간이 증가하는지 확인
    ts1 = get_timestamp()
    time.sleep(0.01)
    ts2 = get_timestamp()
    assert ts2 > ts1, f"❌ 시간 증가 오류: {ts1} -> {ts2}"
    print(f"✅ 연속 호출 시 시간 증가: {ts1:.3f} -> {ts2:.3f}")


def test_format_timestamp():
    """format_timestamp() 테스트"""
    print("\n===== test_format_timestamp =====")

    ts = get_timestamp()
    formatted = format_timestamp(ts)

    # 1. 문자열 타입인지 확인
    assert isinstance(formatted, str), f"❌ 타입 오류: {type(formatted)}"
    print(f"✅ 타입 확인: str")

    # 2. 형식 확인 (YYYY-MM-DD_HH-MM-SS.mmm)
    assert len(formatted) == 23, f"❌ 길이 오류: {len(formatted)} ({formatted})"
    print(f"✅ 형식 확인: {formatted}")

    # 3. ms 범위 확인 (000~999)
    ms = int(formatted.split(".")[1])
    assert 0 <= ms <= 999, f"❌ ms 범위 오류: {ms}"
    print(f"✅ ms 범위 확인: {ms}")

    # 4. 구분자 확인
    assert formatted[4] == "-" and formatted[7] == "-", "❌ 날짜 구분자 오류"
    assert formatted[10] == "_", "❌ 날짜-시간 구분자 오류"
    assert formatted[13] == "-" and formatted[16] == "-", "❌ 시간 구분자 오류"
    assert formatted[19] == ".", "❌ ms 구분자 오류"
    print(f"✅ 구분자 확인")


if __name__ == "__main__":
    test_get_timestamp()
    test_format_timestamp()
    print("\n✅ 모든 테스트 통과!")