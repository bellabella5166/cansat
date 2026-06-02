class IDManager:
    """
    이미지와 센서 데이터에 고유 식별자를 부여한다.
    중복 없이 순서대로 증가하는 ID를 생성한다.

    하나의 카운터에서 두 가지 표현을 파생한다:
      - 파일명용 문자열  : 'IMG_00000001'
      - 통신용 uint16    : 0~65535 (패킷 image_id)
    """

    UINT16_MAX = 0xFFFF  # 65535

    def __init__(self):
        self._image_counter = 0
        self._sensor_counter = 0

    # ── 이미지 ────────────────────────────────────────────────
    def get_image_id(self) -> str:
        """파일명용 이미지 ID. 예: 'IMG_00000001'"""
        self._image_counter += 1
        return f"IMG_{self._image_counter:08d}"

    def get_image_id_uint16(self) -> int:
        """
        통신용 이미지 ID (uint16, 0~65535).
        현재 카운터 값을 그대로 uint16 범위로 순환시켜 반환한다.
        get_image_id()와 동일한 카운터를 참조하므로 파일명과 매칭된다.
        """
        return self._image_counter & self.UINT16_MAX

    # ── 센서 ──────────────────────────────────────────────────
    def get_sensor_id(self) -> str:
        """파일명용 센서 ID. 예: 'SEN_00000001'"""
        self._sensor_counter += 1
        return f"SEN_{self._sensor_counter:08d}"

    def get_sensor_id_uint16(self) -> int:
        """통신용 센서 ID (uint16, 0~65535)."""
        return self._sensor_counter & self.UINT16_MAX

    def reset(self):
        """카운터를 초기화한다. (테스트 용도)"""
        self._image_counter = 0
        self._sensor_counter = 0
