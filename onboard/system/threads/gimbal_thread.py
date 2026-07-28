# onboard/system/threads/gimbal_thread.py

from __future__ import annotations

import logging
import math
import time
from onboard.system.config import (
    GIMBAL_ALPHA, GIMBAL_SLEW, GIMBAL_LIM,
    GIMBAL_PIN_ROLL, GIMBAL_PIN_PITCH,
    GIMBAL_NEUTRAL_ROLL, GIMBAL_NEUTRAL_PITCH,
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


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _read_raw(bus, MPU_ADDR: int) -> tuple:
    """MPU6050에서 가속도/자이로 원시값 읽기"""
    def read_word(reg):
        h = bus.read_byte_data(MPU_ADDR, reg)
        l = bus.read_byte_data(MPU_ADDR, reg + 1)
        v = (h << 8) + l
        return v - 65536 if v >= 0x8000 else v

    ax = read_word(0x3B) / 16384.0
    ay = read_word(0x3D) / 16384.0
    az = read_word(0x3F) / 16384.0
    gx = read_word(0x43) / 131.0  # deg/s
    gy = read_word(0x45) / 131.0
    return ax, ay, az, gx, gy


def _calibrate_gyro(bus, MPU_ADDR: int) -> tuple:
    """부팅 시 자이로 바이어스 측정 (3초간 정지 상태)"""
    logger.info("Gimbal: calibrating gyro bias (3s, keep still)...")
    gx_sum, gy_sum = 0.0, 0.0
    for _ in range(BIAS_SAMPLES):
        _, _, _, gx, gy = _read_raw(bus, MPU_ADDR)
        gx_sum += gx
        gy_sum += gy
        time.sleep(DT)
    bias_gx = gx_sum / BIAS_SAMPLES
    bias_gy = gy_sum / BIAS_SAMPLES
    logger.info("Gimbal: gyro bias gx=%.4f, gy=%.4f", bias_gx, bias_gy)
    return bias_gx, bias_gy


def gimbal_loop(running: list) -> None:
    try:
        import smbus2
        import pigpio
    except ImportError as e:
        logger.error("Gimbal: library not found: %s", e)
        return

    MPU_ADDR = 0x68
    bus = smbus2.SMBus(1)
    bus.write_byte_data(MPU_ADDR, 0x6B, 0)  # 슬립 해제

    pi = pigpio.pi()
    if not pi.connected:
        logger.error("Gimbal: pigpio daemon not running")
        return

    # 자이로 바이어스 측정
    bias_gx, bias_gy = _calibrate_gyro(bus, MPU_ADDR)

    # 상보필터 초기값
    roll, pitch = 0.0, 0.0
    cmd = {"roll": 0.0, "pitch": 0.0}

    logger.info("Gimbal loop started (50Hz)")

    while running[0]:
        loop_start = time.monotonic()

        try:
            ax, ay, az, gx, gy = _read_raw(bus, MPU_ADDR)

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

            pi.set_servo_pulsewidth(PIN_ROLL,  NEUTRAL_ROLL  + cmd["roll"]  * 10.0)
            pi.set_servo_pulsewidth(PIN_PITCH, NEUTRAL_PITCH + cmd["pitch"] * 10.0)

        except Exception as e:
            logger.error("Gimbal loop error: %s", e)

        elapsed = time.monotonic() - loop_start
        time.sleep(max(0.0, DT-elapsed))

    # 종료 시 서보 중립 복귀
    pi.set_servo_pulsewidth(PIN_ROLL,  NEUTRAL_ROLL)
    pi.set_servo_pulsewidth(PIN_PITCH, NEUTRAL_PITCH)
    pi.stop()
    logger.info("Gimbal loop stopped")