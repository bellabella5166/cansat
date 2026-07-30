# onboard/preprocess/altitude_anchor.py

from __future__ import annotations

import math

from onboard.system.config import BARO_SENTINEL, GPS_MAX_HDOP


class AltitudeAnchor:
    """
    baro/gps "센서 완전 실패" 판정을 위한 독립적인 최소 유효성 추적기.

    AltitudeArbiter(altitude_arbiter.py)는 이미 baro 우선/GPS 대체의 정교한
    이상 판정(freeze/jump 등)을 통해 어떤 값을 쓸지 결정한다 — 이 클래스는
    그 판단 로직을 전혀 건드리지 않고, 완전히 독립적으로 "baro가 마지막으로
    유효했던 시각", "GPS가 마지막으로 유효했던 시각"만 병렬로 추적한다.

    또한 baro 또는 GPS 중 하나라도 유효할 때마다 anchor(마지막 신뢰 가능한
    고도/시각)를 갱신한다 — baro가 죽어도 GPS가 살아있으면 GPS 값으로 계속
    갱신되며, 특정 센서로 고정되지 않는다.
    """

    def __init__(self, sensor_timeout_s: float):
        self._sensor_timeout_s = sensor_timeout_s
        self._last_baro_valid_time: float | None = None
        self._last_gps_valid_time: float | None = None
        self.last_valid_altitude: float | None = None
        self.last_valid_time: float | None = None

    def _baro_valid(self, baro_alt) -> bool:
        return (
            baro_alt is not None
            and not math.isnan(baro_alt)
            and not math.isinf(baro_alt)
            and baro_alt < BARO_SENTINEL
        )

    def _gps_valid(self, processed: dict) -> bool:
        return (
            int(processed.get("fix_quality", 0)) > 0
            and float(processed.get("hdop", 99.9)) <= GPS_MAX_HDOP
        )

    def update(self, processed: dict, now: float) -> None:
        """매 샘플 호출. baro/gps 유효 시각을 독립적으로 갱신하고, anchor도 갱신한다."""
        # 첫 호출 시 두 타이머를 now로 시작 — 그래야 처음부터 완전 무응답이어도
        # sensor_timeout_s가 지나야 실패로 판정된다 (기동 직후 즉시 실패 오판 방지).
        if self._last_baro_valid_time is None:
            self._last_baro_valid_time = now
        if self._last_gps_valid_time is None:
            self._last_gps_valid_time = now

        baro_alt = processed.get("baro_altitude", BARO_SENTINEL)
        baro_ok = self._baro_valid(baro_alt)
        gps_ok = self._gps_valid(processed)

        if baro_ok:
            self._last_baro_valid_time = now
        if gps_ok:
            self._last_gps_valid_time = now

        # anchor 갱신: baro 우선, baro가 죽어도 gps가 살아있으면 gps로 계속 갱신
        if baro_ok:
            self.last_valid_altitude = baro_alt
            self.last_valid_time = now
        elif gps_ok:
            self.last_valid_altitude = processed.get("gps_altitude", BARO_SENTINEL)
            self.last_valid_time = now

    def is_sensor_failure(self, now: float) -> bool:
        """baro, gps 각각 독립적으로 sensor_timeout_s 이상 무응답이면 True (둘 다 조건 충족 시)."""
        if self._last_baro_valid_time is None or self._last_gps_valid_time is None:
            return False  # update()가 아직 한 번도 호출되지 않음
        return (
            now - self._last_baro_valid_time >= self._sensor_timeout_s
            and now - self._last_gps_valid_time >= self._sensor_timeout_s
        )
