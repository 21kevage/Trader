from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date

@dataclass(frozen=True)
class Bar:
    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    spread_bps: float = 15.0

@dataclass(frozen=True)
class Proposal:
    symbol: str
    side: str
    quantity: int
    signal_date: date
    rationale: str
    stop_pct: float = 0.04

@dataclass(frozen=True)
class PendingOrder:
    proposal: Proposal
    order_id: str
    limit_price: float

@dataclass(frozen=True)
class Fill:
    date: date
    symbol: str
    side: str
    quantity: int
    price: float
    fee: float
    order_id: str

@dataclass
class Position:
    quantity: int
    average_price: float
    stop_price: float

@dataclass
class Portfolio:
    cash: float = 1000.0
    positions: dict[str, Position] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    fees: float = 0.0
    realized_pnl: float = 0.0
    peak_equity: float = 1000.0
    last_equity: float = 1000.0
    previous_equity: float = 1000.0
    day_start_equity: float = 1000.0
    week_start_equity: float = 1000.0
    last_date: date | None = None
    traded_date_count: dict[date, int] = field(default_factory=dict)
    last_buy_date: dict[str, date] = field(default_factory=dict)

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(p.quantity * prices.get(s, p.average_price) for s, p in self.positions.items())

@dataclass(frozen=True)
class Audit:
    date: date
    actor: str
    kind: str
    message: str
