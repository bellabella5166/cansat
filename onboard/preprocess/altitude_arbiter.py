# onboard/preprocess/altitude_arbiter.py

from __future__ import annotations

import logging
import math
from collections import deque

from onboard.system.config import (
    BARO_SENTINEL,
    BARO_FREEZE_WINDOW,
    BARO_FREEZE_EPS,
    BARO_MAX_JUMP,
    GPS_MAX_HDOP,
)

logger = logging.getLogger("onboard.altitude")


class AltitudeArbiter:
    """
    기압계(주) / GPS(부) 이중화 고도 판정.

    평소엔 기압계 고도(정밀도↑, 갱신 빠름)를 신뢰 기준선으로 사용한다.
    기압계가 미보정·정지(freeze)·급점프 등 이상 징후를 보이면 GPS 고도로
    자동 전환하고, 다음 샘플이 기준선 대비 다시 정상으로 판정되는 즉시
    기압계로 복귀한다.

    이상 판정된 샘플은 기준선(_last_baro/_baro_history) 갱신에 반영하지
    않는다 — 그래야 (a) freeze 상태에서도 다음 정상값이 들어오자마자 바로
    벗어날 수 있고, (b) 순간적인 급점프 글리치 한 번 때문에 기준선 자체가
    오염되어 이후의 정상값들까지 계속 이상치로 오판되는 일이 없다.
    """

    def __init__(self):
        self._baro_history: deque = deque(maxlen=BARO_FREEZE_WINDOW)
        self._last_baro: float | None = None
        self._using_gps = False

    def _baro_anomaly(self, baro_alt: float) -> str | None:
        if baro_alt is None or math.isnan(baro_alt) or math.isinf(baro_alt):
            return "invalid"
        if baro_alt >= BARO_SENTINEL:
            return "uncalibrated"
        if self._last_baro is not None and abs(baro_alt - self._last_baro) > BARO_MAX_JUMP:
            return "jump"
        # freeze 판정은 현재 샘플까지 포함한 윈도우로 본다 — 그래야 기준선이
        # 정지 상태로 굳어 있어도 값이 다시 움직이기 시작하면 즉시 감지된다.
        window = list(self._baro_history) + [baro_alt]
        if len(window) >= BARO_FREEZE_WINDOW:
            window = window[-BARO_FREEZE_WINDOW:]
            if max(window) - min(window) < BARO_FREEZE_EPS:
                return "freeze"
        return None

    def _gps_valid(self, processed: dict) -> bool:
        return (
            int(processed.get("fix_quality", 0)) > 0
            and float(processed.get("hdop", 99.9)) <= GPS_MAX_HDOP
        )

    def resolve(self, processed: dict) -> tuple[float, str]:
        """
        Args:
            processed (dict): SensorPreprocess 출력 (baro_altitude, gps_altitude,
                               fix_quality, hdop 포함)

        Returns:
            tuple: (altitude_m, source) — source는 "baro" 또는 "gps"
        """
        baro_alt = processed.get("baro_altitude", BARO_SENTINEL)
        gps_alt  = processed.get("gps_altitude", BARO_SENTINEL)

        anomaly = self._baro_anomaly(baro_alt)

        if anomaly is None:
            self._baro_history.append(baro_alt)
            self._last_baro = baro_alt
            if self._using_gps:
                logger.info("Barometer recovered (baro=%.1fm) — switching back to barometer", baro_alt)
                self._using_gps = False
            return baro_alt, "baro"

        # 기압계 이상 감지 → GPS로 전환 시도
        if self._gps_valid(processed):
            if not self._using_gps:
                logger.warning("Barometer anomaly (%s, baro=%.1fm) — switching to GPS altitude",
                                anomaly, baro_alt)
            self._using_gps = True
            return gps_alt, "gps"

        # GPS도 불량하면 마지막 신뢰 기준값으로 폴백 (완전 무신호 방지)
        self._using_gps = True
        fallback = self._last_baro if self._last_baro is not None else baro_alt
        return fallback, "baro"
