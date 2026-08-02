"""
shared/serial_wrapper.py
=========================
pyserial 래퍼. onboard(main.py)와 지상국(ground_receiver.py) 양쪽에서
공용으로 import한다.
"""

from __future__ import annotations
import logging
import time

logger = logging.getLogger(__name__)


class XBeeSerial:
    def __init__(self, port: str, baudrate: int = 9600,
                 retry_count: int = 5, retry_delay_s: float = 1.0) -> None:
        try:
            import serial  # type: ignore
        except ImportError:
            raise RuntimeError("pyserial 미설치: pip install pyserial")

        # 포트가 아직 OS에 완전히 잡히기 전(부팅 직후, USB/UART 재연결 직후)에
        # main.py가 먼저 열려고 시도하면 한 번에 실패할 수 있다 — 몇 번
        # 재시도해서 그런 타이밍 문제로 통신 전체가 시작도 못 하는 걸 막는다.
        last_exc = None
        for attempt in range(1, retry_count + 1):
            try:
                # write_timeout이 없으면(기본 None) write()가 무한 대기할 수 있음 —
                # 링크가 9600bps 한계치 근처로 포화 상태일 때 RF 순간 간섭 등으로
                # 송신 버퍼가 밀리면 메인 송신 루프 자체가 영원히 멈춰서 SENSOR뿐
                # 아니라 HEARTBEAT까지 포함한 전체 통신이 끊기는 원인이 됨.
                self._ser = serial.Serial(port=port, baudrate=baudrate, timeout=1.0, write_timeout=2.0)
                logger.info("시리얼 열림: %s @ %d baud (attempt %d/%d)", port, baudrate, attempt, retry_count)
                return
            except Exception as e:
                last_exc = e
                logger.warning("시리얼 열기 실패 (attempt %d/%d): %s", attempt, retry_count, e)
                if attempt < retry_count:
                    time.sleep(retry_delay_s)
        raise RuntimeError(f"시리얼 포트 열기 최종 실패 ({retry_count}회 시도, port={port}): {last_exc}")

    def read_available(self) -> bytes:
        w = self._ser.in_waiting
        return self._ser.read(w) if w else b""

    def write(self, data: bytes) -> int:
        return self._ser.write(data)

    def close(self):
        if self._ser.is_open:
            self._ser.close()
            logger.info("시리얼 닫힘")

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
