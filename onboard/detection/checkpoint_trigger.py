# onboard/detection/checkpoint_trigger.py

from __future__ import annotations


class CheckpointTrigger:
    """
    다중 고도 체크포인트 트리거.

    checkpoints(예: [300, 150])를 고도 내림차순으로 하나씩 감시한다.
    각 체크포인트는 독립적으로 딱 1회만 발동하며, 발동한 체크포인트는 다시
    감시하지 않고 바로 다음 체크포인트로 넘어간다. 노이즈로 인한 오탐을
    막기 위해 임계값 이하 샘플이 debounce_count회 연속 관측되어야 확정된다.

    poll()은 정상 고도 기반 트리거, poll_time_backup()은 baro/gps 둘 다
    무응답일 때를 위한 시간 기반 백업 트리거다 — 호출 순서(정상 → 백업)로
    우선순위를 정하는 건 호출부(image_thread.py) 책임이며, 이 클래스는 두
    경로 모두 confirm_fired() 한 번으로 함께 정리되는 것만 보장한다.

    poll()은 "현재 고도 <= 체크포인트"만으로 판단하지 않는다 — 지상 대기
    중이거나 정점(apogee) 전 상승 중에도 이 조건은 트리비얼하게(또는 목표
    체크포인트 값보다 낮은 고도를 지나가는 것만으로) 만족돼버리기 때문에,
    "관측된 최고 고도 대비 min_launch_altitude 이상 올라갔었고, 그 최고
    고도보다 descent_confirm_margin 이상 낮아진 상태"(= 진짜 하강 중)일
    때만 debounce 카운팅을 시작한다.
    """

    def __init__(self, checkpoints: list[float], debounce_count: int, descent_rate_mps: float,
                 min_launch_altitude: float, descent_confirm_margin: float):
        self._checkpoints = list(checkpoints)
        self._debounce_count = debounce_count
        self._descent_rate_mps = descent_rate_mps
        self._min_launch_altitude = min_launch_altitude
        self._descent_confirm_margin = descent_confirm_margin
        self._idx = 0
        self._counter = 0
        self._armed = False  # 현재 체크포인트 debounce 확정 후 전송(confirm) 대기 중인지
        self._max_altitude_seen: float | None = None  # 발사/하강 확인 게이트용, 체크포인트 전환과 무관하게 비행 전체에서 계속 갱신

        # 시간 기반 백업 트리거 상태 (baro/gps 둘 다 무응답일 때만 사용)
        self._time_armed = False
        self._time_fire_info: dict | None = None

    def all_done(self) -> bool:
        return self._idx >= len(self._checkpoints)

    def current_target(self) -> float | None:
        if self.all_done():
            return None
        return self._checkpoints[self._idx]

    def poll(self, altitude: float) -> bool:
        """
        고도를 한 샘플 반영한다.

        Returns:
            bool: 현재 체크포인트가 (이번 호출로 새로 confirm되었거나, 이미
                  confirm되어 전송 재시도 대기 중이라) 대표 이미지를 전송해야
                  하면 True.
        """
        if self.all_done():
            return False

        if self._max_altitude_seen is None or altitude > self._max_altitude_seen:
            self._max_altitude_seen = altitude

        descended = (
            self._max_altitude_seen >= self._min_launch_altitude
            and (self._max_altitude_seen - altitude) >= self._descent_confirm_margin
        )

        target = self._checkpoints[self._idx]
        if descended and altitude <= target:
            self._counter += 1
            if self._counter >= self._debounce_count:
                self._armed = True
        else:
            # 아직 confirm 전(armed=False)이라면 노이즈로 본 카운트를 리셋한다.
            # 이미 confirm된(armed=True) 뒤에는 전송 재시도 중일 수 있으므로
            # 순간적으로 다시 튀어도 armed 상태를 유지한다.
            if not self._armed:
                self._counter = 0

        return self._armed

    def poll_time_backup(self, anchor_altitude: float | None,
                          anchor_time: float | None, now: float) -> bool:
        """
        baro/gps 둘 다 무응답일 때의 시간 기반 백업 트리거.

        마지막 유효 고도/시각(anchor) 기준, 목표 하강속도로 현재 체크포인트
        고도에 도달했을 것으로 추정되는 시각(estimated_time)을 넘기는 첫
        순간(윈도우 방식 — 정확히 그 시각 하나를 노리지 않음) 발동한다.
        정상 고도 트리거와 마찬가지로 한 번 확정(armed)되면 confirm_fired()
        전까지 유지된다 (재시도 대기).

        Args:
            anchor_altitude: 마지막으로 유효했던 고도(m). 아직 한 번도 유효한
                              값이 없었다면 None — 이 경우 발동하지 않는다.
            anchor_time: anchor_altitude를 관측한 시각.
            now: 현재 시각 (anchor_time과 같은 시간 기준이어야 함).
        """
        if self.all_done():
            return False
        if self._time_armed:
            return True
        if anchor_altitude is None or anchor_time is None:
            return False

        target = self._checkpoints[self._idx]
        estimated_time = anchor_time + (anchor_altitude - target) / self._descent_rate_mps
        if now >= estimated_time:
            self._time_armed = True
            self._time_fire_info = {
                "target": target,
                "anchor_altitude": anchor_altitude,
                "anchor_time": anchor_time,
                "estimated_time": estimated_time,
            }
        return self._time_armed

    def time_backup_info(self) -> dict | None:
        """가장 최근 poll_time_backup() 확정 시점의 anchor/estimated_time 스냅샷 (로깅용)."""
        return self._time_fire_info

    def confirm_fired(self) -> None:
        """대표 이미지가 실제로 큐잉 성공했을 때 호출 — 다음 체크포인트로 진행한다."""
        self._idx += 1
        self._counter = 0
        self._armed = False
        self._time_armed = False
        self._time_fire_info = None

    def reset(self) -> None:
        """전체 상태 초기화 (테스트 용도)"""
        self._idx = 0
        self._counter = 0
        self._armed = False
        self._time_armed = False
        self._time_fire_info = None
        self._max_altitude_seen = None
