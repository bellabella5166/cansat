class IDManager:
    """
    이미지와 센서 데이터에 고유 식별자를 부여한다.
    중복 없이 순서대로 증가하는 ID를 생성한다.
    """

    def __init__(self):
        self._image_counter = 0
        self._sensor_counter = 0

    def get_image_id(self) -> str:
        """
        이미지 고유 식별자를 생성하고 반환한다.

        Returns:
            str: 'IMG_00000001' 형식의 이미지 ID
        """
        self._image_counter += 1
        return f"IMG_{self._image_counter:08d}"

    def get_sensor_id(self) -> str:
        """
        센서 데이터 고유 식별자를 생성하고 반환한다.

        Returns:
            str: 'SEN_00000001' 형식의 센서 ID
        """
        self._sensor_counter += 1
        return f"SEN_{self._sensor_counter:08d}"

    def reset(self):
        """
        카운터를 초기화한다. (테스트 용도)
        """
        self._image_counter = 0
        self._sensor_counter = 0