# onboard/system/threads/nack_thread.py

from __future__ import annotations

import logging
import queue
import threading
import time

from protocol  import Packet, PacketType, PacketParser
from telemetry import decode_nack

from onboard.detection.chunk_cache import ChunkCache

logger = logging.getLogger("onboard.nack")

IMG_Q_MAX = 200


def _track_retransmit_completion(img_id: int, packet_count: int, total: int,
                                  remaining: list, remaining_lock: threading.Lock,
                                  running: list, timeout_s: float) -> None:
    """재전송 큐에 넣은 청크가 실제로 tx_q를 빠져나가 serial.write()까지 갔는지
    (전송 성공 여부 자체는 아니고, 온보드가 내보내는 시도를 끝냈는지) 별도
    스레드에서 추적한다 — nack_loop 본 루프를 여기서 막으면 그 사이 들어오는
    다른 NACK 패킷 처리가 지연되므로 논블로킹으로 분리한다."""
    start = time.monotonic()
    while running[0]:
        with remaining_lock:
            left = remaining[0]
        if left <= 0:
            logger.info(
                "Retransmit complete: image_id=%d nack_packet_count=%d "
                "%d/%d requested chunk(s) sent out over serial",
                img_id, packet_count, total, total
            )
            return
        if time.monotonic() - start > timeout_s:
            logger.warning(
                "Retransmit timed out: image_id=%d nack_packet_count=%d "
                "%d/%d requested chunk(s) still unsent after %.0fs",
                img_id, packet_count, total - left, total, timeout_s
            )
            return
        time.sleep(0.05)


def nack_loop(serial, tx_q: queue.PriorityQueue, seq,
              running: list, chunk_cache: ChunkCache, enqueue_fn,
              retransmit_priority: int, retransmit_timeout_s: float) -> None:
    """
    지상국(ImageReassembler.poll_nack_targets())이 누락 청크가 많은 이미지 하나를
    NACK 패킷 여러 개로 나눠 보낼 수 있다(패킷당 최대 62개, MAX_MISSING_PER_NACK).
    그 여러 패킷은 "한 번의 재요청 라운드"를 쪼갠 것일 뿐이라 — NACK *패킷* 수로
    재시도 상한을 세면(과거 방식) 몇 번째 패킷부터 부당하게 거부될 수 있다.
    라운드 수・포기 시점은 이미 지상국의 poll_nack_targets()/expire()가 관리하므로,
    온보드는 캐시에 남아있는 한 요청받은 청크를 그냥 다 처리한다 — NACK 패킷 수는
    로그 확인용으로만 센다.
    """

    parser = PacketParser()
    nack_packet_counts: dict[int, int] = {}
    logger.info("NACK loop started")

    while running[0]:
        try:
            raw = serial.read_available()
        except Exception as e:
            logger.error("Serial read error: %s", e)
            time.sleep(0.1)
            continue

        if raw:
            # 헤더(0xAA55)조차 못 잡아 CRC Mismatch 로그도 안 남는 경우를 대비한
            # 최하위 레벨 기록 — "그 시간대에 시리얼로 뭔가 들어오긴 했다"는
            # 사실 자체를 남겨서, 로그에 아무 것도 없을 때 그게 "RF 미도달"인지
            # "패킷으로 조립은 됐는데 그 이후 단계에서 조용히 버려졌는지"를 구분한다.
            logger.debug("Raw serial bytes received: %d bytes: %s",
                         len(raw), raw.hex())
            try:
                for pkt in parser.feed(raw):
                    if pkt.ptype == PacketType.NACK:
                        try:
                            img_id, missing = decode_nack(pkt.payload)
                            # 같은 NACK 패킷 안의 중복 번호만 제거한다 — 다음 NACK
                            # 패킷(다른 라운드)에서 같은 번호가 다시 오면 그때는
                            # 별개 요청으로 다시 처리해야 한다 (무선 유실로 재전송분도
                            # 또 안 도착했을 수 있으므로).
                            missing = sorted(set(missing))
                            packet_count = nack_packet_counts.get(img_id, 0) + 1
                            nack_packet_counts[img_id] = packet_count

                            resend = chunk_cache.get_chunks(img_id, missing)
                            remaining = [len(resend)]
                            remaining_lock = threading.Lock()

                            def _mark_dequeued():
                                with remaining_lock:
                                    remaining[0] -= 1

                            queued_count = 0
                            failed_count = 0
                            for chunk_payload in resend:
                                queued = enqueue_fn(tx_q, PacketType.IMG, chunk_payload, seq,
                                                     IMG_Q_MAX, priority=retransmit_priority,
                                                     on_dequeue=_mark_dequeued)
                                if queued:
                                    queued_count += 1
                                else:
                                    failed_count += 1
                                    # 큐 등록에 실패한 청크는 on_dequeue가 절대 안 불리므로
                                    # 직접 빼주지 않으면 완료 판정이 타임아웃까지 밀린다.
                                    _mark_dequeued()

                            if queued_count > 0:
                                threading.Thread(
                                    target=_track_retransmit_completion,
                                    args=(img_id, packet_count, len(resend),
                                          remaining, remaining_lock, running,
                                          retransmit_timeout_s),
                                    daemon=True, name=f"nack-track-{img_id}-{packet_count}"
                                ).start()

                            logger.info(
                                "NACK packet received: image_id=%d requested=%d "
                                "found_in_cache=%d queued=%d queue_failed=%d "
                                "nack_packet_count=%d",
                                img_id, len(missing), len(resend),
                                queued_count, failed_count, packet_count
                            )
                            not_found = len(missing) - len(resend)
                            if not_found:
                                logger.warning(
                                    "image_id=%d: %d requested chunk(s) not found in "
                                    "cache (already evicted?) — cannot resend",
                                    img_id, not_found
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