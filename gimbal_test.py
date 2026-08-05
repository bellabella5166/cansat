import time
import sys

import board
import busio
import adafruit_bno055
import lgpio

USE_IMU_MODE = True
PIN_ROLL = 13
PIN_PITCH = 18
GPIO_CHIP = 0
NEUTRAL = {"roll": 1545, "pitch": 1370}
LIM_DEG = 20.0
SLEW_DEG_PER_TICK = 2.0
DEADBAND_DEG = 1.0
ANGLE_SMOOTH_ALPHA = 0.85
LOOP_HZ = 50
US_PER_DEG = 10.0
INVERT_ROLL = False
INVERT_PITCH = False

print("BNO055 연결 중...")
i2c = busio.I2C(board.SCL, board.SDA)
sensor = adafruit_bno055.BNO055_I2C(i2c)
sensor.mode = adafruit_bno055.IMUPLUS_MODE if USE_IMU_MODE else adafruit_bno055.NDOF_MODE
print("모드:", "IMUPLUS" if USE_IMU_MODE else "NDOF")
time.sleep(1.0)

h = lgpio.gpiochip_open(GPIO_CHIP)
lgpio.gpio_claim_output(h, PIN_ROLL)
lgpio.gpio_claim_output(h, PIN_PITCH)
print(f"GPIO{PIN_ROLL}, GPIO{PIN_PITCH} 클레임 완료 (계속 유지)")

def set_servo(pin, us):
    lgpio.tx_servo(h, pin, int(us), servo_frequency=50)

set_servo(PIN_ROLL, NEUTRAL["roll"])
set_servo(PIN_PITCH, NEUTRAL["pitch"])
time.sleep(0.5)

cmd = {"roll": 0.0, "pitch": 0.0}
smoothed = {"roll": None, "pitch": None}
dt = 1.0 / LOOP_HZ

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

sys_c, gyro_c, accel_c, mag_c = sensor.calibration_status
print(f"[캘리브레이션] sys={sys_c} gyro={gyro_c} accel={accel_c} mag={mag_c}")

last_print = time.time()
try:
    while True:
        t0 = time.time()
        euler = sensor.euler
        if euler is None or euler[1] is None or euler[2] is None:
            time.sleep(dt); continue

        _, roll, pitch = euler
        if smoothed["roll"] is None:
            smoothed["roll"], smoothed["pitch"] = roll, pitch
        else:
            smoothed["roll"] = ANGLE_SMOOTH_ALPHA*smoothed["roll"] + (1-ANGLE_SMOOTH_ALPHA)*roll
            smoothed["pitch"] = ANGLE_SMOOTH_ALPHA*smoothed["pitch"] + (1-ANGLE_SMOOTH_ALPHA)*pitch
        rf, pf = smoothed["roll"], smoothed["pitch"]

        g_roll = (rf - pf) * 0.7071
        g_pitch = (rf + pf) * 0.7071
        if INVERT_ROLL: g_roll = -g_roll
        if INVERT_PITCH: g_pitch = -g_pitch

        for axis, ang in (("roll", g_roll), ("pitch", g_pitch)):
            target = clamp(-ang, -LIM_DEG, LIM_DEG)
            diff = target - cmd[axis]
            step = 0.0 if abs(diff) < DEADBAND_DEG else clamp(diff, -SLEW_DEG_PER_TICK, SLEW_DEG_PER_TICK)
            cmd[axis] += step
            pin = PIN_ROLL if axis=="roll" else PIN_PITCH
            set_servo(pin, NEUTRAL[axis] + cmd[axis]*US_PER_DEG)

        if time.time() - last_print > 1.0:
            print(f"roll={roll:6.1f} pitch={pitch:6.1f} -> cmd_roll={cmd['roll']:6.1f} cmd_pitch={cmd['pitch']:6.1f}")
            last_print = time.time()

        time.sleep(max(0.0, dt - (time.time()-t0)))

except KeyboardInterrupt:
    print("\n종료 중...")
finally:
    set_servo(PIN_ROLL, NEUTRAL["roll"])
    set_servo(PIN_PITCH, NEUTRAL["pitch"])
    time.sleep(0.5)
    set_servo(PIN_ROLL, 0)
    set_servo(PIN_PITCH, 0)
    lgpio.gpiochip_close(h)
    print("완료.")
