"""
shared/image_chunker.py
=======================
대표 이미지 1장을 160×120 JPEG로 축소한 뒤 청크로 분할한다.
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

from protocol import MAX_PAYLOAD_SIZE

logger = logging.getLogger(__name__)

# ── 설정값 (config.py 대신 여기서 직접 관리) ──────────────────────────────────
IMAGE_WIDTH:  int = 160
IMAGE_HEIGHT: int = 120
IMAGE_QUALITY: int = 75          # JPEG 품질 (0~95)
IMAGE_CHUNK_SIZE: int = 110      # 청크당 데이터 bytes (패킷 오버헤드 고려)

# ── 지상국 NACK 재요청 정책 ───────────────────────────────────────────────────
# 마지막으로 "새" 청크(처음 보는 chunk_id)를 받은 시점부터 이만큼 진행이 없으면
# 재요청(NACK) 대상으로 본다 — 이미지당 최대 MAX_NACK_RETRY회까지.
NACK_INACTIVITY_SEC: float = 15.0
MAX_NACK_RETRY: int = 5
# 재요청을 다 써버린(MAX_NACK_RETRY회) 뒤에도 NACK_INACTIVITY_SEC만큼 더 진행이
# 없거나, 첫 청크 수신 후 이 시간이 지나면(온보드 쪽 청크 캐시도 이 시점이면
# 이미 비웠을 가능성이 높음) 포기하고 버퍼를 삭제하는 절대 상한선.
IMAGE_REASSEMBLY_TIMEOUT_SEC: float = 300.0

# NACK 패킷 하나(MAX_PAYLOAD_SIZE)에 실을 수 있는 최대 누락 청크 번호 개수.
# NACK payload = image_id(2) + count(2) + chunk_id(2)*N
_NACK_HDR_SIZE = 4
MAX_MISSING_PER_NACK: int = (MAX_PAYLOAD_SIZE - _NACK_HDR_SIZE) // 2

# ── 청크 헤더 ─────────────────────────────────────────────────────────────────
_CHUNK_HDR_FMT  = "<HHH"   # image_id, chunk_id, total_chunks
_CHUNK_HDR_SIZE = struct.calcsize(_CHUNK_HDR_FMT)  # 6 bytes


# ── 온보드 (Raspberry Pi) 측 ──────────────────────────────────────────────────
def resize_jpeg(raw_bytes: bytes) -> bytes:
    """임의 이미지 bytes(이미 JPEG로 인코딩된 것) → 리사이즈된 JPEG bytes (Pillow 필요).

    입력이 이미 JPEG라 여기서 디코드→재인코드가 한 번 더 일어난다 — 원본 배열을
    바로 가지고 있다면 이중 압축을 피하기 위해 resize_and_encode()를 대신 써야 한다.
    """
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        raise RuntimeError("Pillow 미설치: pip install Pillow")
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    img = img.resize((IMAGE_WIDTH, IMAGE_HEIGHT), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=IMAGE_QUALITY)
    return buf.getvalue()


def resize_and_encode(image) -> bytes:
    """원본 이미지 배열(H×W×3 ndarray) → 리사이즈 후 JPEG 1회 압축.

    카메라 원본을 이미 한 번 JPEG로 인코딩한 뒤 그걸 다시 열어 리사이즈+재인코드하는
    (resize_jpeg를 거치는) 이중 압축을 피하기 위한 경로 — 배열을 바로 받아 딱 한 번만
    압축한다.
    """
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        raise RuntimeError("Pillow 미설치: pip install Pillow")
    img = Image.fromarray(image).convert("RGB")
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
    """편의 함수: resize → split. 입력이 이미 JPEG bytes일 때만 사용 (이중 압축 경로)."""
    return split_into_chunks(resize_jpeg(raw_bytes), image_id)


def prepare_chunks_from_array(image, image_id: int) -> list[bytes]:
    """편의 함수: 원본 배열에서 곧바로 리사이즈+압축(1회)+분할."""
    return split_into_chunks(resize_and_encode(image), image_id)


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

    NACK 재요청 정책 (온보드의 ChunkCache/nack_thread와 짝을 이룬다):
      - poll_nack_targets(): 마지막 새 청크 수신 후 NACK_INACTIVITY_SEC 동안
        진행이 없는 이미지를 찾아 NACK 대상으로 반환한다. 버퍼는 지우지 않는다
        (재전송 청크가 도착하면 그대로 이어붙일 수 있어야 하므로). 이미지당
        MAX_NACK_RETRY회까지만 대상이 된다.
      - expire(): MAX_NACK_RETRY를 다 쓰고도 다시 NACK_INACTIVITY_SEC만큼 진행이
        없거나, 첫 청크 수신 후 IMAGE_REASSEMBLY_TIMEOUT_SEC(절대 상한)가 지나면
        그때 비로소 포기하고 버퍼를 삭제한다.
    """
    _bufs:           dict[int, dict[int, bytes]] = field(default_factory=dict)
    _totals:         dict[int, int]              = field(default_factory=dict)
    _first_seen:     dict[int, float]            = field(default_factory=dict)
    _last_new_chunk: dict[int, float]             = field(default_factory=dict)
    _retry_counts:   dict[int, int]               = field(default_factory=dict)
    _completed_ids:  set[int]                     = field(default_factory=set)

    def feed(self, image_id: int, chunk_id: int, total: int, data: bytes) -> bytes | None:
        """청크 추가. 모든 청크가 모이면 JPEG bytes 반환, 미완성 시 None.

        이미 가지고 있던 chunk_id가 재전송으로 다시 도착해도 같은 키에 덮어쓸
        뿐이라 중복 저장되지 않는다.

        이미 완성돼서 버퍼가 지워진 image_id로 뒤늦게 낙오 청크(원본 전송분이
        저우선순위 큐에 오래 묶여있다 뒤늦게 도착하는 등)가 도착하면, 그걸 "새
        이미지 수신 시작"으로 오인해 절대 못 채울 유령 버퍼를 만들고 NACK
        재요청까지 낭비하게 된다 — 이미 완성된 image_id는 조용히 무시한다."""
        if image_id in self._completed_ids:
            logger.debug("image_id=%d 낙오 청크(chunk %d) 무시 — 이미 완성됨",
                         image_id, chunk_id)
            return None
        now = time.monotonic()
        if image_id not in self._bufs:
            self._bufs[image_id]           = {}
            self._totals[image_id]         = total
            self._first_seen[image_id]     = now
            self._retry_counts[image_id]   = 0
        is_new_chunk = chunk_id not in self._bufs[image_id]
        self._bufs[image_id][chunk_id] = data
        if is_new_chunk:
            self._last_new_chunk[image_id] = now
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
        self._last_new_chunk.pop(image_id, None)
        self._retry_counts.pop(image_id, None)
        jpeg = b"".join(chunks[i] for i in range(len(chunks)))
        logger.info("image_id=%d 재조립 완료 (%d bytes)", image_id, len(jpeg))
        return jpeg

    def missing(self, image_id: int) -> list[int]:
        if image_id not in self._bufs:
            return []
        total    = self._totals.get(image_id, 0)
        received = set(self._bufs[image_id])
        return [i for i in range(total) if i not in received]

    def progress(self, image_id: int) -> tuple[int, int]:
        """현재까지 수신한 고유 청크 수와 전체 청크 수를 반환한다 (대시보드 진행률 표시용)."""
        return (
            len(self._bufs.get(image_id, {})),
            self._totals.get(image_id, 0),
        )

    def missing_batched(self, image_id: int,
                         batch_size: int = MAX_MISSING_PER_NACK) -> list[list[int]]:
        """missing()을 NACK 패킷 하나에 담을 수 있는 크기(기본 MAX_MISSING_PER_NACK)
        단위로 잘라 반환한다. 호출부는 이 배치들을 각각 별도 NACK 패킷으로 보내되,
        이 전체가 재요청 1회로 취급되도록(poll_nack_targets가 이미 그렇게 센다)
        한 번의 poll_nack_targets() 결과에서 얻은 배치들을 한꺼번에 보내야 한다."""
        m = self.missing(image_id)
        return [m[i:i + batch_size] for i in range(0, len(m), batch_size)]

    def poll_nack_targets(self, inactivity_s: float = NACK_INACTIVITY_SEC,
                           max_retry: int = MAX_NACK_RETRY) -> list[tuple[int, list[int]]]:
        """지금 NACK을 보내야 할 이미지들을 (image_id, missing_chunks) 리스트로
        반환한다. 버퍼는 지우지 않는다 — expire()만 버퍼를 지운다.
        호출 하나당 대상 이미지의 재시도 횟수가 1 증가한다 (누락 청크가 얼마나
        많아 missing_batched()로 NACK을 여러 개 나눠 보내든 이 호출 자체는 1회다)."""
        now = time.monotonic()
        targets = []
        for image_id, last_new in list(self._last_new_chunk.items()):
            if now - last_new < inactivity_s:
                continue
            if self._retry_counts.get(image_id, 0) >= max_retry:
                continue
            miss = self.missing(image_id)
            if not miss:
                continue
            self._retry_counts[image_id] = self._retry_counts.get(image_id, 0) + 1
            # 재요청 후 바로 다음 폴링에서 또 대상으로 잡히지 않도록 기준 시각을
            # 갱신한다 — 온보드가 응답할 시간(inactivity_s)을 한 번 더 준다.
            self._last_new_chunk[image_id] = now
            targets.append((image_id, miss))
        return targets

    def expire(self, inactivity_s: float = NACK_INACTIVITY_SEC,
               max_retry: int = MAX_NACK_RETRY,
               absolute_timeout_s: float = IMAGE_REASSEMBLY_TIMEOUT_SEC
               ) -> list[tuple[int, list[int]]]:
        """포기할 image_id → (id, missing_chunks) 리스트를 반환하고 버퍼를 삭제한다.

        포기 조건: (재요청 max_retry회를 다 쓰고도 다시 inactivity_s만큼 무진전)
        또는 (첫 청크 수신 후 absolute_timeout_s 경과, 온보드 청크 캐시도 이미
        비웠을 시점이라 더 기다려도 소용없음)."""
        now     = time.monotonic()
        expired = []
        for image_id, first in list(self._first_seen.items()):
            retry_exhausted = self._retry_counts.get(image_id, 0) >= max_retry
            stale = now - self._last_new_chunk.get(image_id, first) >= inactivity_s
            absolute_timeout = now - first > absolute_timeout_s
            if (retry_exhausted and stale) or absolute_timeout:
                miss = self.missing(image_id)
                reason = "absolute_timeout" if absolute_timeout else "retry_exhausted"
                logger.warning("image_id=%d 포기(%s), 누락 청크: %s", image_id, reason, miss)
                expired.append((image_id, miss))
                for d in (self._bufs, self._totals, self._first_seen,
                          self._last_new_chunk, self._retry_counts):
                    d.pop(image_id, None)
        return expired

    def active_ids(self) -> list[int]:
        return list(self._bufs)
