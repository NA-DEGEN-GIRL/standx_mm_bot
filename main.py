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
    SPREAD_BPS, DRIFT_THRESHOLD, USE_MID_DRIFT, MARK_MID_DIFF_LIMIT, MIN_WAIT_SEC, REFRESH_INTERVAL,
    SIZE_UNIT, LEVERAGE, MAX_SIZE_BTC,
    MAX_HISTORY, MAX_CONSECUTIVE_ERRORS,
    AUTO_CLOSE_POSITION,
    CLOSE_METHOD, CLOSE_AGGRESSIVE_BPS, CLOSE_WAIT_SEC,
    CLOSE_MIN_SIZE_MARKET, CLOSE_MAX_ITERATIONS,
    SNAPSHOT_INTERVAL, SNAPSHOT_FILE,
)

load_dotenv()

# ==================== 로깅 설정 ====================
LOG_FILE = "position_log.txt"

# 파일 로거 설정
file_logger = logging.getLogger("position")
file_logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
file_logger.addHandler(file_handler)

STANDX_KEY = SimpleNamespace(
    wallet_address=os.getenv("WALLET_ADDRESS"),
    chain='bsc',
    evm_private_key=os.getenv("PRIVATE_KEY"),
    open_browser=True,
)

console = Console()

# ==================== 포지션 통계 ====================
position_stats = {
    "total_closes": 0,       # 총 청산 횟수
    "total_volume": 0.0,     # 총 청산 BTC 수량
    "total_pnl": 0.0,        # 총 실현 손익 (USD)
    "last_close_time": 0.0,  # 마지막 청산 소요 시간 (초)
    "total_close_time": 0.0, # 총 청산 소요 시간 (초)
}


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
    # 부동소수점 오차 보정을 위해 round 사용
    size = round(size / size_unit) * size_unit
    
    return round(size, 8)  # 최종 정밀도 보정


# ==================== 전략적 포지션 청산 ====================

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
    전략적 포지션 청산.

    Args:
        exchange: Exchange wrapper 인스턴스
        symbol: 거래 심볼
        position: 포지션 정보 {'size', 'side'}
        method: "market", "aggressive", "chase"
        aggressive_bps: aggressive 모드 BPS
        wait_sec: 대기 시간 (초)
        min_size_market: 시장가 전환 최소 수량
        max_iterations: 최대 반복 횟수

    Returns:
        (success, elapsed_time, iterations, log_message)
    """
    import time

    pos_side = position.get("side", "").lower()
    remaining_size = abs(float(position.get("size", 0)))
    close_side = "sell" if pos_side in ["long", "buy"] else "buy"

    start_time = time.time()
    iterations = 0

    # Market close - 즉시 시장가
    if method == "market":
        await exchange.close_position(symbol, position)
        elapsed = time.time() - start_time
        return (True, elapsed, 1, f"MARKET 청산 ({elapsed:.2f}s)")

    # Limit order close loop (aggressive or chase)
    while remaining_size > 0:
        iterations += 1

        # 최대 반복 횟수 초과 시 시장가로 강제 청산
        if iterations > max_iterations:
            await exchange.create_order(
                symbol=symbol,
                side=close_side,
                amount=remaining_size,
                order_type="market",
                is_reduce_only=True,
            )
            elapsed = time.time() - start_time
            return (True, elapsed, iterations, f"{method.upper()} 청산 - max iterations 초과, 시장가 전환 ({elapsed:.1f}s)")

        # 잔여 수량이 너무 작으면 시장가로 청산
        if remaining_size < min_size_market:
            await exchange.create_order(
                symbol=symbol,
                side=close_side,
                amount=remaining_size,
                order_type="market",
                is_reduce_only=True,
            )
            elapsed = time.time() - start_time
            return (True, elapsed, iterations, f"{method.upper()} 청산 - dust 시장가 전환 ({elapsed:.1f}s, {iterations} iter)")

        # 방식에 따라 지정가 계산
        limit_price = None

        if method == "aggressive":
            if aggressive_bps == 0:
                # BPS가 0이면 즉시 체결되는 호가에 지정가 (시장가처럼 동작)
                orderbook = await exchange.get_orderbook(symbol)
                bids = orderbook.get("bids", [])
                asks = orderbook.get("asks", [])
                if close_side == "sell":
                    # LONG 청산: best_bid에 매도 → 즉시 체결
                    limit_price = bids[0][0] if bids else None
                else:
                    # SHORT 청산: best_ask에 매수 → 즉시 체결
                    limit_price = asks[0][0] if asks else None

                # 오더북 없으면 mark_price로 fallback (시장가 회피)
                if limit_price is None:
                    limit_price = float(await exchange.get_mark_price(symbol))
            else:
                mark_price = float(await exchange.get_mark_price(symbol))
                if close_side == "sell":
                    # LONG 청산: 낮은 가격에 매도 (빠른 체결)
                    limit_price = mark_price * (1 - aggressive_bps / 10000)
                else:
                    # SHORT 청산: 높은 가격에 매수 (빠른 체결)
                    limit_price = mark_price * (1 + aggressive_bps / 10000)

        elif method == "chase":
            orderbook = await exchange.get_orderbook(symbol)
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            if close_side == "sell":
                # LONG 청산: best_ask에 매도
                limit_price = asks[0][0] if asks else None
            else:
                # SHORT 청산: best_bid에 매수
                limit_price = bids[0][0] if bids else None

            # 오더북 데이터 없으면 시장가 fallback
            if limit_price is None:
                await exchange.create_order(
                    symbol=symbol,
                    side=close_side,
                    amount=remaining_size,
                    order_type="market",
                    is_reduce_only=True,
                )
                elapsed = time.time() - start_time
                return (True, elapsed, iterations, f"CHASE 청산 - 오더북 없음, 시장가 전환 ({elapsed:.1f}s)")

        # 지정가 주문 생성
        cl_ord_id = f"CLOSE-{uuid.uuid4().hex[:8].upper()}"
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
            # 주문 실패 시 다음 iteration에서 재시도
            console.print(f"[yellow]Close order failed: {e}, retrying...[/yellow]")
            await asyncio.sleep(1.0)
            continue

        # 폴링으로 체결 확인 (0.5초 간격, wait_sec까지)
        poll_interval = 0.01
        poll_start = time.time()
        filled = False

        while (time.time() - poll_start) < wait_sec:
            await asyncio.sleep(poll_interval)

            # 포지션 확인
            new_position = await exchange.get_position(symbol)
            if new_position is None or float(new_position.get("size", 0)) == 0:
                # 완전 청산 완료
                elapsed = time.time() - start_time
                return (True, elapsed, iterations, f"{method.upper()} 청산 완료 ({elapsed:.1f}s, {iterations} iter)")

            # 잔여 수량 확인
            new_remaining = abs(float(new_position.get("size", 0)))
            if new_remaining < remaining_size:
                # 부분 체결 발생
                console.print(f"[dim]Partial fill: {remaining_size:.6f} -> {new_remaining:.6f}[/dim]")
                remaining_size = new_remaining
                filled = True

        # 대기 시간 만료 후에도 미체결이면 취소 후 재시도
        if not filled:
            remaining_size = abs(float((await exchange.get_position(symbol) or {}).get("size", 0)))

        # 미체결 주문 취소
        try:
            await exchange.cancel_order(client_order_id=cl_ord_id)
        except Exception:
            pass  # 이미 체결되었거나 취소됨

    elapsed = time.time() - start_time
    return (True, elapsed, iterations, f"{method.upper()} 청산 완료 ({elapsed:.1f}s, {iterations} iter)")


# ==================== 대시보드 출력 (Rich) ====================

def build_dashboard(
    symbol: str,
    mark_price: float,
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
        Text(f"  Total: ${total_collateral:,.2f}  Available: ${available_collateral:,.2f}", style="green"),
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
    # Mid price (수량 가중 평균)
    total_size = best_bid_size + best_ask_size
    mid_price = (best_bid * best_bid_size + best_ask * best_ask_size) / total_size if total_size > 0 else (best_bid + best_ask) / 2
    mid_diff_bps = (mid_price - mark_price) / mark_price * 10000 if mark_price > 0 else 0
    mid_diff_style = "green" if abs(mid_diff_bps) < 3 else ("yellow" if abs(mid_diff_bps) < 6 else "red")

    # 스프레드 색상
    if spread_bps < 5:
        spread_style = "green"
    elif spread_bps < 10:
        spread_style = "yellow"
    else:
        spread_style = "red"
    drift_style = "yellow" if drift_bps > DRIFT_THRESHOLD else "green"

    # 정렬된 출력 (고정 너비 12자)
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
    elif status == "MID_WAIT":
        status_text = Text("◌ MID_WAIT - Mid drift unstable", style="yellow bold")
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

    # 첫 줄: 주문 통계
    stats_line1 = Text(
        f"Placed: {order_mgr.total_placed}  Cancelled: {order_mgr.total_cancelled}  Rebalanced: {order_mgr.total_rebalanced}",
        style="dim"
    )
    table.add_row(stats_line1, "")

    # 둘째 줄: 청산 통계
    stats_line2 = Text(f"Closes: {pos_stats['total_closes']} (", style="dim")
    stats_line2.append(f"{pos_stats['total_volume']:.4f} BTC", style="dim")
    stats_line2.append(", ", style="dim")
    stats_line2.append(f"${pos_stats['total_pnl']:+.2f}", style=pnl_style)
    # 청산 시간 표시
    if pos_stats.get('total_close_time', 0) > 0:
        stats_line2.append(f", total: {pos_stats['total_close_time']:.1f}s", style="dim")
    if pos_stats.get('last_close_time', 0) > 0:
        stats_line2.append(f", last: {pos_stats['last_close_time']:.1f}s", style="dim")
    stats_line2.append(")", style="dim")
    table.add_row(stats_line2, "")

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
    mid_drift_str = "+mid" if USE_MID_DRIFT else ""
    console.print(f"  Coin: {COIN}, Spread: {SPREAD_BPS}bps, Drift: {DRIFT_THRESHOLD}bps{mid_drift_str}, MarkMidLimit: {MARK_MID_DIFF_LIMIT}bps")
    console.print(f"{'='*60}\n")

    # LIVE 모드 확인
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
        countdown = float(MIN_WAIT_SEC)

        # 연속 에러 추적
        consecutive_errors = 0

        # 스냅샷 추적
        last_snapshot_time = 0.0

        # 메인 루프 (Live context로 flicker-free 업데이트)
        with Live(console=console, refresh_per_second=10, transient=True) as live:
            while True:
                try:
                    current_time = time.time()

                    # ========== 0. LIVE 모드: 매 iteration 주문 동기화 ==========
                    if is_live:
                        await order_mgr.sync_orders()

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
                    best_bid_size = bids[0][1] if len(bids[0]) > 1 else 0
                    best_ask_size = asks[0][1] if len(asks[0]) > 1 else 0

                    # mid price drift 계산 (수량 가중 평균)
                    total_size = best_bid_size + best_ask_size
                    mid_price = (best_bid * best_bid_size + best_ask * best_ask_size) / total_size if total_size > 0 else (best_bid + best_ask) / 2
                    mid_diff_bps = abs((mid_price - mark_price) / mark_price * 10000) if mark_price > 0 else 0

                    # collateral 조회 및 주문 수량 계산
                    collateral = await exchange.get_collateral()
                    available_collateral = float(collateral.get("available_collateral", 0))
                    total_collateral = float(collateral.get("total_collateral", 0))
                    # total 기준으로 계산 (주문이 들어가도 일관된 크기 표시)
                    order_size = calc_order_size(total_collateral, mark_price)

                    # position 조회
                    position = await exchange.get_position(symbol)

                    # ========== 포지션 자동 청산 ==========
                    if AUTO_CLOSE_POSITION and position and float(position.get("size", 0)) != 0:
                        # 1. 모든 주문 취소 (sync는 iteration 시작시 이미 완료)
                        await order_mgr.cancel_all("Position detected - auto close")
                        orders_exist_since = None

                        # 2. 포지션 정보 수집
                        pos_side = position.get("side", "").upper()
                        pos_size = abs(float(position.get("size", 0)))
                        pos_entry = float(position.get("entry_price", 0))
                        pos_pnl = float(position.get("unrealized_pnl", 0))

                        # 로그: 포지션 감지
                        file_logger.info(f"POSITION DETECTED | {pos_side} {pos_size:.6f} BTC @ {pos_entry:.2f} | uPnL: ${pos_pnl:+.2f}")
                        console.print(f"[yellow]Auto-closing {pos_side} {pos_size:.4f} via {CLOSE_METHOD} (uPnL: ${pos_pnl:+.2f})...[/yellow]")

                        # 3. 전략적 포지션 청산
                        try:
                            success, elapsed_time, iterations, close_log = await close_position_strategic(
                                exchange=exchange,
                                symbol=symbol,
                                position=position,
                                method=CLOSE_METHOD,
                                aggressive_bps=CLOSE_AGGRESSIVE_BPS,
                                wait_sec=CLOSE_WAIT_SEC,
                                min_size_market=CLOSE_MIN_SIZE_MARKET,
                                max_iterations=CLOSE_MAX_ITERATIONS,
                            )

                            # 통계 업데이트
                            position_stats["total_closes"] += 1
                            position_stats["total_volume"] += pos_size
                            position_stats["total_pnl"] += pos_pnl
                            position_stats["last_close_time"] = elapsed_time
                            position_stats["total_close_time"] += elapsed_time

                            # 로그: 포지션 청산 완료
                            file_logger.info(
                                f"POSITION CLOSED  | {pos_side} {pos_size:.6f} BTC | PnL: ${pos_pnl:+.2f} | "
                                f"Method: {CLOSE_METHOD} | Time: {elapsed_time:.2f}s ({iterations} iter) | "
                                f"Total: {position_stats['total_closes']} closes, "
                                f"{position_stats['total_volume']:.6f} BTC, ${position_stats['total_pnl']:+.2f}"
                            )

                            last_action = f"Closed {pos_side} {pos_size:.4f} via {CLOSE_METHOD} ({elapsed_time:.1f}s, ${pos_pnl:+.2f})"
                            console.print(f"[green]{close_log} (PnL: ${pos_pnl:+.2f})[/green]")
                        except Exception as e:
                            file_logger.info(f"POSITION CLOSE FAILED | {pos_side} {pos_size:.6f} BTC | uPnL: ${pos_pnl:+.2f} | Error: {e}")
                            console.print(f"[red]Failed to close position: {e}[/red]")

                        await asyncio.sleep(REFRESH_INTERVAL)
                        continue

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
                    # USE_MID_DRIFT가 True면 mark drift + mid drift 합산, False면 mark drift만
                    effective_drift = (drift_bps + mid_diff_bps) if USE_MID_DRIFT else drift_bps
                    # mark-mid 차이가 너무 크면 주문 대기 (MARK_MID_DIFF_LIMIT > 0일 때만)
                    mid_unstable = MARK_MID_DIFF_LIMIT > 0 and mid_diff_bps > MARK_MID_DIFF_LIMIT

                    if order_size <= 0:
                        status = "NO_SIZE"
                    elif not buy_is_maker or not sell_is_maker:
                        status = "WAITING"
                    elif mid_unstable and not has_orders:
                        status = "MID_WAIT"  # mid drift 안정화 대기
                    elif has_orders:
                        if effective_drift > DRIFT_THRESHOLD:
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
                        countdown = max(0.0, MIN_WAIT_SEC - time_with_orders)
                        can_modify_orders = time_with_orders >= MIN_WAIT_SEC
                    else:
                        orders_exist_since = None  # 주문 없으면 리셋
                        countdown = 0.0
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
                    elif has_orders and effective_drift > DRIFT_THRESHOLD and can_modify_orders:
                        await order_mgr.cancel_all("Drift exceeded threshold")
                        order_mgr.rebalance()
                        buy_order = await order_mgr.place_order("buy", buy_price, order_size, mark_price)
                        sell_order = await order_mgr.place_order("sell", sell_price, order_size, mark_price)
                        drift_info = f"{drift_bps:.1f}+{mid_diff_bps:.1f}" if USE_MID_DRIFT else f"{drift_bps:.1f}"
                        last_action = f"Rebalanced @ {format_price(mark_price)} (drift: {drift_info}bps)"
                        orders_exist_since = current_time  # 새 주문이니 타이머 리셋

                    # 주문이 없고 maker 조건 충족 - 신규 주문 (mid drift 안정 시에만)
                    elif not has_orders and buy_is_maker and sell_is_maker and not mid_unstable:
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

                    # ========== 6. 스냅샷 저장 ==========
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
                            pass  # 스냅샷 실패해도 무시

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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # 이미 main()에서 처리됨
