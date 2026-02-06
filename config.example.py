"""
StandX MM Bot Configuration
"""

# Mode Settings
MODE = "LIVE"           # "TEST" = simulation, "LIVE" = real orders
EXCHANGE = "standx"
COIN = "BTC"
AUTO_CONFIRM = True    # True: skip YES confirmation for LIVE mode

# Order Settings
SPREAD_BPS = 6.5        # Order spread (bps)
DRIFT_THRESHOLD = 3.5   # Rebalance trigger (bps)
USE_MID_AS_MARK = False # True: use mid price instead of mark price for order calculation
MID_PRICE_DEPTH = 1     # Number of orderbook levels for mid price (1 = best only, N = top N weighted avg)
USE_MID_DRIFT = True    # True: mark drift + mid drift combined, False: mark drift only
MARK_MID_DIFF_LIMIT = 1.0  # Wait if mark-mid diff exceeds this (bps), 0 to disable
MID_UNSTABLE_COOLDOWN = 0  # Extra wait after mid unstable (sec), 0 for immediate
SPREAD_UNSTABLE_LIMIT = 0  # Wait if orderbook spread exceeds this (bps), 0 to disable
SPREAD_UNSTABLE_COOLDOWN = 0  # Extra wait after spread unstable (sec), 0 for immediate
MIN_WAIT_SEC = 0.1      # Minimum wait before order modification (sec)
REFRESH_INTERVAL = 0.05 # Screen refresh interval (sec)
CANCEL_AFTER_DELAY = 0.5 # Delay after order cancellation (sec)
INCOMPLETE_ORDER_THRESHOLD = 10  # Cancel if one-sided order detected N times consecutively (0 = immediate)

# Size Settings
SIZE_UNIT = 0.0001      # Order size unit (BTC)
LEVERAGE = 30           # Leverage multiplier (bidirectional, so each side is 1/2)
MAX_SIZE_BTC = 2.0      # Max order size (None = unlimited)

# Stability Settings
MAX_HISTORY = 1000              # Max order history to keep
MAX_CONSECUTIVE_ERRORS = 10     # Max consecutive errors allowed

# Auto Position Close
AUTO_CLOSE_POSITION = True      # True: auto close position and resume MM

# Close Method: "market" | "aggressive" | "chase"
# - market: immediate market close
# - aggressive: limit order at mark price (faster fill)
# - chase: limit order at best bid/ask
CLOSE_METHOD = "aggressive"

# Aggressive Mode Settings
CLOSE_AGGRESSIVE_BPS = 0      # BPS offset from mark price

# Aggressive/Chase Common Settings
CLOSE_WAIT_SEC = 5.0            # Wait time after order (sec)
CLOSE_MIN_SIZE_MARKET = 0.01    # Market close if size below this

# Safety Limits
CLOSE_MAX_ITERATIONS = 20      # Max iterations (market fallback if exceeded)

# Snapshot Settings (for status check without tmux)
SNAPSHOT_INTERVAL = 60         # Snapshot save interval (sec), 0 to disable
SNAPSHOT_FILE = "status.txt"   # Snapshot filename

# Auto Restart
RESTART_INTERVAL = 3600        # Auto restart interval (sec), 0 to disable
RESTART_DELAY = 10             # Delay before restart after cancelling orders (sec)
MAX_WS_FALLBACK = 10           # Force restart if WS fallback count exceeds this, 0 to disable