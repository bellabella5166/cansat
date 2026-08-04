# onboard/system/threads/gimbal_thread.py

from __future__ import annotations

import logging
import time
from onboard.system.config import (
    GIMBAL_MOCK,
    GIMBAL_SLEW, GIMBAL_FILTER_ALPHA, GIMBAL_REPOSITION_INTERVAL_S,
    GIMBAL_ROLL_DEADBAND, GIMBAL_PITCH_DEADBAND,
    GIMBAL_ROLL_LIM_POS, GIMBAL_ROLL_LIM_NEG,
    GIMBAL_PITCH_LIM_POS, GIMBAL_PITCH_LIM_NEG,
    GIMBAL_PIN_ROLL, GIMBAL_PIN_PITCH,
    GIMBAL_NEUTRAL_ROLL, GIMBAL_NEUTRAL_PITCH,
    GIMBAL_DT,
)

logger = logging.getLogger("onboard.gimbal")

# ── 설정 ──────────────────────────────────────────────────────────────────────
MOCK          = GIMBAL_MOCK
SLEW          = GIMBAL_SLEW
FILTER_ALPHA  = GIMBAL_FILTER_ALPHA
DEADBANDS = {
    "roll":  GIMBAL_ROLL_DEADBAND,
    "pitch": GIMBAL_PITCH_DEADBAND,
}
# 롤/피치를 동시에 극단으로 구동해도 안전하다고 실측 검증된 조합 기준 리밋.
# 두 축 모두 독립적인 (lo, hi) 대신, 축별로 비대칭 범위를 가짐 — 상세 근거는 config.py 참고.
LIMITS = {
    "roll":  (-GIMBAL_ROLL_LIM_NEG,  GIMBAL_ROLL_LIM_POS),
    "pitch": (-GIMBAL_PITCH_LIM_NEG, GIMBAL_PITCH_LIM_POS),
}
PIN_ROLL      = GIMBAL_PIN_ROLL
PIN_PITCH     = GIMBAL_PIN_PITCH
NEUTRAL_ROLL  = GIMBAL_NEUTRAL_ROLL
NEUTRAL_PITCH = GIMBAL_NEUTRAL_PITCH
DT            = GIMBAL_DT
# IMU 읽기/필터/PWM 신호 유지는 계속 매 틱(50Hz) 돌지만, 목표 재계산(재조준)은
# 이 틱 수마다 한 번만 한다 — CAMERA_FPS=1이라 그보다 빠르게 재조준할 이유가
# 없고, MG90류 서보를 "계속 미세 추적"이 아니라 "가끔 굵직하게 재조준"하는
# 용도로 써야 떨림이 줄어든다는 게 실측으로 확인됨.
REPOSITION_TICKS = max(1, round(GIMBAL_REPOSITION_INTERVAL_S / DT))


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
    filt = {"roll": 0.0, "pitch": 0.0}
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

            # 실측 결과 PIN_ROLL(물리 커넥터)이 실제로는 pitch 방향에 반응하고
            # PIN_PITCH가 roll 방향에 반응함 — 핀/중립값/리밋은 실측 기반이라
            # 그대로 두고, 여기서 어느 신호를 어느 축 슬롯에 넣을지만 맞바꿔서 보정.
            raw_ang = {"roll": g_pitch, "pitch": g_roll}

            # 저역통과(EMA) 필터 — target 자체를 BNO055 노이즈로부터 미리 스무딩.
            # 데드밴드(아래)는 "언제 멈출지"를 다루는 별개 계층이고, 이건 그
            # 이전 단계에서 목표값 자체가 떨리는 걸 줄인다.
            for ax_name in ("roll", "pitch"):
                filt[ax_name] = FILTER_ALPHA * filt[ax_name] + (1 - FILTER_ALPHA) * raw_ang[ax_name]

            # 서보 제어 — 재조준 판단은 REPOSITION_TICKS(기본 1초)마다 한 번만.
            # 그 사이엔 cmd를 그대로 유지한 채 아래에서 PWM만 계속 재전송한다.
            if tick == 1 or tick % REPOSITION_TICKS == 0:
                for ax_name in ("roll", "pitch"):
                    lo, hi = LIMITS[ax_name]
                    target = _clamp(filt[ax_name], lo, hi)  # 실측 결과 반전 없이 그대로 써야 방향이 맞음
                    error  = target - cmd[ax_name]
                    deadband = DEADBANDS[ax_name]

                    if abs(error) < deadband:
                        step = 0
                    else:
                        step = _clamp(error, -SLEW, SLEW)

                    cmd[ax_name] += step

            servo_roll  = round(NEUTRAL_ROLL  + cmd["roll"]  * 10.0)
            servo_pitch = round(NEUTRAL_PITCH + cmd["pitch"] * 10.0)

            # 50Hz 루프에서 매 틱 로그는 과하니 약 1초 간격으로만 downsample.
            # mock 여부와 무관하게 항상 남긴다 — 실제 서보 동작 중에도 사후에
            # "그 순간 roll/pitch가 뭐였는지" 추적할 수 있어야 한다.
            if tick % 50 == 0:
                logger.info("Gimbal: roll=%.2f pitch=%.2f -> servo_roll=%d servo_pitch=%d",
                            g_roll, g_pitch, servo_roll, servo_pitch)

            if not MOCK:
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
