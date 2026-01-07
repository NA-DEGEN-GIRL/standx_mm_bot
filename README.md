# StandX Market Making Bot

> **This README is available in:** English | 한국어 | 中文
>
> **이 README는 다음 언어로 제공됩니다:** English | 한국어 | 中文
>
> **本README提供以下语言版本：** English | 한국어 | 中文

---

# [English](#english) | [한국어](#한국어) | [中文](#中文)

---

<a name="english"></a>
# English

## StandX Market Making Bot

An automated market making bot for the StandX perpetual futures exchange.

---

## Disclaimer

> **WARNING: This software is provided AS-IS without any warranty.**
>
> - **All losses incurred from using this bot are solely your responsibility.**
> - This software is **NOT financial advice.** Make your own financial decisions.
> - Cryptocurrency trading involves **risk of loss**, and leverage trading can amplify losses.
> - The developer is **NOT responsible for unexpected behavior** due to bugs, exchange outages, or network issues.
> - **This is a hobby project.** There may be bugs or errors. Use with caution.
> - Only trade with money you can afford to lose.
>
> By using this software, you agree to the above terms.

---

## Quick Start (For First-Time Users)

### Step 1: Check Python Installation

Open terminal and run:

```bash
python --version
```

You should see `Python 3.10.x` or higher. If not, install Python 3.10 first.

### Step 2: Install Dependencies

Navigate to the project folder and run:

```bash
pip install -r requirements.in
```

### Step 3: Create Wallet Configuration File

Copy `.env.example` to `.env`:

**Windows:**
```bash
copy .env.example .env
```

**Mac/Linux:**
```bash
cp .env.example .env
```

Then edit `.env`:

```
WALLET_ADDRESS=0xYOUR_WALLET_ADDRESS_HERE
PRIVATE_KEY=YOUR_PRIVATE_KEY_HERE
```

> **Note**: `PRIVATE_KEY` is optional. If omitted, a browser login window will open.

### Step 4: Create Bot Configuration File

Copy `config.example.py` to `config.py`:

**Windows:**
```bash
copy config.example.py config.py
```

**Mac/Linux:**
```bash
cp config.example.py config.py
```

Then edit `config.py` as needed. (See "Configuration Parameters" section below)

### Step 5: Run the Bot

```bash
python main.py
```

Start with `MODE = "TEST"` to test in simulation mode first!

---

## Updating the Program

**GitHub URL:** https://github.com/pica-lab/standx_mm_bot

### Method 1: Using Git (Recommended)

```bash
# Navigate to project folder
cd standx_mm_bot

# Pull latest version
git pull

# Update dependencies (important!)
pip install -r requirements.in
```

> **Note**: `config.py` and `.env` are in `.gitignore` and won't be overwritten.

### Method 2: Manual Download

1. Download ZIP from GitHub (**Code** → **Download ZIP**)
2. Extract files
3. Overwrite existing folder (but keep `config.py` and `.env`!)
4. Update dependencies:
   ```bash
   pip install -r requirements.in
   ```

---

## Configuration Guide (config.py)

### 1. MODE - Real or Simulation

```python
MODE = "TEST"    # Simulation mode - no real money
MODE = "LIVE"    # Real mode - actual trading!
```

**Always start with "TEST" first!**

---

### 2. AUTO_CONFIRM - Skip YES Confirmation

```python
AUTO_CONFIRM = False   # Requires YES input for LIVE mode
AUTO_CONFIRM = True    # Start immediately
```

---

### 3. SPREAD_BPS - Order Spread

```python
SPREAD_BPS = 8.0    # Place orders 0.08% away from current price
```

**Example:** If BTC is $100,000:
- Buy order: $99,920 (0.08% below)
- Sell order: $100,080 (0.08% above)

Recommended: **5-10**

---

### 4. DRIFT_THRESHOLD - Rebalance Trigger

```python
DRIFT_THRESHOLD = 3.0   # Rebalance when price moves 0.03%
```

Recommended: **2-5**

---

### 5. USE_MID_DRIFT - Consider Mid Price

```python
USE_MID_DRIFT = False   # Only consider mark price drift
USE_MID_DRIFT = True    # Consider mark + mid price drift
```

---

### 6. MARK_MID_DIFF_LIMIT - Wait When Market is Unstable

```python
MARK_MID_DIFF_LIMIT = 0.0   # Disabled (always place orders)
MARK_MID_DIFF_LIMIT = 1.0   # Wait if mark-mid difference > 1bps
```

Recommended: **1.0-2.0** or **0** (always order)

---

### 6-1. MID_UNSTABLE_COOLDOWN - Cooldown After Instability

```python
MID_UNSTABLE_COOLDOWN = 0    # Disabled (order immediately when stable)
MID_UNSTABLE_COOLDOWN = 3.0  # Wait 3 more seconds after becoming stable
```

This helps filter "false stability" after market turbulence.

Recommended: **0** (immediate) or **1-3 seconds** (safer)

---

### 7. LEVERAGE - Leverage Multiplier

```python
LEVERAGE = 6     # 6x leverage
```

Recommended for beginners: **3-6**

---

### 8. MAX_SIZE_BTC - Maximum Order Size

```python
MAX_SIZE_BTC = 0.001    # Max 0.001 BTC per order
MAX_SIZE_BTC = None     # No limit (risky!)
```

Recommended: **0.0001-0.001** to start small

---

### 9. AUTO_CLOSE_POSITION - Auto Close

```python
AUTO_CLOSE_POSITION = True    # Auto close positions
AUTO_CLOSE_POSITION = False   # Keep positions
```

Recommended: **True**

---

### 10. CLOSE_METHOD - Closing Method

```python
CLOSE_METHOD = "market"      # Market order (fast, some slippage)
CLOSE_METHOD = "aggressive"  # Limit order (slower, less slippage)
CLOSE_METHOD = "chase"       # Chase orderbook
```

If unsure: **"market"**

---

### 11. CLOSE_AGGRESSIVE_BPS - Aggressive Mode Setting

```python
CLOSE_AGGRESSIVE_BPS = 5.0   # Place order 0.05% from current price
CLOSE_AGGRESSIVE_BPS = 0     # Place at immediately executable price
```

Only relevant when `CLOSE_METHOD = "aggressive"`

---

### 12. Stability Settings (Don't Touch)

```python
MAX_HISTORY = 1000
MAX_CONSECUTIVE_ERRORS = 10
MIN_WAIT_SEC = 3.0
REFRESH_INTERVAL = 0.05
SIZE_UNIT = 0.0001
```

These are advanced settings. Don't modify unless you know what you're doing!

---

### 13. RESTART_INTERVAL - Auto Restart

```python
RESTART_INTERVAL = 0       # Disabled
RESTART_INTERVAL = 3600    # Restart every 1 hour
RESTART_INTERVAL = 86400   # Restart every 24 hours
```

Useful for long-running bots to prevent memory leaks and connection issues.

Recommended for servers: **3600-86400**, for testing: **0**

---

## Recommended Settings for Beginners

```python
MODE = "TEST"              # Always TEST first!
LEVERAGE = 6
MAX_SIZE_BTC = 0.0001
SPREAD_BPS = 8.0
AUTO_CONFIRM = False
AUTO_CLOSE_POSITION = True
CLOSE_METHOD = "market"
```

---

## Position Log

Positions are logged to `position_log.txt`:

```
2026-01-06 14:30:15 | POSITION DETECTED | LONG 0.005000 BTC @ 97500.00 | uPnL: $+12.50
  → CLOSE iter 1: SELL 0.005000 @ 97499.00 (aggressive)
  → CLOSE iter 1: partial fill 0.005000 -> 0.002000
  → CLOSE iter 2: SELL 0.002000 @ 97498.50 (aggressive)
  → CLOSE iter 2: filled completely
2026-01-06 14:30:21 | POSITION CLOSED  | LONG 0.005000 BTC | PnL: $+12.50 | Method: aggressive | Time: 6.32s (2 iter)
```

---

## Running on Remote Servers (AWS, GCP, etc.)

Use **tmux** to keep the bot running after SSH disconnection:

```bash
# Install tmux
sudo apt install tmux

# Create new session
tmux new -s mm

# Run the bot
python main.py

# Detach: Ctrl+B then D
# Reattach later: tmux attach -t mm
```

---

## Shutdown

Press `Ctrl+C` to stop. In LIVE mode, all orders are automatically cancelled.

---

## How It Works

1. **Order Placement**: Place BUY/SELL orders at ±SPREAD_BPS from current price
2. **Maker Verification**: Cancel if becoming taker (loss prevention)
3. **Drift Monitoring**: Track price movement
4. **Rebalancing**: Cancel and replace orders when price moves too much
5. **Repeat**: Continue the above process

---

## Cautions

- **Always test with `MODE = "TEST"` first!**
- LIVE mode uses real money
- Orders won't be created if collateral is insufficient

### About "REST API skipped" Message

You may occasionally see this message:
```
REST API skipped on. No order at this moment
```
or
```
[StandXExchange] create_order WS failed: balance not enough
```

**This is normal and not a cause for concern.** This happens when orders are placed immediately after cancellation, and the StandX server hasn't updated the balance yet. The bot will automatically retry on the next cycle.

---

<a name="한국어"></a>
# 한국어

## StandX 마켓 메이킹 봇

StandX 무기한 선물 거래소에서 자동으로 마켓메이킹을 수행하는 봇입니다.

---

## 면책조항

> **경고: 이 소프트웨어는 있는 그대로(AS-IS) 제공되며, 어떠한 보증도 하지 않습니다.**
>
> - 이 봇을 사용하여 발생하는 **모든 손실에 대한 책임은 전적으로 사용자에게 있습니다.**
> - 이 소프트웨어는 **투자 조언이 아닙니다.** 재정적 결정은 본인의 판단 하에 내려야 합니다.
> - 암호화폐 거래는 **원금 손실 위험**이 있으며, 레버리지 거래는 손실을 증폭시킬 수 있습니다.
> - 개발자는 버그, 거래소 장애, 네트워크 문제 등으로 인한 **예기치 않은 동작에 대해 책임지지 않습니다.**
> - **이것은 취미로 만드는 프로젝트입니다.** 버그나 오류가 있을 수 있으니 신중하게 사용하세요.
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

**GitHub 주소:** https://github.com/pica-lab/standx_mm_bot

### 방법 1: Git 사용 (추천)

```bash
# 프로젝트 폴더로 이동
cd standx_mm_bot

# 최신 버전 받아오기
git pull

# 의존성 업데이트 (중요!)
pip install -r requirements.in
```

> **주의**: `config.py`와 `.env` 파일은 `.gitignore`에 있어서 덮어쓰지 않습니다.

### 방법 2: 수동 다운로드

1. GitHub에서 **Code** → **Download ZIP** 클릭
2. 압축 풀기
3. 기존 폴더에 덮어쓰기 (`config.py`와 `.env`는 덮어쓰지 마세요!)
4. 의존성 업데이트:
   ```bash
   pip install -r requirements.in
   ```

---

## 설정 방법 (config.py)

### 1. MODE - 진짜 돈 쓸지 말지 (제일 중요!!)

```python
MODE = "TEST"    # 가짜 모드 - 돈 안 씀, 연습용
MODE = "LIVE"    # 진짜 모드 - 실제 돈으로 거래!!
```

**처음엔 무조건 `"TEST"`로 하세요!**

---

### 2. AUTO_CONFIRM - YES 입력 생략

```python
AUTO_CONFIRM = False   # LIVE 모드 시작할 때 YES 입력해야 함
AUTO_CONFIRM = True    # YES 입력 없이 바로 시작
```

---

### 3. SPREAD_BPS - 얼마나 떨어진 가격에 주문할지

```python
SPREAD_BPS = 8.0    # 현재가에서 0.08% 떨어진 곳에 주문
```

**예시:** 비트코인이 $100,000일 때
- 매수 주문: $99,920에 (0.08% 아래)
- 매도 주문: $100,080에 (0.08% 위에)

추천: **5~10 사이**

---

### 4. DRIFT_THRESHOLD - 언제 주문을 다시 넣을지

```python
DRIFT_THRESHOLD = 3.0   # 가격이 0.03% 움직이면 주문 재배치
```

추천: **2~5**

---

### 5. USE_MID_DRIFT - mid price 변동도 고려할지

```python
USE_MID_DRIFT = False   # mark price만 보고 취소 결정
USE_MID_DRIFT = True    # mark price + mid price 둘 다 보고 결정
```

---

### 6. MARK_MID_DIFF_LIMIT - 시장 불안정할 때 주문 대기

```python
MARK_MID_DIFF_LIMIT = 0.0   # 비활성화 (항상 주문)
MARK_MID_DIFF_LIMIT = 1.0   # mark-mid 차이 1bps 이상이면 대기
```

추천: **1.0~2.0** 또는 **0** (항상 주문)

---

### 6-1. MID_UNSTABLE_COOLDOWN - 불안정 후 추가 대기 시간

```python
MID_UNSTABLE_COOLDOWN = 0    # 비활성화 (안정되면 즉시 주문)
MID_UNSTABLE_COOLDOWN = 3.0  # 안정 후 3초 더 기다림
```

"가짜 안정"을 필터링하는 용도입니다.

추천: **0** (바로 주문) 또는 **1~3초** (급변동 후 안전하게)

---

### 7. LEVERAGE - 레버리지 배수

```python
LEVERAGE = 6     # 6배 레버리지
```

추천: 처음엔 **3~6**

---

### 8. MAX_SIZE_BTC - 최대 주문 수량 제한

```python
MAX_SIZE_BTC = 0.001    # 한번에 최대 0.001 BTC만 주문
MAX_SIZE_BTC = None     # 제한 없음 (위험!)
```

추천: **0.0001~0.001**

---

### 9. AUTO_CLOSE_POSITION - 자동 청산

```python
AUTO_CLOSE_POSITION = True    # 포지션 생기면 자동으로 정리
AUTO_CLOSE_POSITION = False   # 포지션 그냥 둠
```

추천: **True**

---

### 10. CLOSE_METHOD - 청산 방법

```python
CLOSE_METHOD = "market"      # 시장가로 즉시 청산 (빠름, 약간 손해)
CLOSE_METHOD = "aggressive"  # 지정가로 청산 (느림, 손해 적음)
CLOSE_METHOD = "chase"       # 호가 따라가며 청산
```

뭘 고를지 모르겠으면: **"market"**

---

### 11. CLOSE_AGGRESSIVE_BPS - aggressive 모드 세부설정

```python
CLOSE_AGGRESSIVE_BPS = 5.0   # 현재가에서 0.05% 떨어진 가격에 주문
CLOSE_AGGRESSIVE_BPS = 0     # 바로 체결되는 가격에 주문
```

`CLOSE_METHOD = "aggressive"` 일 때만 의미있어요.

---

### 12. 안정성 설정 (건드리지 마세요)

```python
MAX_HISTORY = 1000
MAX_CONSECUTIVE_ERRORS = 10
MIN_WAIT_SEC = 3.0
REFRESH_INTERVAL = 0.05
SIZE_UNIT = 0.0001
```

이건 고급 설정이에요. 뭔지 모르면 절대 건드리지 마세요!

---

### 13. RESTART_INTERVAL - 자동 재시작

```python
RESTART_INTERVAL = 0       # 비활성화 (재시작 안 함)
RESTART_INTERVAL = 3600    # 1시간마다 자동 재시작
RESTART_INTERVAL = 86400   # 24시간마다 자동 재시작
```

봇을 오래 돌리면 메모리 누수나 연결 문제가 생길 수 있어요. 이 설정으로 주기적으로 재시작합니다.

추천: 서버에서 **3600~86400**, 테스트할 땐 **0**

---

## 처음 시작하는 사람을 위한 추천 설정

```python
MODE = "TEST"              # 처음엔 무조건 TEST!
LEVERAGE = 6
MAX_SIZE_BTC = 0.0001
SPREAD_BPS = 8.0
AUTO_CONFIRM = False
AUTO_CLOSE_POSITION = True
CLOSE_METHOD = "market"
```

---

## 포지션 로그 기록

포지션이 감지되고 청산될 때마다 `position_log.txt` 파일에 기록됩니다:

```
2026-01-06 14:30:15 | POSITION DETECTED | LONG 0.005000 BTC @ 97500.00 | uPnL: $+12.50
  → CLOSE iter 1: SELL 0.005000 @ 97499.00 (aggressive)
  → CLOSE iter 1: partial fill 0.005000 -> 0.002000
  → CLOSE iter 2: SELL 0.002000 @ 97498.50 (aggressive)
  → CLOSE iter 2: filled completely
2026-01-06 14:30:21 | POSITION CLOSED  | LONG 0.005000 BTC | PnL: $+12.50 | Method: aggressive | Time: 6.32s (2 iter)
```

---

## 원격 서버에서 실행 (AWS, GCP 등)

**tmux**를 사용하면 SSH 끊겨도 봇이 계속 돌아갑니다:

```bash
# tmux 설치
sudo apt install tmux

# 새 세션 시작
tmux new -s mm

# 봇 실행
python main.py

# 세션 분리: Ctrl+B 후 D
# 나중에 다시 연결: tmux attach -t mm
```

---

## 종료 방법

`Ctrl+C`를 누르면 종료됩니다. LIVE 모드에서는 자동으로 모든 주문을 취소합니다.

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

### "REST API skipped" 메시지에 대해

가끔 이런 메시지가 보일 수 있습니다:
```
REST API skipped on. No order at this moment
```
또는
```
[StandXExchange] create_order WS failed: balance not enough
```

**이것은 정상이며 걱정할 필요 없습니다.** 주문 취소 직후 바로 새 주문이 들어갈 때 StandX 서버에서 아직 잔고가 업데이트되지 않아서 발생합니다. 봇이 다음 사이클에서 자동으로 다시 시도합니다.

---

<a name="中文"></a>
# 中文

## StandX 做市机器人

用于 StandX 永续合约交易所的自动做市机器人。

---

## 免责声明

> **警告：本软件按"原样"提供，不提供任何担保。**
>
> - 使用本机器人造成的**所有损失由用户自行承担。**
> - 本软件**不构成投资建议。** 请自行做出财务决策。
> - 加密货币交易存在**本金损失风险**，杠杆交易可能放大损失。
> - 开发者**不对因错误、交易所故障或网络问题导致的意外行为负责。**
> - **这是一个业余爱好项目。** 可能存在错误或Bug，请谨慎使用。
> - 只用**您能承受损失的资金**进行交易。
>
> 使用本软件即表示您同意上述条款。

---

## 快速开始（新手指南）

### 第1步：检查Python安装

打开终端并运行：

```bash
python --version
```

应该显示 `Python 3.10.x` 或更高版本。如果没有，请先安装 Python 3.10。

### 第2步：安装依赖

进入项目文件夹后运行：

```bash
pip install -r requirements.in
```

### 第3步：创建钱包配置文件

将 `.env.example` 复制为 `.env`：

**Windows:**
```bash
copy .env.example .env
```

**Mac/Linux:**
```bash
cp .env.example .env
```

然后编辑 `.env` 文件：

```
WALLET_ADDRESS=0x您的钱包地址
PRIVATE_KEY=您的私钥
```

> **注意**：`PRIVATE_KEY` 可以省略。省略后运行时会打开浏览器登录窗口。

### 第4步：创建机器人配置文件

将 `config.example.py` 复制为 `config.py`：

**Windows:**
```bash
copy config.example.py config.py
```

**Mac/Linux:**
```bash
cp config.example.py config.py
```

然后根据需要编辑 `config.py`。（参见下方"配置参数"部分）

### 第5步：运行

```bash
python main.py
```

首次使用请先设置 `MODE = "TEST"` 在模拟模式下测试！

---

## 程序更新方法

**GitHub地址：** https://github.com/pica-lab/standx_mm_bot

### 方法1：使用Git（推荐）

```bash
# 进入项目文件夹
cd standx_mm_bot

# 拉取最新版本
git pull

# 更新依赖（重要！）
pip install -r requirements.in
```

> **注意**：`config.py` 和 `.env` 在 `.gitignore` 中，不会被覆盖。

### 方法2：手动下载

1. 从GitHub下载ZIP（**Code** → **Download ZIP**）
2. 解压文件
3. 覆盖现有文件夹（但保留 `config.py` 和 `.env`！）
4. 更新依赖：
   ```bash
   pip install -r requirements.in
   ```

---

## 配置指南 (config.py)

### 1. MODE - 真实交易还是模拟

```python
MODE = "TEST"    # 模拟模式 - 不使用真钱
MODE = "LIVE"    # 真实模式 - 实际交易！
```

**新手务必先使用 "TEST"！**

---

### 2. AUTO_CONFIRM - 跳过YES确认

```python
AUTO_CONFIRM = False   # LIVE模式需要输入YES
AUTO_CONFIRM = True    # 直接启动
```

---

### 3. SPREAD_BPS - 订单价差

```python
SPREAD_BPS = 8.0    # 在当前价格的0.08%位置下单
```

**示例：** 如果BTC价格是 $100,000：
- 买单：$99,920（低0.08%）
- 卖单：$100,080（高0.08%）

推荐：**5-10**

---

### 4. DRIFT_THRESHOLD - 重新平衡触发点

```python
DRIFT_THRESHOLD = 3.0   # 价格移动0.03%时重新下单
```

推荐：**2-5**

---

### 5. USE_MID_DRIFT - 考虑中间价

```python
USE_MID_DRIFT = False   # 只考虑标记价格偏移
USE_MID_DRIFT = True    # 同时考虑标记价格和中间价格偏移
```

---

### 6. MARK_MID_DIFF_LIMIT - 市场不稳定时等待

```python
MARK_MID_DIFF_LIMIT = 0.0   # 禁用（始终下单）
MARK_MID_DIFF_LIMIT = 1.0   # mark-mid差异>1bps时等待
```

推荐：**1.0-2.0** 或 **0**（始终下单）

---

### 6-1. MID_UNSTABLE_COOLDOWN - 不稳定后的冷却时间

```python
MID_UNSTABLE_COOLDOWN = 0    # 禁用（稳定后立即下单）
MID_UNSTABLE_COOLDOWN = 3.0  # 稳定后再等3秒
```

用于过滤"假稳定"。

推荐：**0**（立即）或 **1-3秒**（更安全）

---

### 7. LEVERAGE - 杠杆倍数

```python
LEVERAGE = 6     # 6倍杠杆
```

新手推荐：**3-6**

---

### 8. MAX_SIZE_BTC - 最大订单数量

```python
MAX_SIZE_BTC = 0.001    # 每单最多0.001 BTC
MAX_SIZE_BTC = None     # 无限制（危险！）
```

推荐：**0.0001-0.001** 从小开始

---

### 9. AUTO_CLOSE_POSITION - 自动平仓

```python
AUTO_CLOSE_POSITION = True    # 自动平仓
AUTO_CLOSE_POSITION = False   # 保持仓位
```

推荐：**True**

---

### 10. CLOSE_METHOD - 平仓方法

```python
CLOSE_METHOD = "market"      # 市价单（快，有滑点）
CLOSE_METHOD = "aggressive"  # 限价单（慢，滑点少）
CLOSE_METHOD = "chase"       # 追踪订单簿
```

不确定选什么：**"market"**

---

### 11. CLOSE_AGGRESSIVE_BPS - Aggressive模式设置

```python
CLOSE_AGGRESSIVE_BPS = 5.0   # 在当前价格的0.05%位置下单
CLOSE_AGGRESSIVE_BPS = 0     # 在可立即成交的价格下单
```

仅在 `CLOSE_METHOD = "aggressive"` 时有效。

---

### 12. 稳定性设置（请勿修改）

```python
MAX_HISTORY = 1000
MAX_CONSECUTIVE_ERRORS = 10
MIN_WAIT_SEC = 3.0
REFRESH_INTERVAL = 0.05
SIZE_UNIT = 0.0001
```

这些是高级设置。如果不知道是什么，请勿修改！

---

### 13. RESTART_INTERVAL - 自动重启

```python
RESTART_INTERVAL = 0       # 禁用
RESTART_INTERVAL = 3600    # 每1小时重启
RESTART_INTERVAL = 86400   # 每24小时重启
```

长时间运行可能导致内存泄漏和连接问题。此设置可定期重启。

服务器推荐：**3600-86400**，测试时：**0**

---

## 新手推荐设置

```python
MODE = "TEST"              # 务必先TEST！
LEVERAGE = 6
MAX_SIZE_BTC = 0.0001
SPREAD_BPS = 8.0
AUTO_CONFIRM = False
AUTO_CLOSE_POSITION = True
CLOSE_METHOD = "market"
```

---

## 仓位日志

仓位检测和平仓记录保存在 `position_log.txt`：

```
2026-01-06 14:30:15 | POSITION DETECTED | LONG 0.005000 BTC @ 97500.00 | uPnL: $+12.50
  → CLOSE iter 1: SELL 0.005000 @ 97499.00 (aggressive)
  → CLOSE iter 1: partial fill 0.005000 -> 0.002000
  → CLOSE iter 2: SELL 0.002000 @ 97498.50 (aggressive)
  → CLOSE iter 2: filled completely
2026-01-06 14:30:21 | POSITION CLOSED  | LONG 0.005000 BTC | PnL: $+12.50 | Method: aggressive | Time: 6.32s (2 iter)
```

---

## 在远程服务器运行（AWS、GCP等）

使用 **tmux** 可以在SSH断开后保持机器人运行：

```bash
# 安装tmux
sudo apt install tmux

# 创建新会话
tmux new -s mm

# 运行机器人
python main.py

# 分离会话：Ctrl+B 然后 D
# 稍后重新连接：tmux attach -t mm
```

---

## 关闭方法

按 `Ctrl+C` 停止。在LIVE模式下会自动取消所有订单。

---

## 工作原理

1. **下单**：在当前价格的±SPREAD_BPS位置放置买/卖订单
2. **Maker验证**：如果变成Taker则立即取消（防止损失）
3. **偏移监控**：追踪价格变动
4. **重新平衡**：价格大幅移动时取消并重新下单
5. **重复**：持续上述过程

---

## 注意事项

- **务必先用 `MODE = "TEST"` 测试！**
- LIVE模式使用真钱
- 保证金不足时不会创建订单

---
