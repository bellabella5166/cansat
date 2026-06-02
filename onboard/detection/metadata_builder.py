class MetadataBuilder:
    """
    탐지 결과와 센서 데이터를 결합하여 메타데이터를 생성한다.
    """

    def build(self, detections: list, timestamp: float, sensor_data: dict) -> list:
        """
        탐지 결과를 메타데이터로 변환한다.

        Args:
            detections (list): 탐지 결과 list of dict
            timestamp (float): 타임스탬프
            sensor_data (dict): 전처리된 센서 데이터

        Returns:
            list of dict: 메타데이터 리스트
                [{'timestamp': float, 'image_id': str, 'class': str,
                  'confidence': float, 'bbox': list, 'lat': float,
                  'lon': float, 'altitude': float}]
                실패 시 빈 리스트 반환
        """
        if detections is None:
            print("[MetadataBuilder] ❌ detection result None")
            return []

        if sensor_data is None:
            print("[MetadataBuilder] ❌ sensor data None")
            return []

        if len(detections) == 0:
            return []

        try:
            metadata_list = []

            for det in detections:
                metadata = {
                    'timestamp': timestamp,
                    'image_id': det['image_id'],
                    'class': det['class'],
                    'confidence': det['confidence'],
                    'bbox': det['bbox'],
                    'lat': sensor_data.get('lat', 0.0),
                    'lon': sensor_data.get('lon', 0.0),
                    'altitude': sensor_data.get('gps_altitude', 0.0),
                }
                metadata_list.append(metadata)

            return metadata_list

        except Exception as e:
            print(f"[MetadataBuilder] ❌ metadata generation error : {e}")
            return []