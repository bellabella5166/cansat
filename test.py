import lgpio
import time

from onboard.system.config import (
    GIMBAL_PIN_ROLL,
    GIMBAL_PIN_PITCH,
)


# ==============================
# Servo 설정
# ==============================

PIN_ROLL = GIMBAL_PIN_ROLL
PIN_PITCH = GIMBAL_PIN_PITCH

# 초기 중립 PWM
NEUTRAL_ROLL = 1500
NEUTRAL_PITCH = 1500

# 1도당 PWM 변화량
US_PER_DEG = 10

# 중립 튜닝 step
NEUTRAL_STEP = 5


# 안전 범위
MIN_US = 500
MAX_US = 2500


# 현재 각도
roll_deg = 0
pitch_deg = 0


# ==============================
# 함수
# ==============================

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def angle_to_pwm(neutral, angle):
    pwm = neutral + angle * US_PER_DEG
    return int(clamp(pwm, MIN_US, MAX_US))


def send_servo(h):
    roll_pwm = angle_to_pwm(
        NEUTRAL_ROLL,
        roll_deg
    )

    pitch_pwm = angle_to_pwm(
        NEUTRAL_PITCH,
        pitch_deg
    )

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
        f"Roll={roll_deg:+d}° "
        f"(PWM {roll_pwm}us), "
        f"Pitch={pitch_deg:+d}° "
        f"(PWM {pitch_pwm}us)"
    )


# ==============================
# Main
# ==============================

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

    print("Servo test start")

    send_servo(h)


    while True:

        cmd = input(
            "\n"
            "[1]-Roll  [2]+Roll  "
            "[3]-Pitch [4]+Pitch\n"
            "[r]Roll0  [t]Pitch0 "
            "[c]Center\n"
            "[z]Roll neutral- "
            "[x]Roll neutral+\n"
            "[v]Pitch neutral- "
            "[b]Pitch neutral+\n"
            "[q]Quit\n"
            "> "
        )


        # ----------------------
        # 각도 이동
        # ----------------------

        if cmd == "1":
            roll_deg -= 1

        elif cmd == "2":
            roll_deg += 1

        elif cmd == "3":
            pitch_deg -= 1

        elif cmd == "4":
            pitch_deg += 1


        # ----------------------
        # 각도 초기화
        # ----------------------

        elif cmd == "r":
            roll_deg = 0

        elif cmd == "t":
            pitch_deg = 0

        elif cmd == "c":
            roll_deg = 0
            pitch_deg = 0


        # ----------------------
        # 중립 PWM 튜닝
        # ----------------------

        elif cmd == "z":
            NEUTRAL_ROLL -= NEUTRAL_STEP
            print(
                "NEUTRAL_ROLL =",
                NEUTRAL_ROLL
            )

        elif cmd == "x":
            NEUTRAL_ROLL += NEUTRAL_STEP
            print(
                "NEUTRAL_ROLL =",
                NEUTRAL_ROLL
            )


        elif cmd == "v":
            NEUTRAL_PITCH -= NEUTRAL_STEP
            print(
                "NEUTRAL_PITCH =",
                NEUTRAL_PITCH
            )

        elif cmd == "b":
            NEUTRAL_PITCH += NEUTRAL_STEP
            print(
                "NEUTRAL_PITCH =",
                NEUTRAL_PITCH
            )


        # ----------------------
        # 종료
        # ----------------------

        elif cmd == "q":
            break

        else:
            print("Unknown command")


        send_servo(h)



except KeyboardInterrupt:
    print("\nInterrupted")


finally:

    if h is not None:

        # 중립 복귀
        lgpio.tx_servo(
            h,
            PIN_ROLL,
            NEUTRAL_ROLL
        )

        lgpio.tx_servo(
            h,
            PIN_PITCH,
            NEUTRAL_PITCH
        )

        time.sleep(0.3)

        # PWM OFF
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

    print("Servo test finished")