# onboard/system/threads/heartbeat_thread.py

from __future__ import annotations

import logging
import queue
import time

from protocol import PacketType

logger = logging.getLogger("onboard.heartbeat")

HB_INTERVAL = 5.0


def heartbeat_loop(tx_q: queue.PriorityQueue, seq,
                   running: list, enqueue_fn) -> None:

    logger.info("Heartbeat loop started")

    while running[0]:
        enqueue_fn(tx_q, PacketType.HEARTBEAT, b"", seq, 5)
        time.sleep(HB_INTERVAL)

    logger.info("Heartbeat loop stopped")