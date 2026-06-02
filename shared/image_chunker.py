"""
shared/image_chunker.py
=======================
대표 이미지 1장을 320×240 JPEG로 축소한 뒤 청크로 분할한다.
지상국에서 청크를 모아 JPEG를 복원한다.

IMG 패킷 PAYLOAD 구조:
  image_id     : uint16 (2)   이미지 식별자
  chunk_id     : uint16 (2)   0-based 청크 번호
  total_chunks : uint16 (2)   전체 청크 수
  data         : bytes  (n)   JPEG 조각 (최대 IMAGE_CHUNK_SIZE bytes)
  청크 헤더 오버헤드: 6 bytes
"""

from __future__ import annotations

import io
import logging
import struct
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── 설정값 (config.py 대신 여기서 직접 관리) ──────────────────────────────────
IMAGE_WIDTH:  int = 320
IMAGE_HEIGHT: int = 240
IMAGE_QUALITY: int = 75          # JPEG 품질 (0~95)
IMAGE_CHUNK_SIZE: int = 110      # 청크당 데이터 bytes (패킷 오버헤드 고려)
IMAGE_REASSEMBLY_TIMEOUT_SEC: int = 30

# ── 청크 헤더 ─────────────────────────────────────────────────────────────────
_CHUNK_HDR_FMT  = "<HHH"   # image_id, chunk_id, total_chunks
_CHUNK_HDR_SIZE = struct.calcsize(_CHUNK_HDR_FMT)  # 6 bytes


# ── 온보드 (Raspberry Pi) 측 ──────────────────────────────────────────────────
def resize_jpeg(raw_bytes: bytes) -> bytes:
    """임의 이미지 bytes → 320×240 JPEG bytes (Pillow 필요)."""
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        raise RuntimeError("Pillow 미설치: pip install Pillow")
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    img = img.resize((IMAGE_WIDTH, IMAGE_HEIGHT), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=IMAGE_QUALITY)
    return buf.getvalue()


def split_into_chunks(jpeg_bytes: bytes, image_id: int) -> list[bytes]:
    """JPEG bytes → 청크 payload 리스트 (각 원소를 Packet.payload로 사용)."""
    size = IMAGE_CHUNK_SIZE
    total = (len(jpeg_bytes) + size - 1) // size
    chunks = []
    for i in range(total):
        data   = jpeg_bytes[i * size : (i + 1) * size]
        header = struct.pack(_CHUNK_HDR_FMT, image_id & 0xFFFF, i, total)
        chunks.append(header + data)
    logger.debug("image_id=%d → %d 청크 (JPEG %d bytes)", image_id, total, len(jpeg_bytes))
    return chunks


def prepare_chunks(raw_bytes: bytes, image_id: int) -> list[bytes]:
    """편의 함수: resize → split."""
    return split_into_chunks(resize_jpeg(raw_bytes), image_id)


# ── 지상국 측 ─────────────────────────────────────────────────────────────────
def parse_chunk_payload(payload: bytes) -> tuple[int, int, int, bytes]:
    """IMG 패킷 payload → (image_id, chunk_id, total_chunks, data)."""
    if len(payload) < _CHUNK_HDR_SIZE:
        raise ValueError(f"청크 payload 너무 짧음: {len(payload)}")
    image_id, chunk_id, total_chunks = struct.unpack_from(_CHUNK_HDR_FMT, payload)
    return image_id, chunk_id, total_chunks, payload[_CHUNK_HDR_SIZE:]


@dataclass
class ImageReassembler:
    """
    image_id별로 청크를 수집하고, 완성 시 JPEG bytes를 반환한다.
    timeout 초과 시 미완성 이미지를 폐기하고 NACK 목록을 반환한다.
    """
    _bufs:       dict[int, dict[int, bytes]] = field(default_factory=dict)
    _totals:     dict[int, int]              = field(default_factory=dict)
    _first_seen: dict[int, float]            = field(default_factory=dict)

    def feed(self, image_id: int, chunk_id: int, total: int, data: bytes) -> bytes | None:
        """청크 추가. 모든 청크가 모이면 JPEG bytes 반환, 미완성 시 None."""
        if image_id not in self._bufs:
            self._bufs[image_id]       = {}
            self._totals[image_id]     = total
            self._first_seen[image_id] = time.monotonic()
        self._bufs[image_id][chunk_id] = data
        received = len(self._bufs[image_id])
        logger.debug("image_id=%d chunk %d/%d (%d/%d 수신)",
                     image_id, chunk_id, total - 1, received, total)
        if received == total:
            return self._assemble(image_id)
        return None

    def _assemble(self, image_id: int) -> bytes:
        chunks = self._bufs.pop(image_id)
        self._totals.pop(image_id, None)
        self._first_seen.pop(image_id, None)
        jpeg = b"".join(chunks[i] for i in range(len(chunks)))
        logger.info("image_id=%d 재조립 완료 (%d bytes)", image_id, len(jpeg))
        return jpeg

    def missing(self, image_id: int) -> list[int]:
        if image_id not in self._bufs:
            return []
        total    = self._totals.get(image_id, 0)
        received = set(self._bufs[image_id])
        return [i for i in range(total) if i not in received]

    def expire(self) -> list[tuple[int, list[int]]]:
        """timeout된 image_id → (id, missing_chunks) 리스트 반환 후 버퍼 삭제."""
        now     = time.monotonic()
        expired = []
        for img_id, first in list(self._first_seen.items()):
            if now - first > IMAGE_REASSEMBLY_TIMEOUT_SEC:
                miss = self.missing(img_id)
                logger.warning("image_id=%d 타임아웃, 누락 청크: %s", img_id, miss)
                expired.append((img_id, miss))
                for d in (self._bufs, self._totals, self._first_seen):
                    d.pop(img_id, None)
        return expired

    def active_ids(self) -> list[int]:
        return list(self._bufs)
