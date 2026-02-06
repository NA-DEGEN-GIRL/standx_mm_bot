#!/usr/bin/env python3
"""
StandX Market Making Bot
========================
Simulates bidirectional limit orders at ±bps from mark_price.
Real-time monitoring of price and maker/taker status.

Usage:
    python main.py
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import time
import uuid
import logging
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List
from types import SimpleNamespace
from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

from exchange_factory import create_exchange, symbol_create
from dotenv import load_dotenv
from config import (
    MODE, EXCHANGE, COIN, AUTO_CONFIRM,
    SPREAD_BPS, DRIFT_THRESHOLD, USE_MID_AS_MARK, USE_MID_DRIFT, MARK_MID_DIFF_LIMIT, MID_UNSTABLE_COOLDOWN, SPREAD_UNSTABLE_LIMIT, SPREAD_UNSTABLE_COOLDOWN,
    MIN_WAIT_SEC, REFRESH_INTERVAL,
    SIZE_UNIT, LEVERAGE, MAX_SIZE_BTC,
    MAX_HISTORY, MAX_CONSECUTIVE_ERRORS,
    AUTO_CLOSE_POSITION,
    CLOSE_METHOD, CLOSE_AGGRESSIVE_BPS, CLOSE_WAIT_SEC,
    CLOSE_MIN_SIZE_MARKET, CLOSE_MAX_ITERATIONS,
    SNAPSHOT_INTERVAL, SNAPSHOT_FILE, CANCEL_AFTER_DELAY,
    RESTART_INTERVAL, RESTART_DELAY, MAX_WS_FALLBACK,
)

load_dotenv()

# ==================== Logging Setup ====================
LOG_FILE = "position_log.txt"
CONSOLE_LOG_FILE = "console_log.txt"

# File logger setup (for position tracking)
file_logger = logging.getLogger("position")
file_logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
file_logger.addHandler(file_handler)


# Console log file (cleared on startup)
_console_log_file = open(CONSOLE_LOG_FILE, "w", encoding="utf-8")

# Keyboard interrupt flag (for auto-restart logic)
_keyboard_interrupted = False


def log_message(message: str) -> None:
    """Log message to console_log.txt with timestamp"""
    # 파일이 닫혔는지 확인 후 쓰기 시도
    if _console_log_file.closed:
        return
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _console_log_file.write(f"[{timestamp}] {message}\n")
        _console_log_file.flush()
    except ValueError:
        # I/O operation on closed file 에러 무시
        pass

STANDX_KEY = SimpleNamespace(
    wallet_address=os.getenv("WALLET_ADDRESS"),
    chain='bsc',
    evm_private_key=os.getenv("PRIVATE_KEY"),
    open_browser=True,
)

console = Console()

# ==================== Position Statistics ====================
position_stats = {
    "total_closes": 0,       # Total number of closes
    "total_volume": 0.0,     # Total closed BTC volume
    "total_pnl": 0.0,        # Total realized PnL (USD)
    "last_close_time": 0.0,  # Last close elapsed time (sec)
    "total_close_time": 0.0, # Total close elapsed time (sec)
}


# ==================== Simulated Orders ====================

@dataclass
class SimOrder:
    """Simulated order"""
    id: str
    side: str  # "buy" or "sell"
    price: float
    size: float
    status: str = "open"  # "open", "filled", "cancelled"
    placed_at: datetime = field(default_factory=datetime.now)
    reference_price: float = 0.0  # mark_price at order placement
    message: str = ""
    
class SimOrderManager:
    """Simulation order manager"""

    def __init__(self):
        self.orders: Dict[str, SimOrder] = {}
        self.history: List[Dict[str, Any]] = []  # Order history
        self.total_placed = 0
        self.total_cancelled = 0
        self.total_rebalanced = 0
        self.is_live = False

    def _append_history(self, record: Dict[str, Any]) -> None:
        """Append to history (with memory limit)"""
        self.history.append(record)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    async def place_order(self, side: str, price: float, size: float, reference_price: float) -> SimOrder:
        """Create order (simulation)"""
        order_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"
        order = SimOrder(
            id=order_id,
            side=side,
            price=price,
            size=size,
            reference_price=reference_price,
            message="success"
        )
        self.orders[order_id] = order
        self.total_placed += 1
        self._append_history({
            "action": "PLACE",
            "order_id": order_id,
            "side": side,
            "price": price,
            "time": datetime.now()
        })
        return order

    async def cancel_order(self, order_id: str, reason: str = "") -> bool:
        """Cancel order (simulation)"""
        if order_id in self.orders:
            self.orders[order_id].status = "cancelled"
            del self.orders[order_id]
            self.total_cancelled += 1
            self._append_history({
                "action": "CANCEL",
                "order_id": order_id,
                "reason": reason,
                "time": datetime.now()
            })
            return True
        return False

    async def cancel_all(self, reason: str = "") -> int:
        """Cancel all orders (simulation)"""
        count = len(self.orders)
        for order_id in list(self.orders.keys()):
            await self.cancel_order(order_id, reason)
        return count

    def get_open_orders(self) -> List[SimOrder]:
        """Get list of open orders"""
        return list(self.orders.values())

    def get_buy_order(self) -> Optional[SimOrder]:
        """Get BUY order"""
        for order in self.orders.values():
            if order.side == "buy":
                return order
        return None

    def get_sell_order(self) -> Optional[SimOrder]:
        """Get SELL order"""
        for order in self.orders.values():
            if order.side == "sell":
                return order
        return None

    def rebalance(self) -> None:
        """Increment rebalance counter"""
        self.total_rebalanced += 1


class LiveOrderManager:
    """Live order manager (LIVE mode) - Uses server data directly"""

    def __init__(self, exchange, symbol: str):
        self.exchange = exchange
        self.symbol = symbol
        # Only store reference_price locally (for drift calculation, server doesn't know this)
        self.reference_prices: Dict[str, float] = {}  # side -> reference_price
        self.history: List[Dict[str, Any]] = []
        self.total_placed = 0
        self.total_cancelled = 0
        self.total_rebalanced = 0
        self.is_live = True
        # Cached server orders (updated on get_orders_from_server call)
        self._cached_orders: Dict[str, Dict] = {}  # side -> server order

    def _append_history(self, record: Dict[str, Any]) -> None:
        """Append to history (with memory limit)"""
        self.history.append(record)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    async def place_order(self, side: str, price: float, size: float, reference_price: float) -> Optional[SimOrder]:
        """Create live order"""
        try:
            cl_ord_id = f"MM-{uuid.uuid4().hex[:8].upper()}"

            result = await self.exchange.create_order(
                symbol=self.symbol,
                side=side,
                amount=size,
                price=price,
                order_type="limit",
                client_order_id=cl_ord_id,
                skip_rest=True
            )
            if result:
                code = result.get("code", None)
            else:
                code = None
            if code == 0:
                # Store reference_price (for drift calculation)
                self.reference_prices[side] = reference_price
                self.total_placed += 1
                self._append_history({
                    "action": "PLACE",
                    "order_id": cl_ord_id,
                    "side": side,
                    "price": price,
                    "time": datetime.now()
                })
                message = result.get("message")
                # Return SimOrder (for compatibility)
                return SimOrder(
                    id=cl_ord_id,
                    side=side,
                    price=price,
                    size=size,
                    reference_price=reference_price,
                    message=message
                )
            else:
                console.print(f"[red]Order rejected: {result}[/red]")
        except Exception as e:
            console.print(f"[red]Order failed: {e}[/red]")
        return None

    async def cancel_all(self, reason: str = "") -> int:
        """Cancel cached orders only (no conflict with newly created orders)"""
        try:
            orders_to_cancel = list(self._cached_orders.values())
            
            if orders_to_cancel:
                # Cancel each order individually using staggered_gather
                cancel_coros = []
                for order in orders_to_cancel:
                    order_id = order.get("id") or order.get("cl_ord_id")
                    if order_id:
                        cancel_coros.append(self.exchange.cancel_order(order_id=order_id))
                if cancel_coros:
                    await staggered_gather(*cancel_coros)
            count = len(orders_to_cancel)
            self.total_cancelled += count
            if count > 0:
                self._append_history({
                    "action": "CANCEL_ALL",
                    "count": count,
                    "reason": reason,
                    "time": datetime.now()
                })
            self.reference_prices.clear()
            self._cached_orders.clear()
            return count
        except Exception as e:
            console.print(f"[red]Cancel all failed: {e}[/red]")
            self.reference_prices.clear()
            self._cached_orders.clear()
            return 0

    async def fetch_orders(self) -> None:
        """Fetch orders from server and update cache"""
        try:
            real_orders = await self.exchange.get_open_orders(self.symbol)
            self._cached_orders.clear()
            for ro in real_orders:
                side = ro.get("side", "").lower()
                if side in ("buy", "sell"):
                    self._cached_orders[side] = ro
        except Exception as e:
            console.print(f"[yellow]Fetch orders warning: {e}[/yellow]")

    def get_buy_order(self) -> Optional[SimOrder]:
        """Get BUY order (from cached server data)"""
        server_order = self._cached_orders.get("buy")
        if server_order:
            return SimOrder(
                id=server_order.get("client_order_id", server_order.get("order_id", "")),
                side="buy",
                price=float(server_order.get("price", 0)),
                size=float(server_order.get("size", server_order.get("amount", 0))),
                reference_price=self.reference_prices.get("buy", 0)
            )
        return None

    def get_sell_order(self) -> Optional[SimOrder]:
        """Get SELL order (from cached server data)"""
        server_order = self._cached_orders.get("sell")
        if server_order:
            return SimOrder(
                id=server_order.get("client_order_id", server_order.get("order_id", "")),
                side="sell",
                price=float(server_order.get("price", 0)),
                size=float(server_order.get("size", server_order.get("amount", 0))),
                reference_price=self.reference_prices.get("sell", 0)
            )
        return None

    def rebalance(self) -> None:
        """Increment rebalance counter"""
        self.total_rebalanced += 1

# ==================== Utility Functions ====================

async def staggered_gather(*coros, delay: float = 0):
    """
    Execute coroutines in parallel with slight delays between starts.
    Prevents WS message flooding.
    delay=0 is equivalent to regular asyncio.gather.

    Args:
        *coros: Coroutines to execute
        delay: Interval between coroutine starts (sec), 0 to skip

    Returns:
        List of results from all coroutines
    """
    tasks = []
    for i, coro in enumerate(coros):
        if delay > 0 and i > 0:
            await asyncio.sleep(delay)
        tasks.append(asyncio.create_task(coro))
    return await asyncio.gather(*tasks)


def calc_order_prices(mark_price: float, spread_bps: float) -> Tuple[float, float]:
    """
    Calculate order prices at ±spread_bps from mark_price

    Returns:
        (buy_price, sell_price)
    """
    buy_price = mark_price * (1 - spread_bps / 10000)
    sell_price = mark_price * (1 + spread_bps / 10000)
    return buy_price, sell_price


def check_maker_taker(
    buy_price: float,
    sell_price: float,
    best_bid: float,
    best_ask: float
) -> Tuple[bool, bool]:
    """
    Determine if order is maker or taker

    Returns:
        (buy_is_maker, sell_is_maker)
    """
    # buy order: maker if price < best_ask (inside the orderbook)
    buy_is_maker = buy_price < best_ask
    # sell order: maker if price > best_bid (inside the orderbook)
    sell_is_maker = sell_price > best_bid
    return buy_is_maker, sell_is_maker


def calc_drift_bps(current_price: float, reference_price: float) -> float:
    """
    Calculate the difference between current price and reference price in bps
    """
    if reference_price == 0:
        return 0.0
    return abs(current_price - reference_price) / reference_price * 10000


def calc_spread_bps(best_bid: float, best_ask: float) -> float:
    """
    Calculate orderbook spread in bps
    """
    if best_bid == 0:
        return 0.0
    mid = (best_bid + best_ask) / 2
    return (best_ask - best_bid) / mid * 10000


def format_price(price: float, decimals: int = 2) -> str:
    """Format price with thousand separators"""
    return f"{price:,.{decimals}f}"


def calc_order_size(
    available_collateral: float,
    mark_price: float,
    leverage: float = LEVERAGE,
    size_unit: float = SIZE_UNIT,
    max_size: Optional[float] = MAX_SIZE_BTC
) -> float:
    """
    Calculate order size based on collateral.

    Args:
        available_collateral: Available collateral (USD)
        mark_price: Current mark price
        leverage: Leverage multiplier (6x -> 3x each side for bidirectional)
        size_unit: Minimum order unit (default 0.001 BTC)
        max_size: Manual max size limit (None for unlimited)

    Returns:
        Order size (BTC), floored to size_unit

    Example:
        $100 collateral, BTC=$100k, leverage=6
        -> $100 * 6 / 2 / $100k = 0.003 BTC per side
    """
    if mark_price <= 0 or available_collateral <= 0:
        return 0.0

    # collateral * leverage / 2 (bidirectional) / mark_price
    # Example: $100 * 6 / 2 / $100k = 0.003 BTC per side
    collateral_based_size = available_collateral * leverage / 2 / mark_price

    # Use smaller of collateral-based or max_size if set
    if max_size is not None and max_size > 0:
        size = min(collateral_based_size, max_size)
    else:
        size = collateral_based_size

    # Floor to size_unit (e.g., 0.00367 -> 0.003)
    # Use round to handle floating-point precision
    size = round(size / size_unit) * size_unit

    return round(size, 8)  # Final precision fix


# ==================== Strategic Position Close ====================

async def close_position_strategic(
    exchange,
    symbol: str,
    position: Dict[str, Any],
    method: str,
    aggressive_bps: float,
    wait_sec: float,
    min_size_market: float,
    max_iterations: int,
) -> Tuple[bool, float, int, str]:
    """
    Strategic position close.

    Args:
        exchange: Exchange wrapper instance
        symbol: Trading symbol
        position: Position info {'size', 'side'}
        method: "market", "aggressive", "chase"
        aggressive_bps: BPS for aggressive mode
        wait_sec: Wait time (sec)
        min_size_market: Min size for market fallback
        max_iterations: Max retry iterations

    Returns:
        (success, elapsed_time, iterations, log_message)
    """
    pos_side = position.get("side", "").lower()
    remaining_size = abs(float(position.get("size", 0)))
    close_side = "sell" if pos_side in ["long", "buy"] else "buy"

    start_time = time.time()
    iterations = 0

    # Market close - immediate market order
    if method == "market":
        file_logger.info(f"  → CLOSE: MARKET order {close_side.upper()} {remaining_size:.6f}")
        await exchange.close_position(symbol, position)
        elapsed = time.time() - start_time
        return (True, elapsed, 1, f"MARKET close ({elapsed:.2f}s)")

    # Limit order close loop (aggressive or chase)
    while remaining_size > 0:
        iterations += 1

        # Max iterations exceeded - force market close
        if iterations > max_iterations:
            file_logger.info(f"  → CLOSE iter {iterations}: max iterations exceeded, MARKET fallback {remaining_size:.6f}")
            await exchange.create_order(
                symbol=symbol,
                side=close_side,
                amount=remaining_size,
                order_type="market",
                is_reduce_only=True,
            )
            elapsed = time.time() - start_time
            return (True, elapsed, iterations, f"{method.upper()} close - max iterations exceeded, market fallback ({elapsed:.1f}s)")

        # Remaining size too small - market close
        if remaining_size < min_size_market:
            file_logger.info(f"  → CLOSE iter {iterations}: dust {remaining_size:.6f} < {min_size_market}, MARKET fallback")
            await exchange.create_order(
                symbol=symbol,
                side=close_side,
                amount=remaining_size,
                order_type="market",
                is_reduce_only=True,
            )
            elapsed = time.time() - start_time
            return (True, elapsed, iterations, f"{method.upper()} close - dust market fallback ({elapsed:.1f}s, {iterations} iter)")

        # Calculate limit price based on method
        limit_price = None

        if method == "aggressive":
            if aggressive_bps == 0:
                # BPS=0 means use best price for immediate fill (like market order)
                orderbook = await exchange.get_orderbook(symbol)
                bids = orderbook.get("bids", [])
                asks = orderbook.get("asks", [])
                if close_side == "sell":
                    # LONG close: sell at best_bid -> immediate fill
                    limit_price = bids[0][0] if bids else None
                else:
                    # SHORT close: buy at best_ask -> immediate fill
                    limit_price = asks[0][0] if asks else None

                # No orderbook data - fallback to mark_price (avoid market order)
                if limit_price is None:
                    limit_price = float(await exchange.get_mark_price(symbol))
            else:
                mark_price = float(await exchange.get_mark_price(symbol))
                if close_side == "sell":
                    # LONG close: sell at lower price (faster fill)
                    limit_price = mark_price * (1 - aggressive_bps / 10000)
                else:
                    # SHORT close: buy at higher price (faster fill)
                    limit_price = mark_price * (1 + aggressive_bps / 10000)

        elif method == "chase":
            orderbook = await exchange.get_orderbook(symbol)
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            if close_side == "sell":
                # LONG close: sell at best_ask
                limit_price = asks[0][0] if asks else None
            else:
                # SHORT close: buy at best_bid
                limit_price = bids[0][0] if bids else None

            # No orderbook data - market fallback
            if limit_price is None:
                file_logger.info(f"  → CLOSE iter {iterations}: no orderbook, MARKET fallback {remaining_size:.6f}")
                await exchange.create_order(
                    symbol=symbol,
                    side=close_side,
                    amount=remaining_size,
                    order_type="market",
                    is_reduce_only=True,
                )
                elapsed = time.time() - start_time
                return (True, elapsed, iterations, f"CHASE close - no orderbook, market fallback ({elapsed:.1f}s)")

        # Create limit order
        cl_ord_id = f"CLOSE-{uuid.uuid4().hex[:8].upper()}"
        file_logger.info(f"  → CLOSE iter {iterations}: {close_side.upper()} {remaining_size:.6f} @ {limit_price:,.2f} ({method})")
        console.print(f"[dim]Close order: {close_side.upper()} {remaining_size:.6f} @ {limit_price:,.2f}[/dim]")
        try:
            await exchange.create_order(
                symbol=symbol,
                side=close_side,
                amount=remaining_size,
                price=limit_price,
                order_type="limit",
                is_reduce_only=True,
                client_order_id=cl_ord_id,
            )
        except Exception as e:
            # Order failed - retry in next iteration
            file_logger.info(f"  → CLOSE iter {iterations}: order failed - {e}, retrying...")
            console.print(f"[yellow]Close order failed: {e}, retrying...[/yellow]")
            await asyncio.sleep(1.0)
            continue

        # Poll for fill confirmation (0.01s interval, up to wait_sec)
        poll_interval = 0.01
        poll_start = time.time()
        filled = False

        while (time.time() - poll_start) < wait_sec:
            await asyncio.sleep(poll_interval)

            # Check position
            new_position = await exchange.get_position(symbol)
            if new_position is None or float(new_position.get("size", 0)) == 0:
                # Fully closed
                elapsed = time.time() - start_time
                file_logger.info(f"  → CLOSE iter {iterations}: filled completely")
                return (True, elapsed, iterations, f"{method.upper()} close complete ({elapsed:.1f}s, {iterations} iter)")

            # Check remaining size
            new_remaining = abs(float(new_position.get("size", 0)))
            if new_remaining < remaining_size:
                # Partial fill occurred
                file_logger.info(f"  → CLOSE iter {iterations}: partial fill {remaining_size:.6f} -> {new_remaining:.6f}")
                console.print(f"[dim]Partial fill: {remaining_size:.6f} -> {new_remaining:.6f}[/dim]")
                remaining_size = new_remaining
                filled = True

        # Timeout with unfilled - cancel and retry
        if not filled:
            remaining_size = abs(float((await exchange.get_position(symbol) or {}).get("size", 0)))
            if remaining_size > 0:
                file_logger.info(f"  → CLOSE iter {iterations}: timeout, cancelling and retry (remaining: {remaining_size:.6f})")

        # Cancel unfilled order
        try:
            await exchange.cancel_order(client_order_id=cl_ord_id)
        except Exception:
            pass  # Already filled or cancelled

    elapsed = time.time() - start_time
    return (True, elapsed, iterations, f"{method.upper()} close complete ({elapsed:.1f}s, {iterations} iter)")


# ==================== Dashboard Output (Rich) ====================

def build_dashboard(
    symbol: str,
    mark_price: float,
    ref_price: float,
    best_bid: float,
    best_ask: float,
    best_bid_size: float,
    best_ask_size: float,
    buy_is_maker: bool,
    sell_is_maker: bool,
    drift_bps: float,
    status: str,
    countdown: float,
    spread_bps: float,
    order_mgr,  # SimOrderManager or LiveOrderManager
    available_collateral: float,
    total_collateral: float,
    order_size: float,
    position: Optional[Dict[str, Any]],
    pos_stats: Dict[str, Any],
    last_action: str = "",
    mode: str = "TEST"
) -> Panel:
    """Build dashboard as rich Panel"""
    from rich.table import Table
    from rich.text import Text

    now = datetime.now().strftime("%H:%M:%S")
    is_live = mode == "LIVE"

    # Get current orders
    buy_order = order_mgr.get_buy_order()
    sell_order = order_mgr.get_sell_order()

    # Calculate order value (USD)
    order_value = order_size * mark_price

    # ========== Main Table ==========
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="left")
    table.add_column(justify="left")

    # -- Header --
    header = Text()
    header.append(f"Symbol: ", style="bold")
    header.append(f"{symbol}", style="bold cyan")
    header.append(f"    Time: {now}    Target: ±{SPREAD_BPS}bps")
    table.add_row(header, "")
    table.add_row("", "")

    # -- ACCOUNT Section --
    table.add_row(Text("▌ ACCOUNT", style="bold cyan"), "")
    table.add_row(
        Text(f"  Total: ${total_collateral:,.2f}  Available: ${available_collateral:,.2f}", style="green"),
        Text(f"  Order Size: {order_size:.4f} {COIN} (${order_value:,.2f}) x{LEVERAGE:.0f}", style="bold")
    )

    # Position display
    if position and position.get("size", 0) != 0:
        pos_side = position.get("side", "").upper()
        pos_size = float(position.get("size", 0))
        pos_entry = float(position.get("entry_price", 0))
        pos_upnl = float(position.get("unrealized_pnl", 0))
        pos_color = "green" if pos_side == "LONG" else "red"
        upnl_color = "green" if pos_upnl >= 0 else "red"
        pos_text = Text("  Position: ")
        pos_text.append(f"{pos_side} ", style=pos_color)
        pos_text.append(f"{pos_size:.4f} @ {format_price(pos_entry)}  uPnL: ")
        pos_text.append(f"${pos_upnl:+,.2f}", style=upnl_color)
    else:
        pos_text = Text("  Position: No position", style="dim")
    table.add_row(pos_text, "")
    table.add_row("", "")

    # -- MARKET DATA Section --
    table.add_row(Text("▌ MARKET DATA", style="bold cyan"), "")
    # Mid price (size-weighted average)
    total_size = best_bid_size + best_ask_size
    mid_price = (best_bid * best_bid_size + best_ask * best_ask_size) / total_size if total_size > 0 else (best_bid + best_ask) / 2
    mid_diff_bps = (mid_price - mark_price) / mark_price * 10000 if mark_price > 0 else 0
    mid_diff_style = "green" if abs(mid_diff_bps) < 3 else ("yellow" if abs(mid_diff_bps) < 6 else "red")

    # Spread color
    if spread_bps < 5:
        spread_style = "green"
    elif spread_bps < 10:
        spread_style = "yellow"
    else:
        spread_style = "red"
    drift_style = "yellow" if drift_bps > DRIFT_THRESHOLD else "green"

    # Aligned output (fixed width 12 chars)
    table.add_row(Text(f"  Mark:   {format_price(mark_price):>12}  │  Mid:    {format_price(mid_price):>12}"), "")
    table.add_row(Text(f"  Bid:    {format_price(best_bid):>12}  │  Ask:    {format_price(best_ask):>12}"), "")
    spread_line = Text(f"  Spread: ")
    spread_line.append(f"{spread_bps:.2f} bps".rjust(12), style=spread_style)
    spread_line.append(f"  │  Drift:  ")
    spread_line.append(f"{drift_bps:.2f}".rjust(6), style=drift_style)
    spread_line.append(" / ")
    spread_line.append(f"{mid_diff_bps:+.2f} bps", style=mid_diff_style)
    table.add_row(spread_line, "")
    table.add_row("", "")

    # -- SIMULATED ORDERS Section --
    table.add_row(Text("▌ SIMULATED ORDERS", style="bold cyan"), "")

    # SELL Order (displayed above)
    sell_maker_text = Text("[MAKER]", style="green") if sell_is_maker else Text("[TAKER]", style="red")
    if sell_order:
        sell_drift = calc_drift_bps(ref_price, sell_order.reference_price)
        sell_line = Text("  SELL: ", style="red")
        sell_line.append("● OPEN  ", style="red bold")
        sell_line.append(f"{sell_order.id}  @ {format_price(sell_order.price)}  x{sell_order.size}")
        sell_drift_text = Text(f"        (drift: {sell_drift:.1f}bps)  ")
    else:
        sell_line = Text("  SELL: ", style="red")
        sell_line.append("○ No order", style="dim")
        sell_drift_text = Text("        ")
    sell_drift_text.append_text(sell_maker_text)
    table.add_row(sell_line, "")
    table.add_row(sell_drift_text, "")

    # BUY Order (displayed below)
    buy_maker_text = Text("[MAKER]", style="green") if buy_is_maker else Text("[TAKER]", style="red")
    if buy_order:
        buy_drift = calc_drift_bps(ref_price, buy_order.reference_price)
        buy_line = Text("  BUY:  ", style="green")
        buy_line.append("● OPEN  ", style="green bold")
        buy_line.append(f"{buy_order.id}  @ {format_price(buy_order.price)}  x{buy_order.size}")
        buy_drift_text = Text(f"        (drift: {buy_drift:.1f}bps)  ")
    else:
        buy_line = Text("  BUY:  ", style="green")
        buy_line.append("○ No order", style="dim")
        buy_drift_text = Text("        ")
    buy_drift_text.append_text(buy_maker_text)
    table.add_row(buy_line, "")
    table.add_row(buy_drift_text, "")
    table.add_row("", "")

    # -- STATUS Section --
    table.add_row(Text("▌ STATUS", style="bold cyan"), "")

    # Status color
    if status == "MONITORING":
        status_text = Text("● MONITORING - Orders active", style="green bold")
    elif status == "PLACING":
        status_text = Text("▶ PLACING orders...", style="cyan bold")
    elif status == "NO_SIZE":
        status_text = Text("✗ NO SIZE - Insufficient collateral", style="red bold")
    elif status == "WAITING":
        status_text = Text("◌ WAITING - Would be TAKER", style="yellow bold")
    elif status == "MID_WAIT":
        status_text = Text("◌ MID_WAIT - Mid drift unstable", style="yellow bold")
    elif status == "SPREAD_WAIT":
        status_text = Text("◌ SPREAD_WAIT - Spread too wide", style="yellow bold")
    elif status == "REBALANCING":
        status_text = Text("⟳ REBALANCING - Cancelling & replacing", style="yellow bold")
    else:
        status_text = Text(status)

    table.add_row(Text("  ").append_text(status_text), "")

    if last_action:
        table.add_row(Text(f"  Last: {last_action}", style="dim"), "")

    if countdown > 0 and MIN_WAIT_SEC > 0:
        countdown_str = f"{countdown:.1f}s" if countdown < 10 else f"{int(countdown)}s"
        table.add_row(Text(f"  Next check in: {countdown_str}", style="dim"), "")

    table.add_row("", "")

    # -- STATS Section --
    pnl_style = "green" if pos_stats['total_pnl'] >= 0 else "red"

    # First line: Order statistics
    stats_line1 = Text(
        f"Placed: {order_mgr.total_placed}  Cancelled: {order_mgr.total_cancelled}  Rebalanced: {order_mgr.total_rebalanced}",
        style="dim"
    )
    table.add_row(stats_line1, "")

    # Second line: Close statistics
    stats_line2 = Text(f"Closes: {pos_stats['total_closes']} (", style="dim")
    stats_line2.append(f"{pos_stats['total_volume']:.4f} BTC", style="dim")
    stats_line2.append(", ", style="dim")
    stats_line2.append(f"${pos_stats['total_pnl']:+.2f}", style=pnl_style)
    # Close time display
    if pos_stats.get('total_close_time', 0) > 0:
        stats_line2.append(f", total: {pos_stats['total_close_time']:.1f}s", style="dim")
    if pos_stats.get('last_close_time', 0) > 0:
        stats_line2.append(f", last: {pos_stats['last_close_time']:.1f}s", style="dim")
    stats_line2.append(")", style="dim")
    table.add_row(stats_line2, "")

    # Wrap in Panel
    if is_live:
        title = "[bold red]StandX Market Making [LIVE][/bold red]"
        border = "red"
    else:
        title = "[bold cyan]StandX Market Making [TEST][/bold cyan]"
        border = "cyan"

    return Panel(
        table,
        title=title,
        subtitle="[dim]Press Ctrl+C to exit[/dim]",
        border_style=border
    )


# ==================== Main Logic ====================

async def main():
    is_live = MODE == "LIVE"
    mode_str = "[red]LIVE[/red]" if is_live else "[cyan]TEST[/cyan]"

    # Log startup
    log_message(f"Bot started | Mode: {MODE} | Coin: {COIN} | Spread: {SPREAD_BPS}bps | Drift: {DRIFT_THRESHOLD}bps")

    console.print(f"\n{'='*60}")
    console.print(f"  StandX Market Making Bot")
    console.print(f"  Mode: {mode_str}")
    mid_drift_str = "+mid" if USE_MID_DRIFT else ""
    console.print(f"  Coin: {COIN}, Spread: {SPREAD_BPS}bps, Drift: {DRIFT_THRESHOLD}bps{mid_drift_str}, MarkMidLimit: {MARK_MID_DIFF_LIMIT}bps")
    console.print(f"{'='*60}\n")

    # LIVE mode confirmation
    if is_live:
        console.print("[bold red]WARNING: LIVE MODE - Real orders will be placed![/bold red]")
        console.print(f"  Max Size: {MAX_SIZE_BTC} {COIN}")
        console.print(f"  Leverage: {LEVERAGE}x")
        if AUTO_CONFIRM:
            console.print("[yellow]AUTO_CONFIRM enabled, skipping confirmation...[/yellow]")
        else:
            confirm = input("\nType 'YES' to confirm: ")
            if confirm != "YES":
                console.print("[yellow]Aborted.[/yellow]")
                return



    # Exchange initialization
    console.print("Initializing exchange...")
    exchange = await create_exchange(EXCHANGE, STANDX_KEY)
    symbol = symbol_create(EXCHANGE, COIN)
    console.print(f"Symbol: {symbol}")
    try:
        res = await exchange.update_leverage(symbol)
        console.print(f"Updated to max leverage! {res}")
    except Exception as e:
        console.print(f"Failed to update to max leverage.")

    # Create order manager (based on mode)
    if is_live:
        order_mgr = LiveOrderManager(exchange, symbol)
        console.print("[red]Using LIVE order manager[/red]")
    else:
        order_mgr = SimOrderManager()
        console.print("[cyan]Using SIMULATED order manager[/cyan]")

    last_action = ""

    try:
        # Start WS subscriptions
        console.print("Subscribing to price and orderbook...")
        if exchange.ws_client:
            await exchange.ws_client.subscribe_price(symbol)
            await exchange.ws_client.subscribe_orderbook(symbol)

        # Wait for initial data
        console.print("Waiting for initial data...")
        await asyncio.sleep(2)

        # LIVE mode: Fetch existing orders
        if is_live:
            console.print("Fetching existing orders...")
            await order_mgr.fetch_orders()

        # Track order existence time
        orders_exist_since: Optional[float] = None  # When orders started existing
        countdown = float(MIN_WAIT_SEC)

        # Consecutive error tracking
        consecutive_errors = 0

        # Snapshot tracking
        last_snapshot_time = 0.0

        # Collateral related (REST API available, refresh only when needed)
        available_collateral = 0.0
        total_collateral = 0.0
        need_collateral_update = True  # True only on start + after close

        # Auto restart tracking
        start_time = time.time()

        # Mid unstable cooldown tracking
        last_mid_unstable_time = 0.0

        # Spread unstable cooldown tracking
        last_spread_unstable_time = 0.0

        # Main loop (flicker-free update with Live context)
        with Live(console=console, refresh_per_second=10, transient=True) as live:
            while True:
                try:
                    current_time = time.time()

                    # Auto restart check (time-based)
                    if RESTART_INTERVAL > 0 and (current_time - start_time) >= RESTART_INTERVAL:
                        log_message(f"AUTO RESTART | Interval: {RESTART_INTERVAL}s")
                        console.print(f"\n[yellow]Restarting after {RESTART_INTERVAL}s...[/yellow]")
                        if is_live:
                            await order_mgr.cancel_all(reason="auto_restart")
                            await order_mgr.exchange.close()
                            console.print(f"[green]All orders cancelled before restart...{RESTART_DELAY}s remains.[/green]")
                            await asyncio.sleep(RESTART_DELAY)
                        file_logger.info(f"AUTO RESTART | Interval: {RESTART_INTERVAL}s")
                        os.execv(sys.executable, [sys.executable] + sys.argv)

                    # WS fallback check (force restart if too many REST fallbacks)
                    if MAX_WS_FALLBACK > 0:
                        fallback_stats = exchange.get_fallback_stats()
                        ws_total = fallback_stats.get("ws_client", {}).get("total", 0)
                        order_ws_total = fallback_stats.get("order_ws_client", {}).get("total", 0)
                        if ws_total >= MAX_WS_FALLBACK or order_ws_total >= MAX_WS_FALLBACK:
                            log_message(f"FORCE RESTART | WS fallback exceeded (ws: {ws_total}, order_ws: {order_ws_total})")
                            console.print(f"\n[red]WS fallback limit exceeded (ws: {ws_total}, order_ws: {order_ws_total})[/red]")
                            console.print("[yellow]Force restarting to restore WS connection...[/yellow]")
                            if is_live:
                                await order_mgr.cancel_all(reason="ws_fallback_limit_exceeded")
                                await order_mgr.exchange.close()
                                console.print(f"[green]All orders cancelled before restart...{RESTART_DELAY}s remains.[/green]")
                                await asyncio.sleep(RESTART_DELAY)
                            file_logger.info(f"FORCE RESTART | WS fallback exceeded (ws: {ws_total}, order_ws: {order_ws_total})")
                            os.execv(sys.executable, [sys.executable] + sys.argv)

                    # Collateral refresh (on start or after close)
                    if need_collateral_update:
                        need_collateral_update = False
                        collateral = await exchange.get_collateral()
                        available_collateral = float(collateral.get("available_collateral", 0))
                        total_collateral = float(collateral.get("total_collateral", 0))

                    # ========== 0. LIVE mode: Fetch orders from server ==========
                    if is_live:
                        await order_mgr.fetch_orders()

                    # ========== 1. Fetch real-time data ==========
                    # Get mark_price
                    mark_price_str = await exchange.get_mark_price(symbol)
                    mark_price = float(mark_price_str)

                    # Data validation: mark_price
                    if mark_price <= 0:
                        await asyncio.sleep(REFRESH_INTERVAL)
                        continue

                    # Get orderbook
                    orderbook = await exchange.get_orderbook(symbol)
                    bids = orderbook.get("bids", [])
                    asks = orderbook.get("asks", [])

                    # Data validation: orderbook
                    if not bids or not asks:
                        await asyncio.sleep(REFRESH_INTERVAL)
                        continue

                    best_bid = bids[0][0]
                    best_ask = asks[0][0]
                    best_bid_size = bids[0][1] if len(bids[0]) > 1 else 0
                    best_ask_size = asks[0][1] if len(asks[0]) > 1 else 0

                    # Calculate mid price drift (size-weighted average)
                    total_size = best_bid_size + best_ask_size
                    mid_price = (best_bid * best_bid_size + best_ask * best_ask_size) / total_size if total_size > 0 else (best_bid + best_ask) / 2
                    mid_diff_bps = abs((mid_price - mark_price) / mark_price * 10000) if mark_price > 0 else 0

                    # Reference price for order calculation (mid or mark based on config)
                    ref_price = mid_price if USE_MID_AS_MARK else mark_price

                    # Calculate based on total (consistent size display even with orders)
                    order_size = calc_order_size(total_collateral, ref_price)

                    # Get position
                    position = await exchange.get_position(symbol)

                    # ========== Auto Position Close ==========
                    if AUTO_CLOSE_POSITION and position and float(position.get("size", 0)) != 0:
                        # 1. Cancel all orders
                        await order_mgr.cancel_all("Position detected - auto close")
                        orders_exist_since = None

                        # 2. Collect position info
                        pos_side = position.get("side", "").upper()
                        pos_size = abs(float(position.get("size", 0)))
                        pos_entry = float(position.get("entry_price", 0))
                        pos_pnl = float(position.get("unrealized_pnl", 0))

                        # Log: Position detected
                        log_message(f"POSITION DETECTED | {pos_side} {pos_size:.6f} BTC @ {pos_entry:.2f} | uPnL: ${pos_pnl:+.2f}")
                        file_logger.info(f"POSITION DETECTED | {pos_side} {pos_size:.6f} BTC @ {pos_entry:.2f} | uPnL: ${pos_pnl:+.2f}")
                        console.print(f"[yellow]Auto-closing {pos_side} {pos_size:.4f} via {CLOSE_METHOD} (uPnL: ${pos_pnl:+.2f})...[/yellow]")

                        # 3. Strategic position close
                        try:
                            _success, elapsed_time, iterations, close_log = await close_position_strategic(
                                exchange=exchange,
                                symbol=symbol,
                                position=position,
                                method=CLOSE_METHOD,
                                aggressive_bps=CLOSE_AGGRESSIVE_BPS,
                                wait_sec=CLOSE_WAIT_SEC,
                                min_size_market=CLOSE_MIN_SIZE_MARKET,
                                max_iterations=CLOSE_MAX_ITERATIONS,
                            )

                            # Update statistics
                            position_stats["total_closes"] += 1
                            position_stats["total_volume"] += pos_size
                            position_stats["total_pnl"] += pos_pnl
                            position_stats["last_close_time"] = elapsed_time
                            position_stats["total_close_time"] += elapsed_time

                            # Log: Position closed
                            close_msg = (
                                f"POSITION CLOSED  | {pos_side} {pos_size:.6f} BTC | PnL: ${pos_pnl:+.2f} | "
                                f"Method: {CLOSE_METHOD} | Time: {elapsed_time:.2f}s ({iterations} iter)"
                            )
                            log_message(close_msg)
                            file_logger.info(
                                f"{close_msg} | Total: {position_stats['total_closes']} closes, "
                                f"{position_stats['total_volume']:.6f} BTC, ${position_stats['total_pnl']:+.2f}"
                            )

                            last_action = f"Closed {pos_side} {pos_size:.4f} via {CLOSE_METHOD} ({elapsed_time:.1f}s, ${pos_pnl:+.2f})"
                            console.print(f"[green]{close_log} (PnL: ${pos_pnl:+.2f})[/green]")
                        except Exception as e:
                            log_message(f"POSITION CLOSE FAILED | {pos_side} {pos_size:.6f} BTC | Error: {e}")
                            file_logger.info(f"POSITION CLOSE FAILED | {pos_side} {pos_size:.6f} BTC | uPnL: ${pos_pnl:+.2f} | Error: {e}")
                            console.print(f"[red]Failed to close position: {e}[/red]")

                        # Refresh collateral in next iteration
                        need_collateral_update = True

                        await asyncio.sleep(REFRESH_INTERVAL)
                        continue

                    # Calculate order prices
                    buy_price, sell_price = calc_order_prices(ref_price, SPREAD_BPS)

                    # Maker/taker determination
                    buy_is_maker, sell_is_maker = check_maker_taker(
                        buy_price, sell_price, best_bid, best_ask
                    )

                    # Calculate orderbook spread
                    ob_spread_bps = calc_spread_bps(best_bid, best_ask)

                    # Check current orders
                    buy_order = order_mgr.get_buy_order()
                    sell_order = order_mgr.get_sell_order()
                    has_orders = buy_order is not None or sell_order is not None

                    # Calculate drift (based on order)
                    if buy_order:
                        drift_bps = calc_drift_bps(ref_price, buy_order.reference_price)
                    elif sell_order:
                        drift_bps = calc_drift_bps(ref_price, sell_order.reference_price)
                    else:
                        drift_bps = 0.0

                    # ========== 2. Status Determination ==========
                    # If USE_MID_DRIFT is True, combine mark drift + mid drift; otherwise mark drift only
                    effective_drift = (drift_bps + mid_diff_bps) if USE_MID_DRIFT else drift_bps
                    # Wait for orders if mark-mid diff is too large (only when MARK_MID_DIFF_LIMIT > 0)
                    mid_unstable = MARK_MID_DIFF_LIMIT > 0 and mid_diff_bps > MARK_MID_DIFF_LIMIT

                    # Record mid unstable time and check cooldown
                    if mid_unstable:
                        last_mid_unstable_time = time.time()
                    mid_cooldown_active = (
                        MID_UNSTABLE_COOLDOWN > 0 and
                        last_mid_unstable_time > 0 and
                        (time.time() - last_mid_unstable_time) < MID_UNSTABLE_COOLDOWN
                    )

                    # Wait for orders if orderbook spread is too large
                    spread_unstable = SPREAD_UNSTABLE_LIMIT > 0 and ob_spread_bps > SPREAD_UNSTABLE_LIMIT

                    # Record spread unstable time and check cooldown
                    if spread_unstable:
                        last_spread_unstable_time = time.time()
                    spread_cooldown_active = (
                        SPREAD_UNSTABLE_COOLDOWN > 0 and
                        last_spread_unstable_time > 0 and
                        (time.time() - last_spread_unstable_time) < SPREAD_UNSTABLE_COOLDOWN
                    )

                    if order_size <= 0:
                        status = "NO_SIZE"
                    elif not buy_is_maker or not sell_is_maker:
                        status = "WAITING"
                    elif (mid_unstable or mid_cooldown_active) and not has_orders:
                        status = "MID_WAIT"  # Waiting for mid drift stability (or cooldown)
                    elif (spread_unstable or spread_cooldown_active) and not has_orders:
                        status = "SPREAD_WAIT"  # Waiting for spread stability (or cooldown)
                    elif has_orders:
                        if effective_drift > DRIFT_THRESHOLD:
                            status = "REBALANCING"
                        else:
                            status = "MONITORING"
                    else:
                        status = "PLACING"

                    # ========== 3. Track Order Existence Time ==========
                    if has_orders:
                        now = time.time()
                        if orders_exist_since is None:
                            orders_exist_since = now  # Orders first detected
                        time_with_orders = now - orders_exist_since
                        countdown = max(0.0, MIN_WAIT_SEC - time_with_orders)
                        can_modify_orders = time_with_orders >= MIN_WAIT_SEC
                    else:
                        orders_exist_since = None  # Reset if no orders
                        countdown = 0.0
                        can_modify_orders = True  # Can place new orders immediately if none exist

                    # ========== 4. Order Logic ==========
                    # Drift check / unstable check - rebalance (after MIN_WAIT_SEC delay)
                    # cancel_all if drift exceeded threshold or mid/spread unstable
                    if has_orders and (effective_drift > DRIFT_THRESHOLD or mid_unstable or spread_unstable) and can_modify_orders:
                        order_mgr.rebalance()
                        await order_mgr.cancel_all("Drift exceeded threshold or unstable")
                        drift_info = f"{drift_bps:.1f}+{mid_diff_bps:.1f}" if USE_MID_DRIFT else f"{drift_bps:.1f}"
                        last_action = f"Cancelled for rebalance (drift: {drift_info}bps, spread: {ob_spread_bps:.1f}bps)"
                        orders_exist_since = None
                        await asyncio.sleep(CANCEL_AFTER_DELAY)
                        continue  # Place new order with fresh price in next iteration

                    # No orders and maker conditions met - place new orders (only when stable + cooldown done)
                    elif not has_orders and buy_is_maker and sell_is_maker and not mid_unstable and not mid_cooldown_active and not spread_unstable and not spread_cooldown_active:
                        buy_order, sell_order = await staggered_gather(
                            order_mgr.place_order("buy", buy_price, order_size, ref_price),
                            order_mgr.place_order("sell", sell_price, order_size, ref_price),
                        )
                        if buy_order and sell_order:
                            # {'code': 0, 'message': 'success', 'request_id': '....'}
                            has_orders = buy_order.message == 'success' and sell_order.message == 'success'
                            last_action = f"Placed BUY @ {format_price(buy_price)}, SELL @ {format_price(sell_price)}"
                            orders_exist_since = time.time()  # Start timer

                    # ========== 5. Display Dashboard ==========
                    dashboard = build_dashboard(
                        symbol=symbol,
                        mark_price=mark_price,
                        ref_price=ref_price,
                        best_bid=best_bid,
                        best_ask=best_ask,
                        best_bid_size=best_bid_size,
                        best_ask_size=best_ask_size,
                        buy_is_maker=buy_is_maker,
                        sell_is_maker=sell_is_maker,
                        drift_bps=drift_bps,
                        status=status,
                        countdown=countdown,
                        spread_bps=ob_spread_bps,
                        order_mgr=order_mgr,
                        available_collateral=available_collateral,
                        total_collateral=total_collateral,
                        order_size=order_size,
                        position=position,
                        pos_stats=position_stats,
                        last_action=last_action,
                        mode=MODE
                    )
                    live.update(dashboard)

                    # ========== 6. Save Snapshot ==========
                    if SNAPSHOT_INTERVAL > 0 and (current_time - last_snapshot_time) >= SNAPSHOT_INTERVAL:
                        try:
                            buy_order = order_mgr.get_buy_order()
                            sell_order = order_mgr.get_sell_order()
                            with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                                f.write(f"[{MODE}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                f.write(f"Mark: {mark_price:,.2f} | Spread: {ob_spread_bps:.1f}bps\n")
                                f.write(f"Total: ${total_collateral:,.2f} | Available: ${available_collateral:,.2f} | Size: {order_size:.4f} BTC\n")
                                if buy_order:
                                    f.write(f"BUY:  {buy_order.price:,.2f} ({buy_order.status})\n")
                                if sell_order:
                                    f.write(f"SELL: {sell_order.price:,.2f} ({sell_order.status})\n")
                                if position and float(position.get("size", 0)) != 0:
                                    f.write(f"Position: {position.get('side')} {position.get('size')} uPnL: ${position.get('unrealized_pnl', 0):+.2f}\n")
                                f.write(f"Status: {status}\n")
                            last_snapshot_time = current_time
                        except Exception:
                            pass  # Ignore snapshot failures

                    # Reset error counter on success
                    consecutive_errors = 0
                    await asyncio.sleep(REFRESH_INTERVAL)

                except Exception as e:
                    consecutive_errors += 1
                    backoff = min(consecutive_errors * 0.5, 10.0)  # Max 10 seconds
                    log_message(f"ERROR [{consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}] {e}")
                    console.print(f"[red][Error {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}] {e}[/red]")

                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        log_message("Too many consecutive errors, exiting...")
                        console.print("[red]Too many consecutive errors, exiting...[/red]")
                        break

                    await asyncio.sleep(backoff)

    except KeyboardInterrupt:
        global _keyboard_interrupted
        _keyboard_interrupted = True
        console.print("\n[yellow]Shutting down (keyboard interrupt)...[/yellow]")
    finally:
        # Cancel all orders before exit (all symbol orders regardless of cache)
        if is_live:
            console.print("Cancelling all orders...")
            try:
                await order_mgr.cancel_all(reason="shutdown")
                console.print("[green]All orders cancelled.[/green]")
            except Exception as e:
                console.print(f"[red]Failed to cancel orders: {e}[/red]")

        console.print("\n[bold]Final Statistics:[/bold]")
        console.print(f"  Total Orders Placed:    {order_mgr.total_placed}")
        console.print(f"  Total Orders Cancelled: {order_mgr.total_cancelled}")
        console.print(f"  Total Rebalances:       {order_mgr.total_rebalanced}")
        console.print(f"  Position Closes:        {position_stats['total_closes']}")
        console.print(f"  Total Volume Closed:    {position_stats['total_volume']:.6f} BTC")
        pnl_color = "green" if position_stats['total_pnl'] >= 0 else "red"
        console.print(f"  Total Realized PnL:     [{pnl_color}]${position_stats['total_pnl']:+.2f}[/{pnl_color}]")
        if position_stats['total_close_time'] > 0:
            avg_close_time = position_stats['total_close_time'] / max(1, position_stats['total_closes'])
            console.print(f"  Total Close Time:       {position_stats['total_close_time']:.1f}s (avg: {avg_close_time:.1f}s)")

        console.print("Closing exchange connection...")
        await exchange.close()
        console.print("Done.")
        log_message("Bot stopped")

        # Close console log file
        _console_log_file.close()

        # Auto-restart if not keyboard interrupted (server error recovery)
        if not _keyboard_interrupted:
            restart_delay = RESTART_DELAY if RESTART_DELAY > 0 else 5.0
            log_message(f"AUTO RESTART | Unexpected exit, restarting in {restart_delay}s...")
            console.print(f"\n[yellow]Unexpected exit detected. Auto-restarting in {restart_delay}s...[/yellow]")
            console.print("[dim]Press Ctrl+C again to cancel restart[/dim]")
            try:
                time.sleep(restart_delay)
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except KeyboardInterrupt:
                console.print("\n[yellow]Restart cancelled by user.[/yellow]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _keyboard_interrupted = True
    finally:
        # Ensure log file is closed on exit
        if not _console_log_file.closed:
            _console_log_file.close()
