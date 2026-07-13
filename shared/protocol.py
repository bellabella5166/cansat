"""
shared/protocol.py
==================
패킷 인코딩 / 디코딩 / CRC-16 / 스트림 파서.
온보드(Raspberry Pi)와 지상국(노트북) 양쪽에서 동일하게 사용한다.

패킷 구조:
  HEADER(2) │ TYPE(1) │ SEQ(2) │ LENGTH(2) │ PAYLOAD(n) │ CRC16(2)
  고정 오버헤드: 9 bytes
  모든 멀티바이트 값: little-endian

패킷 타입:
  0x01  SENSOR     – GPS/IMU/기압계 데이터 (10 Hz)
  0x02  YOLO_META  – YOLOv8n 탐지 메타데이터 (탐지 발생 시마다)
  0x03  IMG        – 대표 이미지 청크 (1장 선별 후 분할)
  0x04  POWER      – 통신 전력 데이터
  0x10  ACK        – 수신 확인
  0x11  NACK       – 청크 재전송 요청
  0x20  HEARTBEAT  – 생존 신호 (5초 주기)
"""

from __future__ import annotations

import struct
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Generator

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────
HEADER: bytes = b"\xAA\x55"
HEADER_LEN: int = 2
TYPE_LEN: int = 1
SEQ_LEN: int = 2
LENGTH_LEN: int = 2
CRC_LEN: int = 2
FIXED_OVERHEAD: int = HEADER_LEN + TYPE_LEN + SEQ_LEN + LENGTH_LEN + CRC_LEN  # 9

ENDIAN: str = "<"  # little-endian
MAX_PAYLOAD_SIZE: int = 128  # bytes (XBee 스루풋 고려)


class PacketType(IntEnum):
    SENSOR     = 0x01
    YOLO_META  = 0x02
    IMG        = 0x03
    ACK        = 0x10
    NACK       = 0x11
    HEARTBEAT  = 0x20
    POWER      = 0x04


# ── CRC-16/XMODEM ─────────────────────────────────────────────────────────────
def crc16(data: bytes) -> int:
    """CRC-16/XMODEM (poly=0x1021, init=0x0000, refIn=False, refOut=False)"""
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


# ── Packet dataclass ──────────────────────────────────────────────────────────
@dataclass
class Packet:
    ptype:   PacketType
    seq:     int        # uint16, 0~65535 순환
    payload: bytes = field(default=b"")

    def encode(self) -> bytes:
        return encode_packet(self)


# ── Encode ────────────────────────────────────────────────────────────────────
def encode_packet(pkt: Packet) -> bytes:
    if len(pkt.payload) > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"payload size excess: {len(pkt.payload)} > {MAX_PAYLOAD_SIZE}"
        )
    body = (
        HEADER
        + struct.pack(f"{ENDIAN}B",  int(pkt.ptype))
        + struct.pack(f"{ENDIAN}H",  pkt.seq & 0xFFFF)
        + struct.pack(f"{ENDIAN}H",  len(pkt.payload))
        + pkt.payload
    )
    return body + struct.pack(f"{ENDIAN}H", crc16(body))


# ── Decode ────────────────────────────────────────────────────────────────────
def decode_packet(raw: bytes) -> Packet | None:
    """이미 완성된 raw bytes → Packet. CRC 불일치/형식 오류 시 None."""
    if len(raw) < FIXED_OVERHEAD:
        return None
    if not raw.startswith(HEADER):
        return None

    off = HEADER_LEN
    ptype_raw = struct.unpack_from(f"{ENDIAN}B", raw, off)[0];  off += 1
    seq       = struct.unpack_from(f"{ENDIAN}H", raw, off)[0];  off += 2
    length    = struct.unpack_from(f"{ENDIAN}H", raw, off)[0];  off += 2

    if length > MAX_PAYLOAD_SIZE or len(raw) < off + length + CRC_LEN:
        return None

    payload       = raw[off : off + length]
    crc_received  = struct.unpack_from(f"{ENDIAN}H", raw, off + length)[0]
    crc_computed  = crc16(raw[: off + length])

    if crc_received != crc_computed:
        logger.warning("CRC Mismatch: recv=0x%04X calc=0x%04X", crc_received, crc_computed)
        return None

    try:
        ptype = PacketType(ptype_raw)
    except ValueError:
        logger.warning("unknown packet type: 0x%02X", ptype_raw)
        return None

    return Packet(ptype=ptype, seq=seq, payload=payload)


# ── 스트림 파서 ───────────────────────────────────────────────────────────────
class PacketParser:
    """
    XBee 시리얼 바이트 스트림 → Packet 제너레이터.
    부분 수신이나 노이즈 바이트에서 자동으로 재동기화한다.

    사용 예:
        parser = PacketParser()
        for pkt in parser.feed(received_bytes):
            handle(pkt)
    """

    def __init__(self) -> None:
        self._buf: bytearray = bytearray()

    def feed(self, data: bytes) -> Generator[Packet, None, None]:
        self._buf.extend(data)

        while True:
            idx = self._buf.find(HEADER)
            if idx == -1:
                self._buf = self._buf[-1:]  # 마지막 1바이트 보존 (헤더 경계 대비)
                break
            if idx > 0:
                del self._buf[:idx]

            # 최소 길이 확인
            min_needed = HEADER_LEN + TYPE_LEN + SEQ_LEN + LENGTH_LEN
            if len(self._buf) < min_needed:
                break

            length_off = HEADER_LEN + TYPE_LEN + SEQ_LEN
            length = struct.unpack_from(f"{ENDIAN}H", self._buf, length_off)[0]

            if length > MAX_PAYLOAD_SIZE:
                del self._buf[:HEADER_LEN]  # 재동기화
                continue

            total = FIXED_OVERHEAD + length
            if len(self._buf) < total:
                break

            raw = bytes(self._buf[:total])
            del self._buf[:total]

            pkt = decode_packet(raw)
            if pkt is not None:
                yield pkt

    def reset(self) -> None:
        self._buf.clear()
