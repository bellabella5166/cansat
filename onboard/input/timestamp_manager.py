import time

def get_timestamp() -> float:
    """
    현재 시각을 Unix timestamp(float)로 반환한다.
    모든 데이터 수집 시점에 즉시 호출하여 타임스탬프를 부여한다.
    
    Returns:
        float: 현재 Unix timestamp (초 단위)
    """
    return time.time()


def format_timestamp(timestamp: float) -> str:
    """
    Unix timestamp를 사람이 읽기 쉬운 문자열로 변환한다.
    로그 기록 및 파일명 생성에 활용한다.
    
    Args:
        timestamp (float): Unix timestamp
    
    Returns:
        str: 'YYYY-MM-DD_HH-MM-SS.mmm' 형식의 문자열
    """
    t = time.localtime(timestamp)
    ms = int((timestamp % 1) * 1000)
    return time.strftime("%Y-%m-%d_%H-%M-%S", t) + f".{ms:03d}"