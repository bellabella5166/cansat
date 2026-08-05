# onboard/system/threads/gimbal_thread.py

from __future__ import annotations

import logging
import time
from onboard.system.config import (
    GIMBAL_MOCK,
    GIMBAL_SLEW,
    GIMBAL_ROLL_LIM_POS, GIMBAL_ROLL_LIM_NEG,
    GIMBAL_PITCH_LIM_POS, GIMBAL_PITCH_LIM_NEG,
    GIMBAL_DEADBAND_DEG, GIMBAL_ANGLE_SMOOTH_ALPHA, GIMBAL_US_PER_DEG,
    GIMBAL_PIN_ROLL, GIMBAL_PIN_PITCH,
    GIMBAL_NEUTRAL_ROLL, GIMBAL_NEUTRAL_PITCH,
    GIMBAL_DT,
)

logger = logging.getLogger("onboard.gimbal")

# ── 설정 ──────────────────────────────────────────────────────────────────────
MOCK          = GIMBAL_MOCK
SLEW          = GIMBAL_SLEW
# 실측 검증된 축별 비대칭 리밋 — roll+pitch를 동시에 극단까지 밀어도 구조체와
# 충돌하지 않는다고 확인된 조합. 축마다 (lo, hi)가 다르므로 분리해서 관리.
LIMITS = {
    "roll":  (-GIMBAL_ROLL_LIM_NEG,  GIMBAL_ROLL_LIM_POS),
    "pitch": (-GIMBAL_PITCH_LIM_NEG, GIMBAL_PITCH_LIM_POS),
}
DEADBAND      = GIMBAL_DEADBAND_DEG
SMOOTH_ALPHA  = GIMBAL_ANGLE_SMOOTH_ALPHA
US_PER_DEG    = GIMBAL_US_PER_DEG
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

    IMU 모드(IMUPLUS 전환 여부)는 main()에서 스레드가 하나도 뜨기 전에 한 번만
    결정적으로 설정한다 — 이 함수 안에서 다시 건드리면 이미 돌고 있는
    sensor_thread와 경쟁 상태가 생기고, 모드 전환 자체가 BNO055 내부 퓨전
    상태를 리셋시켜 그 순간 roll/pitch가 잠깐 튈 수 있기 때문.
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

    def set_servo(pin: int, us: float) -> None:
        lgpio.tx_servo(h, pin, int(us), servo_frequency=50)

    if not MOCK:
        set_servo(PIN_ROLL, NEUTRAL_ROLL)
        set_servo(PIN_PITCH, NEUTRAL_PITCH)
        time.sleep(0.5)

    cmd = {"roll": 0.0, "pitch": 0.0}
    smoothed = {"roll": None, "pitch": None}
    last_log = time.monotonic()

    logger.info("Gimbal loop started (%dHz)", int(1.0 / DT))

    while running[0]:
        loop_start = time.monotonic()

        try:
            with i2c_lock:
                _, roll, pitch = imu.euler

            if roll is None or pitch is None:
                raise ValueError("BNO055 euler not ready yet")

            # roll/pitch에 EMA 스무딩 적용 — 축변환 이전에 걸어야 두 축 노이즈가
            # 45도 변환으로 서로 섞여 증폭되기 전에 억제된다.
            if smoothed["roll"] is None:
                smoothed["roll"], smoothed["pitch"] = roll, pitch
            else:
                smoothed["roll"] = SMOOTH_ALPHA * smoothed["roll"] + (1 - SMOOTH_ALPHA) * roll
                smoothed["pitch"] = SMOOTH_ALPHA * smoothed["pitch"] + (1 - SMOOTH_ALPHA) * pitch
            rf, pf = smoothed["roll"], smoothed["pitch"]

            # 45도 축변환 (짐벌 장착 방향)
            g_roll  = (rf - pf) * 0.7071
            g_pitch = (rf + pf) * 0.7071

            for ax_name, ang in (("roll", g_roll), ("pitch", g_pitch)):
                lo, hi = LIMITS[ax_name]
                target = _clamp(-ang, lo, hi)  # 반대 방향 보상
                diff = target - cmd[ax_name]
                # 데드밴드: 오차가 작으면 아예 움직이지 않아 자잘한 흔들림을 억제.
                step = 0.0 if abs(diff) < DEADBAND else _clamp(diff, -SLEW, SLEW)
                cmd[ax_name] += step

            servo_roll  = NEUTRAL_ROLL  + cmd["roll"]  * US_PER_DEG
            servo_pitch = NEUTRAL_PITCH + cmd["pitch"] * US_PER_DEG

            # 50Hz 루프에서 매 틱 로그는 과하니 약 1초 간격으로만 downsample.
            # mock 여부와 무관하게 항상 남긴다 — 실제 서보 동작 중에도 사후에
            # "그 순간 roll/pitch가 뭐였는지" 추적할 수 있어야 한다.
            if loop_start - last_log > 1.0:
                logger.info("Gimbal: roll=%.2f pitch=%.2f -> cmd_roll=%.2f cmd_pitch=%.2f",
                            roll, pitch, cmd["roll"], cmd["pitch"])
                last_log = loop_start

            if not MOCK:
                set_servo(PIN_ROLL,  servo_roll)
                set_servo(PIN_PITCH, servo_pitch)

        except Exception as e:
            logger.error("Gimbal loop error: %s", e)

        elapsed = time.monotonic() - loop_start
        time.sleep(max(0.0, DT - elapsed))

    # 종료 시 서보 중립 복귀 후 PWM 정지
    if MOCK:
        logger.info("Gimbal (mock): servo neutral return skipped")
    else:
        set_servo(PIN_ROLL,  NEUTRAL_ROLL)
        set_servo(PIN_PITCH, NEUTRAL_PITCH)
        time.sleep(0.5)  # 중립 위치로 복귀할 시간 확보
        set_servo(PIN_ROLL,  0)
        set_servo(PIN_PITCH, 0)
        lgpio.gpio_free(h, PIN_ROLL)
        lgpio.gpio_free(h, PIN_PITCH)
        lgpio.gpiochip_close(h)
    logger.info("Gimbal loop stopped")
