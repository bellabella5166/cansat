"""
ground_station/serial_wrapper.py
==================================
pyserial 래퍼. ground_receiver.py에서 import한다.
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class XBeeSerial:
    def __init__(self, port: str, baudrate: int = 9600) -> None:
        try:
            import serial  # type: ignore
        except ImportError:
            raise RuntimeError("pyserial 미설치: pip install pyserial")
        self._ser = serial.Serial(port=port, baudrate=baudrate, timeout=1.0)
        logger.info("시리얼 열림: %s @ %d baud", port, baudrate)

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
