# onboard/system/threads/chunk_thread.py

from __future__ import annotations

import io
import logging
import queue

from PIL import Image
from protocol import PacketType
from image_chunker import prepare_chunks

logger = logging.getLogger("onboard.chunk")


def image_chunk_loop(tx_q: queue.PriorityQueue, seq,
                     img_q: queue.Queue,
                     running: list, enqueue_fn, img_sending) -> None:

    logger.info("Image chunk loop started")

    while running[0]:
        try:
            kind, img_id, raw_img = img_q.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            img_sending.set()  # 전송 시작
            buf = io.BytesIO()
            Image.fromarray(raw_img).save(buf, format="JPEG")
            chunks = prepare_chunks(buf.getvalue(), img_id)
            for chunk_payload in chunks:
                enqueue_fn(tx_q, PacketType.IMG, chunk_payload, seq, 200)
            logger.info("Representative image id=%d → %d chunks queued",
                        img_id, len(chunks))
        except Exception as e:
            logger.error("Image chunk error: %s", e)
        finally:
            img_sending.clear()  