# onboard/detection/chunk_cache.py

from __future__ import annotations

import threading
import time


class ChunkCache:
    """
    최근 전송한 대표 이미지의 청크를 RAM에 보관해, NACK 재전송 요청에 실제로
    응답할 수 있게 한다.

    최근 max_images장 또는 ttl_s초 중 먼저 도달하는 조건까지만 보관한다 —
    지상국도 이미지당 최대 재요청 횟수・무응답 시간이 지나면 포기하므로,
    온보드가 그보다 오래 들고 있을 이유가 없다 (메모리도 무한정 늘지 않도록).
    """

    def __init__(self, max_images: int = 5, ttl_s: float = 300.0):
        self._max_images = max_images
        self._ttl_s = ttl_s
        self._entries: dict[int, dict] = {}  # image_id -> {"chunks": {chunk_id: bytes}, "ts": float}
        self._order: list[int] = []          # 오래된 것부터 제거하기 위한 삽입 순서
        self._lock = threading.Lock()

    def store(self, image_id: int, chunks: list[bytes]) -> None:
        """전송 직후 이미지의 청크 전체를 캐시에 등록한다."""
        with self._lock:
            self._entries[image_id] = {
                "chunks": dict(enumerate(chunks)),
                "ts": time.monotonic(),
            }
            if image_id in self._order:
                self._order.remove(image_id)
            self._order.append(image_id)
            while len(self._order) > self._max_images:
                oldest_id = self._order.pop(0)
                self._entries.pop(oldest_id, None)

    def get_chunks(self, image_id: int, chunk_ids: list[int]) -> list[bytes]:
        """image_id의 chunk_ids에 해당하는 청크 payload들을 반환한다.
        캐시에 없는 이미지/청크는 조용히 건너뛴다 (이미 만료됐거나 상한을 넘어 밀려난 경우)."""
        with self._lock:
            self._evict_expired_locked()
            entry = self._entries.get(image_id)
            if entry is None:
                return []
            chunks = entry["chunks"]
            return [chunks[cid] for cid in chunk_ids if cid in chunks]

    def _evict_expired_locked(self) -> None:
        now = time.monotonic()
        expired = [iid for iid, e in self._entries.items() if now - e["ts"] > self._ttl_s]
        for iid in expired:
            self._entries.pop(iid, None)
            if iid in self._order:
                self._order.remove(iid)
