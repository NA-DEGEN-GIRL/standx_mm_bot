#!/usr/bin/env python3
"""
StandX Market Making Simulator (Test Mode)
===========================================
mark_price 기준 ±8bps에 양방향 limit order를 시뮬레이션.
실제 주문 없이 가격과 maker/taker 상태를 실시간 모니터링.

Usage:
    python main.py
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import uuid
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
    MODE, EXCHANGE, COIN,
    SPREAD_BPS, DRIFT_THRESHOLD, MIN_WAIT_SEC, REFRESH_INTERVAL,
    SIZE_UNIT, LEVERAGE, MAX_SIZE_BTC,
    MAX_HISTORY, MAX_CONSECUTIVE_ERRORS,
)

load_dotenv()

STANDX_KEY = SimpleNamespace(
    wallet_address=os.getenv("WALLET_ADDRESS"),
    chain='bsc',
    evm_private_key=os.getenv("PRIVATE_KEY"),
    open_browser=True,
)

console = Console()


# ==================== 시뮬레이션 주문 ====================

@dataclass
class SimOrder:
    """시뮬레이션 주문"""
    id: str
    side: str  # "buy" or "sell"
    price: float
    size: float
    status: str = "open"  # "open", "filled", "cancelled"
    placed_at: datetime = field(default_factory=datetime.now)
    reference_price: float = 0.0  # 주문 시점 mark_price


class SimOrderManager:
    """시뮬레이션 주문 관리자"""

    def __init__(self):
        self.orders: Dict[str, SimOrder] = {}
        self.history: List[Dict[str, Any]] = []  # 주문 히스토리
        self.total_placed = 0
        self.total_cancelled = 0
        self.total_rebalanced = 0
        self.is_live = False

    def _append_history(self, record: Dict[str, Any]) -> None:
        """히스토리 추가 (메모리 제한)"""
        self.history.append(record)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    async def place_order(self, side: str, price: float, size: float, reference_price: float) -> SimOrder:
        """주문 생성 (시뮬레이션)"""
        order_id = f"SIM-{uuid.uuid4().hex[:8].upper()}"
        order = SimOrder(
            id=order_id,
            side=side,
            price=price,
            size=size,
            reference_price=reference_price
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
        """주문 취소 (시뮬레이션)"""
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
        """모든 주문 취소 (시뮬레이션)"""
        count = len(self.orders)
        for order_id in list(self.orders.keys()):
            await self.cancel_order(order_id, reason)
        return count

    def get_open_orders(self) -> List[SimOrder]:
        """열린 주문 목록"""
        return list(self.orders.values())

    def get_buy_order(self) -> Optional[SimOrder]:
        """BUY 주문 조회"""
        for order in self.orders.values():
            if order.side == "buy":
                return order
        return None

    def get_sell_order(self) -> Optional[SimOrder]:
        """SELL 주문 조회"""
        for order in self.orders.values():
            if order.side == "sell":
                return order
        return None

    def rebalance(self) -> None:
        """리밸런스 카운트 증가"""
        self.total_rebalanced += 1


class LiveOrderManager:
    """실제 주문 관리자 (LIVE 모드)"""

    def __init__(self, exchange, symbol: str):
        self.exchange = exchange
        self.symbol = symbol
        self.orders: Dict[str, SimOrder] = {}  # 로컬 캐시 (reference_price 저장용)
        self.history: List[Dict[str, Any]] = []
        self.total_placed = 0
        self.total_cancelled = 0
        self.total_rebalanced = 0
        self.is_live = True

    def _append_history(self, record: Dict[str, Any]) -> None:
        """히스토리 추가 (메모리 제한)"""
        self.history.append(record)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    async def place_order(self, side: str, price: float, size: float, reference_price: float) -> Optional[SimOrder]:
        """실제 주문 생성"""
        try:
            # client_order_id 생성 (추적용)
            cl_ord_id = f"MM-{uuid.uuid4().hex[:8].upper()}"

            result = await self.exchange.create_order(
                symbol=self.symbol,
                side=side,
                amount=size,
                price=price,
                order_type="limit",
                client_order_id=cl_ord_id
            )

            # StandX 응답: {'code': 0, 'message': 'success', 'request_id': '...'}
            # order_id가 없으므로 cl_ord_id를 사용
            code = result.get("code")
            if code == 0:
                order = SimOrder(
                    id=cl_ord_id,  # client_order_id를 ID로 사용
                    side=side,
                    price=price,
                    size=size,
                    reference_price=reference_price
                )
                self.orders[cl_ord_id] = order
                self.total_placed += 1
                self._append_history({
                    "action": "PLACE",
                    "order_id": cl_ord_id,
                    "side": side,
                    "price": price,
                    "time": datetime.now()
                })
                return order
            else:
                console.print(f"[red]Order rejected: {result}[/red]")
        except Exception as e:
            console.print(f"[red]Order failed: {e}[/red]")
        return None

    async def cancel_all(self, reason: str = "") -> int:
        """모든 주문 취소 (symbol 기반 전체 취소)"""
        try:
            await self.exchange.cancel_orders(symbol=self.symbol)
            count = len(self.orders)
            self.total_cancelled += count
            self.orders.clear()
            return count
        except Exception as e:
            console.print(f"[red]Cancel all failed: {e}[/red]")
            self.orders.clear()  # 에러나도 로컬 캐시는 초기화
            return 0

    async def sync_orders(self) -> None:
        """
        실제 오픈 오더와 로컬 캐시 동기화.
        - 체결된 주문 감지 (로컬에는 있는데 서버에 없으면 제거)
        - reference_price는 보존 (drift 계산용)
        """
        try:
            real_orders = await self.exchange.get_open_orders(self.symbol)

            # 서버 주문을 side별로 정리
            server_by_side: Dict[str, Dict] = {}
            for ro in real_orders:
                side = ro.get("side", "").lower()
                if side in ("buy", "sell"):
                    server_by_side[side] = ro

            # 로컬 주문과 비교
            for side in ["buy", "sell"]:
                local_order = self.get_buy_order() if side == "buy" else self.get_sell_order()
                server_order = server_by_side.get(side)

                if local_order and not server_order:
                    # 로컬에 있는데 서버에 없음 = 체결됨
                    self.orders.pop(local_order.id, None)
                elif not local_order and server_order:
                    # 서버에 있는데 로컬에 없음 = 외부에서 생성된 주문 (무시하거나 추가)
                    pass  # MM이 만든 주문만 추적

        except Exception as e:
            console.print(f"[yellow]Sync warning: {e}[/yellow]")

    def get_open_orders(self) -> List[SimOrder]:
        """열린 주문 목록"""
        return list(self.orders.values())

    def get_buy_order(self) -> Optional[SimOrder]:
        """BUY 주문 조회"""
        for order in self.orders.values():
            if order.side == "buy":
                return order
        return None

    def get_sell_order(self) -> Optional[SimOrder]:
        """SELL 주문 조회"""
        for order in self.orders.values():
            if order.side == "sell":
                return order
        return None

    def rebalance(self) -> None:
        """리밸런스 카운트 증가"""
        self.total_rebalanced += 1

# ==================== 유틸 함수 ====================

def calc_order_prices(mark_price: float, spread_bps: float) -> Tuple[float, float]:
    """
    mark_price 기준 ±spread_bps 위치의 주문 가격 계산

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
    주문이 maker인지 taker인지 판정

    Returns:
        (buy_is_maker, sell_is_maker)
    """
    # buy order: maker if price < best_ask (호가창 안에 들어감)
    buy_is_maker = buy_price < best_ask
    # sell order: maker if price > best_bid (호가창 안에 들어감)
    sell_is_maker = sell_price > best_bid
    return buy_is_maker, sell_is_maker


def calc_drift_bps(current_price: float, reference_price: float) -> float:
    """
    현재 가격과 기준 가격의 차이를 bps로 계산
    """
    if reference_price == 0:
        return 0.0
    return abs(current_price - reference_price) / reference_price * 10000


def calc_spread_bps(best_bid: float, best_ask: float) -> float:
    """
    오더북 스프레드를 bps로 계산
    """
    if best_bid == 0:
        return 0.0
    mid = (best_bid + best_ask) / 2
    return (best_ask - best_bid) / mid * 10000


def format_price(price: float, decimals: int = 2) -> str:
    """가격 포맷팅 (천단위 콤마)"""
    return f"{price:,.{decimals}f}"


def calc_order_size(
    available_collateral: float,
    mark_price: float,
    leverage: float = LEVERAGE,
    size_unit: float = SIZE_UNIT,
    max_size: Optional[float] = MAX_SIZE_BTC
) -> float:
    """
    Collateral 기반 주문 수량 계산.

    Args:
        available_collateral: 사용 가능한 담보금 (USD)
        mark_price: 현재 마크 가격
        leverage: 레버리지 배수 (6배 → 양방향 3배씩)
        size_unit: 최소 주문 단위 (기본 0.001 BTC)
        max_size: 수동 최대 수량 제한 (None이면 무제한)

    Returns:
        주문 수량 (BTC), size_unit 단위로 내림

    예시:
        $100 collateral, BTC=$100k, leverage=6
        -> $100 * 6 / 2 / $100k = 0.003 BTC per side
    """
    if mark_price <= 0 or available_collateral <= 0:
        return 0.0

    # collateral * leverage / 2 (양방향) / mark_price
    # 예: $100 * 6 / 2 / $100k = 0.003 BTC per side
    collateral_based_size = available_collateral * leverage / 2 / mark_price

    # max_size가 설정되어 있으면 더 작은 값 선택
    if max_size is not None and max_size > 0:
        size = min(collateral_based_size, max_size)
    else:
        size = collateral_based_size

    # size_unit 단위로 내림 (예: 0.00367 -> 0.003)
    size = (size // size_unit) * size_unit

    return size


# ==================== 대시보드 출력 (Rich) ====================

def build_dashboard(
    symbol: str,
    mark_price: float,
    best_bid: float,
    best_ask: float,
    buy_is_maker: bool,
    sell_is_maker: bool,
    drift_bps: float,
    status: str,
    countdown: int,
    spread_bps: float,
    order_mgr,  # SimOrderManager or LiveOrderManager
    available_collateral: float,
    order_size: float,
    position: Optional[Dict[str, Any]],
    last_action: str = "",
    mode: str = "TEST"
) -> Panel:
    """대시보드를 rich Panel로 생성"""
    from rich.table import Table
    from rich.text import Text

    now = datetime.now().strftime("%H:%M:%S")
    is_live = mode == "LIVE"

    # 현재 주문 가져오기
    buy_order = order_mgr.get_buy_order()
    sell_order = order_mgr.get_sell_order()

    # 주문 가치 계산 (USD)
    order_value = order_size * mark_price

    # ========== 메인 테이블 ==========
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
        Text(f"  Available: ${available_collateral:,.2f}", style="green"),
        Text(f"  Order Size: {order_size:.4f} {COIN} (${order_value:,.2f}) x{LEVERAGE:.0f}", style="bold")
    )

    # 포지션 표시
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
    table.add_row(
        Text(f"  Mark Price: {format_price(mark_price):>12}"),
        ""
    )

    # 스프레드 색상
    if spread_bps < 5:
        spread_style = "green"
    elif spread_bps < 10:
        spread_style = "yellow"
    else:
        spread_style = "red"

    drift_style = "yellow" if drift_bps > DRIFT_THRESHOLD else "green"

    market_line1 = Text(f"  Best Bid: {format_price(best_bid):>12}  │  Best Ask: {format_price(best_ask):>12}")
    market_line2 = Text("  OB Spread: ")
    market_line2.append(f"{spread_bps:>6.2f} bps", style=spread_style)
    market_line2.append("  │  Drift: ")
    market_line2.append(f"{drift_bps:>6.2f} bps", style=drift_style)
    table.add_row(market_line1, "")
    table.add_row(market_line2, "")
    table.add_row("", "")

    # -- SIMULATED ORDERS Section --
    table.add_row(Text("▌ SIMULATED ORDERS", style="bold cyan"), "")

    # SELL Order (위에 표시)
    sell_maker_text = Text("[MAKER]", style="green") if sell_is_maker else Text("[TAKER]", style="red")
    if sell_order:
        sell_drift = calc_drift_bps(mark_price, sell_order.reference_price)
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

    # BUY Order (아래에 표시)
    buy_maker_text = Text("[MAKER]", style="green") if buy_is_maker else Text("[TAKER]", style="red")
    if buy_order:
        buy_drift = calc_drift_bps(mark_price, buy_order.reference_price)
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

    # 상태 색상
    if status == "MONITORING":
        status_text = Text("● MONITORING - Orders active", style="green bold")
    elif status == "PLACING":
        status_text = Text("▶ PLACING orders...", style="cyan bold")
    elif status == "NO_SIZE":
        status_text = Text("✗ NO SIZE - Insufficient collateral", style="red bold")
    elif status == "WAITING":
        status_text = Text("◌ WAITING - Would be TAKER", style="yellow bold")
    elif status == "REBALANCING":
        status_text = Text("⟳ REBALANCING - Cancelling & replacing", style="yellow bold")
    else:
        status_text = Text(status)

    table.add_row(Text("  ").append_text(status_text), "")

    if last_action:
        table.add_row(Text(f"  Last: {last_action}", style="dim"), "")

    if countdown > 0:
        table.add_row(Text(f"  Next check in: {countdown}s", style="dim"), "")

    table.add_row("", "")

    # -- STATS Section --
    stats_text = Text(
        f"Placed: {order_mgr.total_placed}  Cancelled: {order_mgr.total_cancelled}  Rebalanced: {order_mgr.total_rebalanced}",
        style="dim"
    )
    table.add_row(stats_text, "")

    # Panel로 감싸기
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


# ==================== 메인 로직 ====================

async def main():
    is_live = MODE == "LIVE"
    mode_str = "[red]LIVE[/red]" if is_live else "[cyan]TEST[/cyan]"

    console.print(f"\n{'='*60}")
    console.print(f"  StandX Market Making Bot")
    console.print(f"  Mode: {mode_str}")
    console.print(f"  Coin: {COIN}, Spread: {SPREAD_BPS}bps, Drift: {DRIFT_THRESHOLD}bps")
    console.print(f"{'='*60}\n")

    # LIVE 모드 확인
    if is_live:
        console.print("[bold red]WARNING: LIVE MODE - Real orders will be placed![/bold red]")
        console.print(f"  Max Size: {MAX_SIZE_BTC} {COIN}")
        console.print(f"  Leverage: {LEVERAGE}x")
        confirm = input("\nType 'YES' to confirm: ")
        if confirm != "YES":
            console.print("[yellow]Aborted.[/yellow]")
            return

    

    # Exchange 초기화
    console.print("Initializing exchange...")
    exchange = await create_exchange(EXCHANGE, STANDX_KEY)
    symbol = symbol_create(EXCHANGE, COIN)
    console.print(f"Symbol: {symbol}")

    # 주문 관리자 생성 (모드에 따라)
    if is_live:
        order_mgr = LiveOrderManager(exchange, symbol)
        console.print("[red]Using LIVE order manager[/red]")
    else:
        order_mgr = SimOrderManager()
        console.print("[cyan]Using SIMULATED order manager[/cyan]")

    last_action = ""

    try:
        # WS 구독 시작
        console.print("Subscribing to price and orderbook...")
        if exchange.ws_client:
            await exchange.ws_client.subscribe_price(symbol)
            await exchange.ws_client.subscribe_orderbook(symbol)

        # 초기 데이터 대기
        console.print("Waiting for initial data...")
        await asyncio.sleep(2)

        # LIVE 모드: 기존 주문 동기화
        if is_live:
            console.print("Syncing existing orders...")
            await order_mgr.sync_orders()

        # 주문 존재 시점 추적
        import time
        orders_exist_since: Optional[float] = None  # 주문이 존재하기 시작한 시점
        countdown = int(MIN_WAIT_SEC)
        last_sync_time = time.time()
        SYNC_INTERVAL = 5.0  # LIVE 모드에서 주문 동기화 간격

        # 연속 에러 추적
        consecutive_errors = 0

        # 메인 루프 (Live context로 flicker-free 업데이트)
        with Live(console=console, refresh_per_second=10, transient=True) as live:
            while True:
                try:
                    current_time = time.time()

                    # ========== 0. LIVE 모드: 주기적 주문 동기화 ==========
                    if is_live and (current_time - last_sync_time) >= SYNC_INTERVAL:
                        await order_mgr.sync_orders()
                        last_sync_time = current_time

                    # ========== 1. 실시간 데이터 fetch ==========
                    # mark_price 조회
                    mark_price_str = await exchange.get_mark_price(symbol)
                    mark_price = float(mark_price_str)

                    # 데이터 검증: mark_price
                    if mark_price <= 0:
                        await asyncio.sleep(REFRESH_INTERVAL)
                        continue

                    # orderbook 조회
                    orderbook = await exchange.get_orderbook(symbol)
                    bids = orderbook.get("bids", [])
                    asks = orderbook.get("asks", [])

                    # 데이터 검증: orderbook
                    if not bids or not asks:
                        await asyncio.sleep(REFRESH_INTERVAL)
                        continue

                    best_bid = bids[0][0]
                    best_ask = asks[0][0]

                    # collateral 조회 및 주문 수량 계산
                    collateral = await exchange.get_collateral()
                    available_collateral = float(collateral.get("available_collateral", 0))
                    order_size = calc_order_size(available_collateral, mark_price)

                    # position 조회
                    position = await exchange.get_position(symbol)

                    # 주문 가격 계산
                    buy_price, sell_price = calc_order_prices(mark_price, SPREAD_BPS)

                    # maker/taker 판정
                    buy_is_maker, sell_is_maker = check_maker_taker(
                        buy_price, sell_price, best_bid, best_ask
                    )

                    # 오더북 스프레드 계산
                    ob_spread_bps = calc_spread_bps(best_bid, best_ask)

                    # 현재 주문 확인
                    buy_order = order_mgr.get_buy_order()
                    sell_order = order_mgr.get_sell_order()
                    has_orders = buy_order is not None or sell_order is not None

                    # 드리프트 계산 (주문 기준)
                    if buy_order:
                        drift_bps = calc_drift_bps(mark_price, buy_order.reference_price)
                    elif sell_order:
                        drift_bps = calc_drift_bps(mark_price, sell_order.reference_price)
                    else:
                        drift_bps = 0.0

                    # ========== 2. 상태 결정 ==========
                    if order_size <= 0:
                        status = "NO_SIZE"
                    elif not buy_is_maker or not sell_is_maker:
                        status = "WAITING"
                    elif has_orders:
                        if drift_bps > DRIFT_THRESHOLD:
                            status = "REBALANCING"
                        else:
                            status = "MONITORING"
                    else:
                        status = "PLACING"

                    # ========== 3. 주문 존재 시간 추적 ==========
                    if has_orders:
                        if orders_exist_since is None:
                            orders_exist_since = current_time  # 주문이 처음 감지됨
                        time_with_orders = current_time - orders_exist_since
                        countdown = max(1, int(MIN_WAIT_SEC - time_with_orders) + 1)
                        can_modify_orders = time_with_orders >= MIN_WAIT_SEC
                    else:
                        orders_exist_since = None  # 주문 없으면 리셋
                        countdown = 0
                        can_modify_orders = True  # 주문이 없으면 바로 새 주문 가능

                    # ========== 4. 주문 로직 ==========
                    # 수량이 0이면 주문 안 함 (즉시)
                    if order_size <= 0:
                        if has_orders and can_modify_orders:
                            count = await order_mgr.cancel_all("Insufficient collateral")
                            if count > 0:
                                last_action = f"Cancelled {count} orders (no collateral)"
                            orders_exist_since = None

                    # Taker 조건 체크 - 즉시 취소 (손실 방지)
                    elif not buy_is_maker or not sell_is_maker:
                        if has_orders:
                            count = await order_mgr.cancel_all("Would become TAKER")
                            if count > 0:
                                last_action = f"Cancelled {count} orders (TAKER risk)"
                            orders_exist_since = None

                    # 드리프트 체크 - 리밸런스 (MIN_WAIT_SEC 대기 후)
                    elif has_orders and drift_bps > DRIFT_THRESHOLD and can_modify_orders:
                        await order_mgr.cancel_all("Drift exceeded threshold")
                        order_mgr.rebalance()
                        buy_order = await order_mgr.place_order("buy", buy_price, order_size, mark_price)
                        sell_order = await order_mgr.place_order("sell", sell_price, order_size, mark_price)
                        last_action = f"Rebalanced @ {format_price(mark_price)} (drift: {drift_bps:.1f}bps)"
                        orders_exist_since = current_time  # 새 주문이니 타이머 리셋

                    # 주문이 없고 maker 조건 충족 - 신규 주문 (즉시)
                    elif not has_orders and buy_is_maker and sell_is_maker:
                        buy_order = await order_mgr.place_order("buy", buy_price, order_size, mark_price)
                        sell_order = await order_mgr.place_order("sell", sell_price, order_size, mark_price)
                        last_action = f"Placed BUY @ {format_price(buy_price)}, SELL @ {format_price(sell_price)}"
                        orders_exist_since = current_time  # 타이머 시작

                    # ========== 5. 대시보드 표시 ==========
                    dashboard = build_dashboard(
                        symbol=symbol,
                        mark_price=mark_price,
                        best_bid=best_bid,
                        best_ask=best_ask,
                        buy_is_maker=buy_is_maker,
                        sell_is_maker=sell_is_maker,
                        drift_bps=drift_bps,
                        status=status,
                        countdown=countdown,
                        spread_bps=ob_spread_bps,
                        order_mgr=order_mgr,
                        available_collateral=available_collateral,
                        order_size=order_size,
                        position=position,
                        last_action=last_action,
                        mode=MODE
                    )
                    live.update(dashboard)

                    # 성공 시 에러 카운터 리셋
                    consecutive_errors = 0
                    await asyncio.sleep(REFRESH_INTERVAL)

                except Exception as e:
                    consecutive_errors += 1
                    backoff = min(consecutive_errors * 0.5, 10.0)  # 최대 10초
                    console.print(f"[red][Error {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}] {e}[/red]")

                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        console.print("[red]Too many consecutive errors, exiting...[/red]")
                        break

                    await asyncio.sleep(backoff)

    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    finally:
        # 종료 전 모든 주문 취소
        if is_live:
            console.print("Cancelling all orders...")
            try:
                await order_mgr.cancel_all("Shutdown")
                console.print("[green]All orders cancelled.[/green]")
            except Exception as e:
                console.print(f"[red]Failed to cancel orders: {e}[/red]")

        console.print("\n[bold]Final Statistics:[/bold]")
        console.print(f"  Total Orders Placed:    {order_mgr.total_placed}")
        console.print(f"  Total Orders Cancelled: {order_mgr.total_cancelled}")
        console.print(f"  Total Rebalances:       {order_mgr.total_rebalanced}")

        console.print("Closing exchange connection...")
        await exchange.close()
        console.print("Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # 이미 main()에서 처리됨
