# StandX Market Making Bot

StandX 무기한 선물 거래소에서 자동으로 마켓메이킹을 수행하는 봇입니다.

---

## 면책조항 (Disclaimer)

> **경고: 이 소프트웨어는 있는 그대로(AS-IS) 제공되며, 어떠한 보증도 하지 않습니다.**
>
> - 이 봇을 사용하여 발생하는 **모든 손실에 대한 책임은 전적으로 사용자에게 있습니다.**
> - 이 소프트웨어는 **투자 조언이 아닙니다.** 재정적 결정은 본인의 판단 하에 내려야 합니다.
> - 암호화폐 거래는 **원금 손실 위험**이 있으며, 레버리지 거래는 손실을 증폭시킬 수 있습니다.
> - 개발자는 버그, 거래소 장애, 네트워크 문제 등으로 인한 **예기치 않은 동작에 대해 책임지지 않습니다.**
> - 반드시 **잃어도 되는 금액**으로만 거래하세요.
>
> 이 소프트웨어를 사용함으로써 위 조건에 동의한 것으로 간주됩니다.

---

## 빠른 시작 (처음 사용자용)

### 1단계: 파이썬 설치 확인

터미널(명령 프롬프트)을 열고 아래 명령어를 입력하세요:

```bash
python --version
```

`Python 3.10.x` 같은 결과가 나와야 합니다. 안 나오면 Python 3.10을 먼저 설치하세요.

### 2단계: 의존성 설치

프로젝트 폴더로 이동한 후:

```bash
pip install -r requirements.in
```

### 3단계: 지갑 설정 파일 만들기

`.env.example` 파일을 복사해서 `.env` 파일을 만듭니다.

**Windows:**
```bash
copy .env.example .env
```

**Mac/Linux:**
```bash
cp .env.example .env
```

그 다음 `.env` 파일을 메모장이나 편집기로 열어서 수정합니다:

```
WALLET_ADDRESS=0x여기에_지갑_주소_입력
PRIVATE_KEY=여기에_개인키_입력
```

**예시:**
```
WALLET_ADDRESS=0x1234567890abcdef1234567890abcdef12345678
PRIVATE_KEY=abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890
```

> **참고**: `PRIVATE_KEY`는 생략 가능합니다. 생략하면 실행 시 브라우저 로그인 창이 열립니다.

### 4단계: 봇 설정 파일 만들기

`config.example.py` 파일을 복사해서 `config.py` 파일을 만듭니다.

**Windows:**
```bash
copy config.example.py config.py
```

**Mac/Linux:**
```bash
cp config.example.py config.py
```

그 다음 `config.py` 파일을 편집기로 열어서 원하는 대로 수정합니다. (아래 "설정 파라미터" 섹션 참고)

### 5단계: 실행

```bash
python main.py
```

처음에는 `MODE = "TEST"`로 시뮬레이션 모드에서 테스트해보세요!

---

## 프로그램 업데이트 방법

봇이 업데이트되면 새 기능이나 버그 수정이 포함됩니다. 업데이트하는 방법은 2가지입니다.

**GitHub 주소:** https://github.com/NA-DEGEN-GIRL/standx_mm_bot

### 방법 1: Git 사용 (추천)

처음에 Git으로 설치했다면 이 방법이 제일 쉽습니다.

```bash
# 1. 프로젝트 폴더로 이동
cd standx_mm_bot

# 2. 최신 버전 받아오기
git pull

# 3. 의존성 업데이트 (중요!)
pip install -r requirements.in
```

> **주의**: `config.py`와 `.env` 파일은 `.gitignore`에 있어서 덮어쓰지 않습니다. 내 설정은 그대로 유지됩니다!

### 방법 2: 수동 다운로드 (Git 안 쓰는 경우)

1. GitHub에서 **Code** → **Download ZIP** 클릭
2. 압축 풀기
3. 기존 폴더에 덮어쓰기
   - **주의**: `config.py`와 `.env` 파일은 덮어쓰지 마세요! (내 설정이 날아갑니다)
4. 의존성 업데이트:
   ```bash
   pip install -r requirements.in
   ```

### 의존성 업데이트가 중요한 이유

이 봇은 `mpdex`라는 거래소 연결 라이브러리를 사용합니다.
`mpdex`가 자주 업데이트되기 때문에 봇 업데이트 후 반드시 아래 명령어를 실행하세요:

```bash
pip install -r requirements.in
```

안 하면 "ModuleNotFoundError"나 이상한 에러가 날 수 있어요!

---

## 설정 방법 (config.py) - 완전 초보자용 가이드

`config.py` 파일을 메모장이나 VS Code로 열어서 수정하면 됩니다.

> **중요**: 설정값 바꿀 때 따옴표(`"`) 조심하세요!
> - 글자는 따옴표 필요: `MODE = "LIVE"`
> - 숫자는 따옴표 없이: `LEVERAGE = 6`
> - True/False는 따옴표 없이: `AUTO_CONFIRM = True`

---

### 1. MODE - 진짜 돈 쓸지 말지 (제일 중요!!)

```python
MODE = "TEST"    # 가짜 모드 - 돈 안 씀, 연습용
MODE = "LIVE"    # 진짜 모드 - 실제 돈으로 거래!!
```

**처음엔 무조건 `"TEST"`로 하세요!** 익숙해지면 `"LIVE"`로 바꾸면 됩니다.

---

### 2. AUTO_CONFIRM - YES 입력 생략

```python
AUTO_CONFIRM = False   # LIVE 모드 시작할 때 YES 입력해야 함
AUTO_CONFIRM = True    # YES 입력 없이 바로 시작
```

처음엔 `False`로 두세요. 나중에 자동화할 때 `True`로 바꾸면 됩니다.

---

### 3. SPREAD_BPS - 얼마나 떨어진 가격에 주문할지

```python
SPREAD_BPS = 8.0    # 현재가에서 0.08% 떨어진 곳에 주문
```

**쉽게 설명:**
- 비트코인이 $100,000일 때
- `SPREAD_BPS = 8`이면
- 매수 주문: $99,920에 (0.08% 아래)
- 매도 주문: $100,080에 (0.08% 위에)

**숫자가 크면?** → 더 멀리 주문 → 체결 안 될 확률 높음 → 안전함
**숫자가 작으면?** → 더 가까이 주문 → 체결 확률 높음 → 위험함

추천: **5~10 사이**로 시작하세요.

---

### 4. DRIFT_THRESHOLD - 언제 주문을 다시 넣을지

```python
DRIFT_THRESHOLD = 3.0   # 가격이 0.03% 움직이면 주문 재배치
```

**쉽게 설명:**
- 주문을 넣어놨는데 가격이 계속 움직이잖아요?
- 가격이 너무 멀어지면 주문을 취소하고 새 가격에 다시 넣어야 해요
- `DRIFT_THRESHOLD = 3`이면 0.03% 움직이면 재배치

**숫자가 크면?** → 주문 재배치 덜 함 → 안정적이지만 가격 따라가기 느림
**숫자가 작으면?** → 주문 재배치 자주 함 → 가격 잘 따라가지만 수수료 많이 듦

추천: **2~5** 사이로 시작하세요.

---

### 5. USE_MID_DRIFT - mid price 변동도 고려할지

```python
USE_MID_DRIFT = False   # mark price만 보고 취소 결정
USE_MID_DRIFT = True    # mark price + mid price 둘 다 보고 결정
```

**쉽게 설명:**
- Mark Price: 거래소가 계산한 "공정 가격"
- Mid Price: 실제 호가창의 중간 가격 (매수/매도 수량 가중 평균)
- `True`로 설정하면 두 가격 변동을 합산해서 더 민감하게 반응

**취소 조건:**
```
False일 때: (mark drift) > DRIFT_THRESHOLD
True일 때:  (mark drift) + (mid drift) > DRIFT_THRESHOLD
```

**예시:** `DRIFT_THRESHOLD=3`, `USE_MID_DRIFT=True`이면
- mark drift 2bps + mid drift 1.5bps = 3.5bps
- 3.5 > 3 이므로 → 주문 취소 후 재배치

추천: 처음엔 **False** (mark만), 더 민감하게 대응하고 싶으면 **True**

---

### 6. MARK_MID_DIFF_LIMIT - 시장 불안정할 때 주문 대기

```python
MARK_MID_DIFF_LIMIT = 0.0   # 비활성화 (항상 주문)
MARK_MID_DIFF_LIMIT = 1.0   # mark-mid 차이 1bps 이상이면 대기
```

**쉽게 설명:**
- Mark Price: 거래소가 계산한 "공정 가격"
- Mid Price: 실제 호가창의 중간 가격 (매수/매도 평균)
- 이 둘의 차이가 크면 시장이 불안정한 거예요

**이 기능이 하는 일:**
- mark-mid 차이가 크면 "지금은 위험하니까 기다리자"
- 차이가 줄어들면 그때 주문 넣기

**예시:** `MARK_MID_DIFF_LIMIT = 1.0`이면
- mark-mid 차이가 1.5bps → 대기 (MID_WAIT 상태)
- mark-mid 차이가 0.8bps → 주문 진행

추천: **1.0~2.0** (시장 안정될 때만 주문), 또는 **0** (항상 주문)

---

### 7. LEVERAGE - 레버리지 배수

```python
LEVERAGE = 6     # 6배 레버리지
```

**쉽게 설명:**
- 내 돈 $100 있으면
- `LEVERAGE = 6`이면 $600어치 거래 가능
- 양방향(사고팔고)이니까 각각 $300씩

**숫자가 크면?** → 더 큰 금액 거래 → 수익/손실 커짐
**숫자가 작으면?** → 더 작은 금액 거래 → 안전함

추천: 처음엔 **3~6** 정도로 시작하세요.

---

### 8. MAX_SIZE_BTC - 최대 주문 수량 제한

```python
MAX_SIZE_BTC = 0.001    # 한번에 최대 0.001 BTC만 주문
MAX_SIZE_BTC = None     # 제한 없음 (위험!)
```

**쉽게 설명:**
- 비트코인 $100,000일 때
- `MAX_SIZE_BTC = 0.001`이면 최대 $100어치만 주문

추천: 처음엔 **0.0001~0.001** 사이로 작게 시작하세요.

---

### 9. AUTO_CLOSE_POSITION - 자동 청산

```python
AUTO_CLOSE_POSITION = True    # 포지션 생기면 자동으로 정리
AUTO_CLOSE_POSITION = False   # 포지션 그냥 둠
```

MM봇은 사고파는 걸 반복하는데, 한쪽이 체결되면 포지션이 생겨요.
`True`로 해두면 자동으로 정리해줍니다.

추천: **True** (기본값 그대로)

---

### 10. CLOSE_METHOD - 청산 방법

```python
CLOSE_METHOD = "market"      # 시장가로 즉시 청산 (빠름, 약간 손해)
CLOSE_METHOD = "aggressive"  # 지정가로 청산 (느림, 손해 적음)
CLOSE_METHOD = "chase"       # 호가 따라가며 청산
```

**뭘 고를지 모르겠으면:** `"market"` (제일 간단)

---

### 11. CLOSE_AGGRESSIVE_BPS - aggressive 모드 세부설정

```python
CLOSE_AGGRESSIVE_BPS = 5.0   # 현재가에서 0.05% 떨어진 가격에 주문
CLOSE_AGGRESSIVE_BPS = 0     # 바로 체결되는 가격에 주문 (시장가 비슷)
```

`CLOSE_METHOD = "aggressive"` 일 때만 의미있어요.

---

### 12. 안정성 설정 (건드리지 마세요)

```python
MAX_HISTORY = 1000              # 그냥 두세요
MAX_CONSECUTIVE_ERRORS = 10     # 그냥 두세요
MIN_WAIT_SEC = 3.0              # 그냥 두세요
REFRESH_INTERVAL = 0.05         # 그냥 두세요
SIZE_UNIT = 0.0001              # 그냥 두세요
```

이건 고급 설정이에요. 뭔지 모르면 절대 건드리지 마세요!

---

## 처음 시작하는 사람을 위한 추천 설정

```python
# === 이것만 바꾸세요 ===
MODE = "TEST"              # 처음엔 무조건 TEST!
LEVERAGE = 6               # 적당한 레버리지
MAX_SIZE_BTC = 0.0001      # 아주 작은 금액으로 시작
SPREAD_BPS = 8.0           # 안전한 거리

# === 나머지는 그대로 두세요 ===
AUTO_CONFIRM = False
AUTO_CLOSE_POSITION = True
CLOSE_METHOD = "market"
```

**테스트 다 했으면:**
1. `MODE = "LIVE"` 로 바꾸기
2. 실행하고 `YES` 입력
3. 돌아가는거 확인

---

### 포지션 로그 기록

포지션이 감지되고 청산될 때마다 `position_log.txt` 파일에 자동으로 기록됩니다.

**로그 예시:**
```
2026-01-06 14:30:15 | POSITION DETECTED | LONG 0.005000 BTC @ 97500.00 | uPnL: $+12.50
2026-01-06 14:30:21 | POSITION CLOSED  | LONG 0.005000 BTC | PnL: $+12.50 | Method: aggressive | Time: 6.32s (2 iter)
```

> **주의**: 기록되는 PnL은 청산 직전의 미실현 손익입니다. 실제 실현 손익과 약간 차이가 날 수 있습니다.

### 실제로 돌리고 싶을 때

```python
MODE = "LIVE"           # 실제 주문
MAX_SIZE_BTC = 0.0002   # 약 $20 정도
```

---

## 실행 화면

```
┌─ StandX Market Making [LIVE] ─────────────────────┐
│ ▌ ACCOUNT                                         │
│   Available: $100.00                              │
│   Order Size: 0.0002 BTC ($20.00) x6              │
│                                                   │
│ ▌ MARKET DATA                                     │
│   Mark Price: 100,000.00                          │
│   Best Bid: 99,990.00  │  Best Ask: 100,010.00    │
│   OB Spread:  2.00 bps │  Drift:  1.50 bps        │
│                                                   │
│ ▌ ORDERS                                          │
│   SELL: ● OPEN  @ 100,008.00  x0.0002             │
│   BUY:  ● OPEN  @  99,992.00  x0.0002             │
│                                                   │
│ ▌ STATUS                                          │
│   ● MONITORING - Orders active                    │
└───────────────────────────────────────────────────┘
```

---

## 종료 방법

`Ctrl+C`를 누르면 종료됩니다.

LIVE 모드에서는 자동으로 모든 주문을 취소한 후 종료합니다.

---

## 원격 서버에서 실행 (AWS, GCP 등)

SSH 접속이 끊겨도 봇이 계속 돌아가게 하려면 **tmux**를 사용하세요.

### tmux 설치

```bash
# Ubuntu/Debian
sudo apt install tmux

# Amazon Linux
sudo yum install tmux
```

### 사용법

**1. 새 세션 시작**
```bash
tmux new -s mm
```
> `mm`은 세션 이름입니다. 원하는 이름으로 바꿔도 됩니다.

**2. 봇 실행**
```bash
python main.py
```

**3. 세션에서 분리 (봇은 계속 실행됨)**
```
1. Ctrl+B 누르고 손 떼기
2. D 누르기
```
> 동시에 누르는 게 아닙니다! 순서대로 누르세요.
> SSH 끊겨도 봇은 계속 돌아갑니다!

**4. 나중에 세션 다시 연결**
```bash
tmux attach -t mm
```
> 대시보드 화면이 그대로 보입니다.

**5. 봇 종료하고 싶을 때**
```bash
tmux attach -t mm    # 세션 연결
Ctrl+C               # 봇 종료
exit                 # 세션 종료
```

### tmux 명령어 요약

| 명령어 | 설명 |
|--------|------|
| `tmux new -s 이름` | 새 세션 시작 |
| `tmux attach -t 이름` | 세션 다시 연결 |
| `tmux ls` | 실행 중인 세션 목록 |
| `tmux kill-session -t 이름` | 세션 강제 종료 |
| `Ctrl+B` → `D` | 세션에서 분리 (detach) |

---

## 문제 해결

### "ModuleNotFoundError" 에러가 나요

의존성이 설치 안 된 것입니다:
```bash
pip install -r requirements.in
```

### ".env 파일을 찾을 수 없어요"

`.env.example`을 `.env`로 복사했는지 확인하세요:
```bash
cp .env.example .env
```

### "config 모듈을 찾을 수 없어요"

`config.example.py`를 `config.py`로 복사했는지 확인하세요:
```bash
cp config.example.py config.py
```

### 봇이 바로 종료돼요

1. `.env`에 `WALLET_ADDRESS`가 제대로 입력됐는지 확인
2. StandX에 담보금(DUSD)이 있는지 확인

---

## 동작 원리

1. **주문 배치**: 현재가 기준 ±SPREAD_BPS 위치에 BUY/SELL 주문
2. **Maker 검증**: Taker가 되면 즉시 취소 (손실 방지)
3. **Drift 모니터링**: 가격 변동 추적
4. **리밸런싱**: 가격이 많이 움직이면 주문 취소 후 재배치
5. **반복**: 위 과정을 계속 반복

---

## 주의사항

- **처음에는 반드시 `MODE = "TEST"`로 테스트하세요!**
- LIVE 모드는 실제 돈이 사용됩니다
- 담보금이 부족하면 주문이 생성되지 않습니다
