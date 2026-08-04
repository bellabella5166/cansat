#!/usr/bin/env python3
"""
servo_limit_test.py

짐벌의 실제 기계적 한계를 측정하기 위한 테스트 프로그램.

조작법
-----------------------------------
1 : Roll -
2 : Roll +

3 : Pitch -
4 : Pitch +

r : Roll 0°
t : Pitch 0°
c : 둘 다 0°

q : 종료
"""

import time

import lgpio

from onboard.system.config import (
    GIMBAL_PIN_ROLL,
    GIMBAL_PIN_PITCH,
    GIMBAL_NEUTRAL_ROLL,
    GIMBAL_NEUTRAL_PITCH,
)

PIN_ROLL = GIMBAL_PIN_ROLL
PIN_PITCH = GIMBAL_PIN_PITCH

NEUTRAL_ROLL = GIMBAL_NEUTRAL_ROLL
NEUTRAL_PITCH = GIMBAL_NEUTRAL_PITCH

US_PER_DEG = 10        # 현재 gimbal_thread와 동일
STEP_DEG = 1           # 한 번에 1도
MIN_US = 500
MAX_US = 2500


def pulse(center, deg):
    us = int(center + deg * US_PER_DEG)
    return max(MIN_US, min(MAX_US, us))


def print_state(r, p):
    print("--------------------------------")
    print(f"Roll : {r:+d}°")
    print(f"Pitch: {p:+d}°")
    print(f"Roll pulse : {pulse(NEUTRAL_ROLL, r)} us")
    print(f"Pitch pulse: {pulse(NEUTRAL_PITCH, p)} us")
    print("--------------------------------")


h = lgpio.gpiochip_open(0)

lgpio.gpio_claim_output(h, PIN_ROLL)
lgpio.gpio_claim_output(h, PIN_PITCH)

roll_deg = 0
pitch_deg = 0

try:

    lgpio.tx_servo(h, PIN_ROLL, pulse(NEUTRAL_ROLL, 0))
    lgpio.tx_servo(h, PIN_PITCH, pulse(NEUTRAL_PITCH, 0))

    print_state(roll_deg, pitch_deg)

    while True:

        cmd = input(
            "[1]-Roll  [2]+Roll  [3]-Pitch  [4]+Pitch  "
            "[r]Roll0 [t]Pitch0 [c]Center [q]Quit > "
        ).strip().lower()

        if cmd == "1":
            roll_deg -= STEP_DEG

        elif cmd == "2":
            roll_deg += STEP_DEG

        elif cmd == "3":
            pitch_deg -= STEP_DEG

        elif cmd == "4":
            pitch_deg += STEP_DEG

        elif cmd == "r":
            roll_deg = 0

        elif cmd == "t":
            pitch_deg = 0

        elif cmd == "c":
            roll_deg = 0
            pitch_deg = 0

        elif cmd == "q":
            break

        else:
            continue

        lgpio.tx_servo(h, PIN_ROLL,
                       pulse(NEUTRAL_ROLL, roll_deg))

        lgpio.tx_servo(h, PIN_PITCH,
                       pulse(NEUTRAL_PITCH, pitch_deg))

        print_state(roll_deg, pitch_deg)

finally:

    lgpio.tx_servo(h, PIN_ROLL, NEUTRAL_ROLL)
    lgpio.tx_servo(h, PIN_PITCH, NEUTRAL_PITCH)

    time.sleep(0.5)

    lgpio.tx_servo(h, PIN_ROLL, 0)
    lgpio.tx_servo(h, PIN_PITCH, 0)

    lgpio.gpio_free(h, PIN_ROLL)
    lgpio.gpio_free(h, PIN_PITCH)
    lgpio.gpiochip_close(h)

    print("Finished.")