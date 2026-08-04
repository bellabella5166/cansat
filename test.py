import lgpio
import time

from onboard.system.config import (
    GIMBAL_PIN_ROLL,
    GIMBAL_PIN_PITCH,
)


PIN_ROLL = GIMBAL_PIN_ROLL
PIN_PITCH = GIMBAL_PIN_PITCH


# 시작 중립값
neutral_roll = 1500
neutral_pitch = 1500


# 조정 단위
STEP = 5


def clamp(v, lo=500, hi=2500):
    return max(lo, min(hi, v))


def send_servo(h):
    roll_pwm = clamp(neutral_roll)
    pitch_pwm = clamp(neutral_pitch)

    lgpio.tx_servo(
        h,
        PIN_ROLL,
        roll_pwm
    )

    lgpio.tx_servo(
        h,
        PIN_PITCH,
        pitch_pwm
    )

    print(
        f"Roll PWM={roll_pwm}us, "
        f"Pitch PWM={pitch_pwm}us"
    )


h = None

try:
    h = lgpio.gpiochip_open(0)

    lgpio.gpio_claim_output(
        h,
        PIN_ROLL
    )

    lgpio.gpio_claim_output(
        h,
        PIN_PITCH
    )


    print("=== Neutral tuning mode ===")

    send_servo(h)


    while True:

        cmd = input(
            "\n"
            "[z] Roll PWM -5us\n"
            "[x] Roll PWM +5us\n"
            "[v] Pitch PWM -5us\n"
            "[b] Pitch PWM +5us\n"
            "[c] Current value\n"
            "[q] Quit\n"
            "> "
        )


        if cmd == "z":
            neutral_roll -= STEP
            send_servo(h)


        elif cmd == "x":
            neutral_roll += STEP
            send_servo(h)


        elif cmd == "v":
            neutral_pitch -= STEP
            send_servo(h)


        elif cmd == "b":
            neutral_pitch += STEP
            send_servo(h)


        elif cmd == "c":
            print(
                f"Current:\n"
                f"Roll={neutral_roll}us\n"
                f"Pitch={neutral_pitch}us"
            )


        elif cmd == "q":
            break


        else:
            print("Unknown command")


except KeyboardInterrupt:
    pass


finally:

    if h is not None:

        # 종료 시 현재 중립 위치 유지 후 PWM OFF
        lgpio.tx_servo(
            h,
            PIN_ROLL,
            0
        )

        lgpio.tx_servo(
            h,
            PIN_PITCH,
            0
        )

        lgpio.gpiochip_close(h)


print("Finished")