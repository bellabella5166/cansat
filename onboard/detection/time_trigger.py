# onboard/detection/time_trigger.py

from __future__ import annotations


class TimeTrigger:
    """
    시간 기반 대표 이미지 트리거.

    전원 인가(프로그램 시작) 시점부터 interval_s 간격으로 무한 반복 발동한다.
    고도값을 전혀 참조하지 않으며, start()로 잡은 기준 시각 이후 interval_s가
    지날 때마다 armed 상태가 된다. confirm_fired() 전까지는 armed를 유지해
    전송 재시도를 지원한다 (CheckpointTrigger와 동일한 재시도 계약).

    confirm_fired()는 다음 예정 시각을 "지금 + interval_s"가 아니라
    "이전 예정 시각 + interval_s"로 잡는다 — 전송이 늦게 confirm돼도 전체
    스케줄이 밀리지 않고, 원래 간격(1분, 2분, 3분...) 그대로 유지된다.
    """

    def __init__(self, interval_s: float):
        self._interval_s = interval_s
        self._next_fire: float | None = None
        self._armed = False

    def start(self, now: float) -> None:
        """이미지 루프 시작 시각 기준으로 첫 발동 예정 시각을 잡는다."""
        self._next_fire = now + self._interval_s

    def poll(self, now: float) -> bool:
        """
        시각을 한 번 반영한다.

        Returns:
            bool: 예정 시각을 (이번 호출로 새로 지났거나, 이미 지나 전송
                  재시도 대기 중이라) 대표 이미지를 전송해야 하면 True.
        """
        if self._next_fire is None:
            return False
        if now >= self._next_fire:
            self._armed = True
        return self._armed

    def confirm_fired(self) -> None:
        """대표 이미지가 실제로 큐잉 성공했을 때 호출 — 다음 예정 시각으로 진행한다."""
        self._next_fire += self._interval_s
        self._armed = False
