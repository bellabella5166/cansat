# onboard/system/threads/chunk_thread.py

from __future__ import annotations

import logging
import queue
import threading
import time

from protocol import PacketType
from image_chunker import prepare_chunks_from_array

from onboard.detection.chunk_cache import ChunkCache

logger = logging.getLogger("onboard.chunk")

IMG_Q_MAX = 200


def image_chunk_loop(tx_q: queue.PriorityQueue, seq,
                     img_q: queue.Queue,
                     running: list, enqueue_fn, img_sending,
                     chunk_cache: ChunkCache, send_timeout_s: float) -> None:

    logger.info("Image chunk loop started")

    while running[0]:
        try:
            kind, img_id, raw_img = img_q.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            img_sending.set()  # 전송 시작
            chunks = prepare_chunks_from_array(raw_img, img_id)  # 리사이즈+압축 1회
            chunk_cache.store(img_id, chunks)  # NACK 재전송용으로 캐시에 보관

            # 이 이미지 자신의 청크가 몇 개 tx_q를 빠져나갔는지 독립적으로 추적한다.
            # 전역 _type_counts[IMG]는 재전송 스레드가 다른(더 오래된) 이미지의
            # 청크를 동시에 큐에 넣을 수 있어, 그걸로는 "이 이미지가 다 나갔는지"를
            # 정확히 판단할 수 없다.
            remaining = [len(chunks)]
            remaining_lock = threading.Lock()

            def _mark_dequeued():
                with remaining_lock:
                    remaining[0] -= 1

            queued_count = 0
            failed_count = 0
            for chunk_payload in chunks:
                queued = enqueue_fn(tx_q, PacketType.IMG, chunk_payload, seq, IMG_Q_MAX,
                                     on_dequeue=_mark_dequeued)
                if queued:
                    queued_count += 1
                else:
                    failed_count += 1
                    # 큐 등록에 실패한 청크는 tx_q에 들어가지 않아 on_dequeue가 절대
                    # 호출되지 않는다 — remaining에서 직접 빼주지 않으면 이미 못 보낸
                    # 청크 때문에 완료 판정이 send_timeout_s까지 불필요하게 밀린다.
                    _mark_dequeued()
            logger.info("Representative image queue result: image_id=%d total=%d "
                        "queued=%d failed=%d", img_id, len(chunks), queued_count, failed_count)

            # 청크가 tx_q에서 실제로 시리얼로 다 빠져나갈 때까지 대기 (재전송 포함).
            # 무한 대기하지 않도록 자체 상한(send_timeout_s)을 둔다 — 지상국과의
            # NACK 왕복이 어떤 이유로 안 되더라도, 그 시간이 지나면 포기하고
            # SENSOR/YOLO_META를 0.5Hz에 계속 묶어두지 않는다.
            start = time.monotonic()
            while running[0]:
                with remaining_lock:
                    left = remaining[0]
                if left <= 0:
                    logger.info(
                        "image_id=%d: all %d chunk(s) sent out over serial (%.1fs)",
                        img_id, len(chunks), time.monotonic() - start)
                    break
                if time.monotonic() - start > send_timeout_s:
                    logger.warning(
                        "image_id=%d timed out after %.0fs with %d/%d chunks still "
                        "unsent — giving up and moving to next image",
                        img_id, send_timeout_s, left, len(chunks))
                    break
                time.sleep(0.05)
        except Exception as e:
            logger.error("Image chunk error: %s", e)
        finally:
            img_sending.clear()