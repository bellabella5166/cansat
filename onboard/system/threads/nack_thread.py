# onboard/system/threads/nack_thread.py

from __future__ import annotations

import logging
import queue
import time

from protocol  import Packet, PacketType, PacketParser
from telemetry import decode_nack

from onboard.system.config import MAX_RETRY
from onboard.detection.chunk_cache import ChunkCache

logger = logging.getLogger("onboard.nack")

IMG_Q_MAX = 200


def nack_loop(serial, tx_q: queue.PriorityQueue, seq,
              running: list, chunk_cache: ChunkCache, enqueue_fn,
              retransmit_priority: int) -> None:

    parser = PacketParser()
    retry_counts: dict[int, int] = {}
    logger.info("NACK loop started")

    while running[0]:
        try:
            raw = serial.read_available()
        except Exception as e:
            logger.error("Serial read error: %s", e)
            time.sleep(0.1)
            continue

        if raw:
            try:
                for pkt in parser.feed(raw):
                    if pkt.ptype == PacketType.NACK:
                        try:
                            img_id, missing = decode_nack(pkt.payload)
                            missing = sorted(set(missing))  # 같은 NACK 안 중복 청크 번호 제거
                            cnt = retry_counts.get(img_id, 0) + 1
                            retry_counts[img_id] = cnt
                            if cnt <= MAX_RETRY:
                                resend = chunk_cache.get_chunks(img_id, missing)
                                for chunk_payload in resend:
                                    enqueue_fn(tx_q, PacketType.IMG, chunk_payload, seq,
                                               IMG_Q_MAX, priority=retransmit_priority)
                                logger.info(
                                    "NACK received: image_id=%d missing=%s → %d/%d chunks "
                                    "resent from cache (retry %d/%d)",
                                    img_id, missing, len(resend), len(missing), cnt, MAX_RETRY
                                )
                                if len(resend) < len(missing):
                                    logger.warning(
                                        "image_id=%d: %d missing chunk(s) not found in cache "
                                        "(already evicted?) — cannot resend",
                                        img_id, len(missing) - len(resend)
                                    )
                            else:
                                logger.warning(
                                    "image_id=%d max retry exceeded, not resending", img_id
                                )
                        except Exception as e:
                            logger.error("NACK decode error: %s", e)
            except Exception as e:
                # parser.feed() 자체(스트림 파싱)가 예상 못한 예외를 던져도
                # nack_loop 전체가 죽지 않도록 방어.
                logger.error("Packet parse error: %s", e)
                parser.reset()

        time.sleep(0.005)

    logger.info("NACK loop stopped")