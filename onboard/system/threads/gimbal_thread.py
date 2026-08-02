# onboard/system/threads/gimbal_thread.py

from __future__ import annotations

import logging
import time
from onboard.system.config import (
    GIMBAL_MOCK,
    GIMBAL_SLEW, GIMBAL_LIM,
    GIMBAL_PIN_ROLL, GIMBAL_PIN_PITCH,
    GIMBAL_NEUTRAL_ROLL, GIMBAL_NEUTRAL_PITCH,
    GIMBAL_DT,
)

logger = logging.getLogger("onboard.gimbal")

# ── 설정 ──────────────────────────────────────────────────────────────────────
MOCK          = GIMBAL_MOCK
SLEW          = GIMBAL_SLEW
LIM           = GIMBAL_LIM
PIN_ROLL      = GIMBAL_PIN_ROLL
PIN_PITCH     = GIMBAL_PIN_PITCH
NEUTRAL_ROLL  = GIMBAL_NEUTRAL_ROLL
NEUTRAL_PITCH = GIMBAL_NEUTRAL_PITCH
DT            = GIMBAL_DT


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def gimbal_loop(running: list, i2c_lock, imu) -> None:
    """
    BNO055는 칩 내부에서 9축 센서 퓨전을 직접 수행해 roll/pitch를 바로
    제공하므로, MPU6050 때처럼 raw accel/gyro로 상보필터를 직접 계산할
    필요가 없다 (sensor.py의 _read_imu()와 동일하게 .euler를 그대로 사용).

    imu는 sensor.py의 Sensor가 만든 BNO055_I2C 인스턴스를 그대로 공유
    받는다 — 여기서 별도로 새 BNO055_I2C()를 만들면 생성자가 칩을 다시
    리셋해서 Sensor 쪽이 쌓아온 캘리브레이션 상태를 날릴 수 있기 때문.
    같은 물리 I2C 버스를 다른 스레드(sensor_thread)와 동시에 쓰므로
    공유 i2c_lock으로 접근을 감싼다.
    """
    if imu is None:
        logger.error("Gimbal: IMU not available (Sensor가 mock 모드이거나 초기화 실패)")
        return

    lgpio = None
    if not MOCK:
        # pigpio는 데몬(pigpiod) 기반이라 Debian trixie부터 apt 저장소에서 빠져
        # 설치가 안 된다 (pip pigpio 클라이언트만 있어도 데몬이 없으면 무용지물).
        # 데몬 없이 커널 gpiochip 캐릭터 디바이스로 직접 동작하는 lgpio로 대체.
        try:
            import lgpio as _lgpio
            lgpio = _lgpio
        except ImportError as e:
            logger.error("Gimbal: library not found: %s", e)
            return

    h = None
    if MOCK:
        logger.info("Gimbal: GIMBAL_MOCK=True — servo/GPIO control skipped, logging only")
    else:
        try:
            h = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(h, PIN_ROLL)
            lgpio.gpio_claim_output(h, PIN_PITCH)
        except Exception as e:
            logger.error("Gimbal: lgpio gpiochip open failed: %s", e)
            return

    cmd = {"roll": 0.0, "pitch": 0.0}
    tick = 0

    logger.info("Gimbal loop started (50Hz)")

    while running[0]:
        loop_start = time.monotonic()
        tick += 1

        try:
            with i2c_lock:
                _, roll, pitch = imu.euler

            if roll is None or pitch is None:
                raise ValueError("BNO055 euler not ready yet")

            # 45도 축변환 (짐벌 장착 방향)
            g_roll  = (roll - pitch) * 0.7071
            g_pitch = (roll + pitch) * 0.7071

            # 서보 제어
            for ax_name, ang in (("roll", g_roll), ("pitch", g_pitch)):
                target = _clamp(-ang, -LIM, LIM)  # 반대 방향 보상
                step   = _clamp(target - cmd[ax_name], -SLEW, SLEW)
                cmd[ax_name] += step

            servo_roll  = int(NEUTRAL_ROLL  + cmd["roll"]  * 10.0)
            servo_pitch = int(NEUTRAL_PITCH + cmd["pitch"] * 10.0)

            if MOCK:
                if tick % 50 == 0:  # 50Hz 루프에서 매 틱 로그는 과함 — 약 1초 간격으로 downsample
                    logger.info("Gimbal (mock): roll=%.2f pitch=%.2f -> servo_roll=%d servo_pitch=%d",
                                g_roll, g_pitch, servo_roll, servo_pitch)
            else:
                lgpio.tx_servo(h, PIN_ROLL,  servo_roll)
                lgpio.tx_servo(h, PIN_PITCH, servo_pitch)

        except Exception as e:
            logger.error("Gimbal loop error: %s", e)

        elapsed = time.monotonic() - loop_start
        time.sleep(max(0.0, DT-elapsed))

    # 종료 시 서보 중립 복귀 후 PWM 정지
    if MOCK:
        logger.info("Gimbal (mock): servo neutral return skipped")
    else:
        lgpio.tx_servo(h, PIN_ROLL,  NEUTRAL_ROLL)
        lgpio.tx_servo(h, PIN_PITCH, NEUTRAL_PITCH)
        time.sleep(0.3)  # 중립 위치로 복귀할 시간 확보
        lgpio.tx_servo(h, PIN_ROLL,  0)
        lgpio.tx_servo(h, PIN_PITCH, 0)
        lgpio.gpio_free(h, PIN_ROLL)
        lgpio.gpio_free(h, PIN_PITCH)
        lgpio.gpiochip_close(h)
    logger.info("Gimbal loop stopped")
