"""
짐벌 기계적 리밋(프레임에 닿는 지점) 실측용 스크립트.

test.py(중립값 튜닝)와 동일한 방식으로 키 입력마다 서보를 0.5도씩
움직인다. GIMBAL_NEUTRAL_ROLL/PITCH(실측된 중립값)에서 시작해서 각
방향으로 한 스텝씩 보내다가, 프레임에 닿거나 저항/지지직 소리가
느껴지는 순간 즉시 [q]로 멈추고 그 직전 [c] 값(중립 대비 각도)을
기록한다. roll +/-, pitch +/- 총 4방향을 각각 측정해서
GIMBAL_ROLL_LIM_POS/NEG, GIMBAL_PITCH_LIM_POS/NEG를 정하는 데 쓴다.
"""
import lgpio

from onboard.system.config import (
    GIMBAL_PIN_ROLL, GIMBAL_PIN_PITCH,
    GIMBAL_NEUTRAL_ROLL, GIMBAL_NEUTRAL_PITCH,
)

PIN_ROLL = GIMBAL_PIN_ROLL
PIN_PITCH = GIMBAL_PIN_PITCH

# gimbal_thread.py의 NEUTRAL + cmd * 10.0 매핑과 동일한 기준(10us/deg)
US_PER_DEG = 10.0
STEP = 5  # 0.5deg

roll_us = GIMBAL_NEUTRAL_ROLL
pitch_us = GIMBAL_NEUTRAL_PITCH


def clamp(v, lo=500, hi=2500):
    return max(lo, min(hi, v))


def print_current():
    roll_deg = (roll_us - GIMBAL_NEUTRAL_ROLL) / US_PER_DEG
    pitch_deg = (pitch_us - GIMBAL_NEUTRAL_PITCH) / US_PER_DEG
    print(
        f"Roll:  {roll_us}us ({roll_deg:+.1f}deg from neutral)\n"
        f"Pitch: {pitch_us}us ({pitch_deg:+.1f}deg from neutral)"
    )


def send_servo(h):
    lgpio.tx_servo(h, PIN_ROLL, clamp(roll_us))
    lgpio.tx_servo(h, PIN_PITCH, clamp(pitch_us))
    print_current()


h = None

try:
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(h, PIN_ROLL)
    lgpio.gpio_claim_output(h, PIN_PITCH)

    print("=== Gimbal limit sweep mode ===")
    print("프레임에 닿거나 저항/지지직 소리가 느껴지면 즉시 [q]로 멈추고 각도를 기록하세요.\n")
    send_servo(h)

    while True:
        cmd = input(
            "\n"
            "[z] Roll -0.5deg\n"
            "[x] Roll +0.5deg\n"
            "[v] Pitch -0.5deg\n"
            "[b] Pitch +0.5deg\n"
            "[c] Current value\n"
            "[q] Quit\n"
            "> "
        )

        if cmd == "z":
            roll_us -= STEP
            send_servo(h)

        elif cmd == "x":
            roll_us += STEP
            send_servo(h)

        elif cmd == "v":
            pitch_us -= STEP
            send_servo(h)

        elif cmd == "b":
            pitch_us += STEP
            send_servo(h)

        elif cmd == "c":
            print_current()

        elif cmd == "q":
            break

        else:
            print("Unknown command")

except KeyboardInterrupt:
    pass

finally:
    if h is not None:
        # 종료 시 중립 복귀 후 PWM OFF (test.py와 동일하게 즉시 정지가 아니라
        # 중립으로 돌려놓아야 다음 실행이 항상 같은 기준에서 시작됨)
        lgpio.tx_servo(h, PIN_ROLL, GIMBAL_NEUTRAL_ROLL)
        lgpio.tx_servo(h, PIN_PITCH, GIMBAL_NEUTRAL_PITCH)
        lgpio.gpiochip_close(h)

print("Finished")
