# onboard/input/i2c_utils.py

from __future__ import annotations

import time


class I2CRetryHelper:
    """
    공유 I2C 버스(IMU/Baro) 읽기 실패에 대한 재시도 + 버스 락업 자동 감지/리셋.

    부품 고장이 아니라 IMU(MPU6050)/Baro(BMP388)가 같은 물리 I2C 버스를
    공유하는 구조상 특성(버스 락업, 접촉 불량, 클럭 스트레칭 충돌)으로
    가끔 읽기가 실패하는 것을 소프트웨어로 완화하기 위한 헬퍼.

    스레드 간 배타 처리는 이 클래스의 책임이 아니다 — 물리 버스를 공유하는
    다른 스레드(예: gimbal_thread)가 있다면, 호출부가 그 스레드와 공유하는
    threading.Lock으로 call() 호출 구간을 감싸야 한다.
    """

    def __init__(self, retry_count: int, retry_delay_s: float,
                 lockup_threshold: int, name: str):
        self._retry_count = retry_count
        self._retry_delay_s = retry_delay_s
        self._lockup_threshold = lockup_threshold
        self._name = name
        self._consecutive_failures = 0

    def call(self, fn, *args, **kwargs):
        """fn(*args, **kwargs) 실행, I2C 오류(OSError) 시 retry_count회까지 재시도."""
        last_exc: Exception | None = None
        for attempt in range(1, self._retry_count + 1):
            try:
                result = fn(*args, **kwargs)
                self._consecutive_failures = 0
                return result
            except OSError as e:
                last_exc = e
                self._consecutive_failures += 1
                print(f"[I2C:{self._name}] read failed (attempt {attempt}/{self._retry_count}, "
                      f"consecutive_failures={self._consecutive_failures}): {e}")

                if self._consecutive_failures >= self._lockup_threshold:
                    self._reset_bus()
                    self._consecutive_failures = 0
                elif attempt < self._retry_count:
                    time.sleep(self._retry_delay_s)

        raise last_exc

    def _reset_bus(self) -> None:
        """
        I2C 버스 소프트 리셋 (SCL 클럭 수동 토글, bit-banging).

        슬레이브가 SDA를 Low로 물고 안 놓는 락업 상태에서 SCL을 9회
        토글해 슬레이브가 진행 중이던 바이트 전송을 강제로 끝내고 버스를
        해제시키는 표준 I2C 복구 절차. 커널 I2C 모듈 재로드보다 가볍다.

        주의: Pi4 실기에서 GPIO(BCM3)↔I2C 커널 드라이버 핀먹스 전환이
        실제로 의도대로 동작하는지는 아직 실측 검증 전 — 추후 조정 예정.

        pigpio는 데몬(pigpiod) 기반이라 Debian trixie부터 apt 저장소에서
        빠져 설치가 안 된다 — 데몬 없이 커널 gpiochip 캐릭터 디바이스로
        직접 동작하는 lgpio를 사용한다.
        """
        reset_time = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[I2C:{self._name}] bus lockup detected "
              f"({self._lockup_threshold} consecutive failures) — resetting bus at {reset_time}")
        try:
            import lgpio
            SCL_BCM = 3  # I2C-1 SCL (Pi4 physical pin 5)

            h = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(h, SCL_BCM, 1)
            for _ in range(9):
                lgpio.gpio_write(h, SCL_BCM, 1)
                time.sleep(0.00001)
                lgpio.gpio_write(h, SCL_BCM, 0)
                time.sleep(0.00001)
            lgpio.gpio_free(h, SCL_BCM)  # 커널 I2C 드라이버에 핀 반환
            lgpio.gpiochip_close(h)
            print(f"[I2C:{self._name}] bus reset complete")
        except Exception as e:
            print(f"[I2C:{self._name}] bus reset failed: {e}")
