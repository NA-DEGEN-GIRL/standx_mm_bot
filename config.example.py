"""
StandX MM Bot 설정 파일
사용법: config.py로 복사 후 수정
"""

# 모드 설정
MODE = "TEST"           # "TEST" = 시뮬레이션, "LIVE" = 실제 주문
EXCHANGE = "standx"
COIN = "BTC"
AUTO_CONFIRM = False    # True: LIVE 모드 YES 확인 생략

# 주문 설정
SPREAD_BPS = 7.5        # 주문 스프레드 (bps)
DRIFT_THRESHOLD = 2.5   # 재주문 트리거 (bps)
USE_MID_DRIFT = False   # True: mark drift + mid drift 합산, False: mark drift만 고려
MARK_MID_DIFF_LIMIT = 1.0  # mark-mid 차이가 이 값(bps) 초과시 주문 대기 (0이면 비활성화)
MIN_WAIT_SEC = 3.0      # 주문 변경 최소 대기 시간 (초)
REFRESH_INTERVAL = 0.05 # 화면 갱신 간격 (초)

# 수량 설정
SIZE_UNIT = 0.0001      # 주문 수량 단위 (BTC)
LEVERAGE = 6            # 레버리지 배수 (양방향이므로 실제 각 3배)
MAX_SIZE_BTC = 0.0002   # 최대 주문 수량 (None = 무제한)

# 안정성 설정
MAX_HISTORY = 1000              # 주문 히스토리 최대 보관 개수
MAX_CONSECUTIVE_ERRORS = 10     # 연속 에러 허용 횟수

# 포지션 자동 청산
AUTO_CLOSE_POSITION = True      # True: 포지션 생기면 자동 청산 후 MM 재개

# 청산 방식: "market" | "aggressive" | "chase"
# - market: 즉시 시장가 청산 (기존 동작)
# - aggressive: mark price 기준 지정가 (빠른 체결 유도)
# - chase: 호가창 최우선가 지정가
CLOSE_METHOD = "market"

# aggressive 모드 설정
CLOSE_AGGRESSIVE_BPS = 5.0      # mark price에서 떨어진 bps, 0이면 즉시체결 best 호가에 주문

# aggressive/chase 공통 설정
CLOSE_WAIT_SEC = 3.0            # 주문 후 대기 시간 (초)
CLOSE_MIN_SIZE_MARKET = 0.0001  # 이 수량 미만이면 시장가 청산

# 안전 제한
CLOSE_MAX_ITERATIONS = 100      # 최대 반복 횟수 (초과시 시장가)

# 스냅샷 설정 (tmux 없이 상태 확인용)
SNAPSHOT_INTERVAL = 60         # 스냅샷 저장 간격 (초), 0이면 비활성화
SNAPSHOT_FILE = "status.txt"   # 스냅샷 파일명
