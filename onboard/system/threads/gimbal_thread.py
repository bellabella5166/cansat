# onboard/system/threads/gimbal_thread.py

from __future__ import annotations

import logging
import math
import time
from onboard.system.config import (
    GIMBAL_ALPHA, GIMBAL_SLEW, GIMBAL_LIM,
    GIMBAL_PIN_ROLL, GIMBAL_PIN_PITCH,
    GIMBAL_NEUTRAL_ROLL, GIMBAL_NEUTRAL_PITCH,
    GIMBAL_DT, GIMBAL_BIAS_SAMPLES,
)

logger = logging.getLogger("onboard.gimbal")

# ── 설정 ──────────────────────────────────────────────────────────────────────
ALPHA         = GIMBAL_ALPHA
SLEW          = GIMBAL_SLEW
LIM           = GIMBAL_LIM
PIN_ROLL      = GIMBAL_PIN_ROLL
PIN_PITCH     = GIMBAL_PIN_PITCH
NEUTRAL_ROLL  = GIMBAL_NEUTRAL_ROLL
NEUTRAL_PITCH = GIMBAL_NEUTRAL_PITCH
DT            = GIMBAL_DT
BIAS_SAMPLES  = GIMBAL_BIAS_SAMPLES


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _read_raw(bus, MPU_ADDR: int, i2c_lock) -> tuple:
    """MPU6050에서 가속도/자이로 원시값 읽기.

    같은 IMU를 sensor.py(sensor_thread)도 같은 물리 I2C 버스로 읽으므로,
    스레드 간 충돌을 막기 위해 공유 i2c_lock으로 레지스터 읽기 구간
    전체를 감싼다.
    """
    def read_word(reg):
        h = bus.read_byte_data(MPU_ADDR, reg)
        l = bus.read_byte_data(MPU_ADDR, reg + 1)
        v = (h << 8) + l
        return v - 65536 if v >= 0x8000 else v

    with i2c_lock:
        ax = read_word(0x3B) / 16384.0
        ay = read_word(0x3D) / 16384.0
        az = read_word(0x3F) / 16384.0
        gx = read_word(0x43) / 131.0  # deg/s
        gy = read_word(0x45) / 131.0
    return ax, ay, az, gx, gy


def _calibrate_gyro(bus, MPU_ADDR: int, i2c_lock) -> tuple:
    """부팅 시 자이로 바이어스 측정 (3초간 정지 상태)"""
    logger.info("Gimbal: calibrating gyro bias (3s, keep still)...")
    gx_sum, gy_sum = 0.0, 0.0
    for _ in range(BIAS_SAMPLES):
        _, _, _, gx, gy = _read_raw(bus, MPU_ADDR, i2c_lock)
        gx_sum += gx
        gy_sum += gy
        time.sleep(DT)
    bias_gx = gx_sum / BIAS_SAMPLES
    bias_gy = gy_sum / BIAS_SAMPLES
    logger.info("Gimbal: gyro bias gx=%.4f, gy=%.4f", bias_gx, bias_gy)
    return bias_gx, bias_gy


def gimbal_loop(running: list, i2c_lock) -> None:
    # pigpio는 데몬(pigpiod) 기반이라 Debian trixie부터 apt 저장소에서 빠져
    # 설치가 안 된다 (pip pigpio 클라이언트만 있어도 데몬이 없으면 무용지물).
    # 데몬 없이 커널 gpiochip 캐릭터 디바이스로 직접 동작하는 lgpio로 대체.
    try:
        import smbus2
        import lgpio
    except ImportError as e:
        logger.error("Gimbal: library not found: %s", e)
        return

    MPU_ADDR = 0x68
    bus = smbus2.SMBus(1)
    with i2c_lock:
        bus.write_byte_data(MPU_ADDR, 0x6B, 0)  # 슬립 해제

    try:
        h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_output(h, PIN_ROLL)
        lgpio.gpio_claim_output(h, PIN_PITCH)
    except Exception as e:
        logger.error("Gimbal: lgpio gpiochip open failed: %s", e)
        return

    # 자이로 바이어스 측정
    bias_gx, bias_gy = _calibrate_gyro(bus, MPU_ADDR, i2c_lock)

    # 상보필터 초기값
    roll, pitch = 0.0, 0.0
    cmd = {"roll": 0.0, "pitch": 0.0}

    logger.info("Gimbal loop started (50Hz)")

    while running[0]:
        loop_start = time.monotonic()

        try:
            ax, ay, az, gx, gy = _read_raw(bus, MPU_ADDR, i2c_lock)

            # 자이로 바이어스 제거
            gx -= bias_gx
            gy -= bias_gy

            # 가속도 기반 각도
            roll_acc  = math.degrees(math.atan2(ay, az))
            pitch_acc = math.degrees(math.atan2(-ax, math.sqrt(ay**2 + az**2)))

            # 상보필터
            roll  = ALPHA * (roll  + gx * DT) + (1 - ALPHA) * roll_acc
            pitch = ALPHA * (pitch + gy * DT) + (1 - ALPHA) * pitch_acc

            # 45도 축변환 (짐벌 장착 방향)
            g_roll  = (roll - pitch) * 0.7071
            g_pitch = (roll + pitch) * 0.7071

            # 서보 제어
            for ax_name, ang in (("roll", g_roll), ("pitch", g_pitch)):
                target = _clamp(-ang, -LIM, LIM)  # 반대 방향 보상
                step   = _clamp(target - cmd[ax_name], -SLEW, SLEW)
                cmd[ax_name] += step

            lgpio.tx_servo(h, PIN_ROLL,  int(NEUTRAL_ROLL  + cmd["roll"]  * 10.0))
            lgpio.tx_servo(h, PIN_PITCH, int(NEUTRAL_PITCH + cmd["pitch"] * 10.0))

        except Exception as e:
            logger.error("Gimbal loop error: %s", e)

        elapsed = time.monotonic() - loop_start
        time.sleep(max(0.0, DT-elapsed))

    # 종료 시 서보 중립 복귀 후 PWM 정지
    lgpio.tx_servo(h, PIN_ROLL,  NEUTRAL_ROLL)
    lgpio.tx_servo(h, PIN_PITCH, NEUTRAL_PITCH)
    time.sleep(0.3)  # 중립 위치로 복귀할 시간 확보
    lgpio.tx_servo(h, PIN_ROLL,  0)
    lgpio.tx_servo(h, PIN_PITCH, 0)
    lgpio.gpio_free(h, PIN_ROLL)
    lgpio.gpio_free(h, PIN_PITCH)
    lgpio.gpiochip_close(h)
    logger.info("Gimbal loop stopped")