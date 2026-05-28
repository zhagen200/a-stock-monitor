from typing import Optional, Callable
from datetime import datetime

from src.core.base import TradeSignal, Order
from src.data.store import SignalStore, TradeStore
from src.risk.manager import RiskManager
from src.execution.broker import Broker, MockBroker, OrderResult
from src.execution.order import OrderFactory
from src.notify.notifier import Notifier


class SignalBus:
    def __init__(
        self,
        risk_manager: RiskManager,
        broker: Optional[Broker] = None,
        notifier: Optional[Notifier] = None,
        auto_execute: bool = False,
    ):
        self.risk_manager = risk_manager
        self.broker = broker or MockBroker()
        self.notifier = notifier
        self.auto_execute = auto_execute
        self.signal_store = SignalStore()
        self._on_signal_callbacks: list[Callable] = []

    def on_signal(self, callback: Callable):
        self._on_signal_callbacks.append(callback)

    def process(self, signal: TradeSignal, context: dict = None) -> Optional[OrderResult]:
        if context is None:
            context = {}

        risk_result = self.risk_manager.check(signal, context)
        signal_id = self.signal_store.save_signal(signal)
        signal.strategy_name = "ensemble"

        if self.notifier and signal.action not in ("hold",):
            self.notifier.send_signal(signal)

        for cb in self._on_signal_callbacks:
            cb(signal, risk_result)

        if not risk_result.passed:
            return None

        if not self.auto_execute:
            return None

        if signal.action not in ("strong_buy", "buy", "strong_sell", "sell"):
            return None

        direction = "buy" if signal.action in ("strong_buy", "buy") else "sell"

        order = OrderFactory.create_market_order(
            code=signal.code,
            name=signal.name,
            direction=direction,
            price=signal.price,
            volume=int(signal.position_pct * 100) if direction == "buy" else 0,
            reason="; ".join(signal.reasons[:3]),
            signal_id=signal_id,
        )

        if direction == "buy":
            return self.broker.buy(order)
        else:
            return self.broker.sell(order)
