from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.core.base import Order
from src.execution.order import OrderFactory
from src.data.store import TradeStore


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[int] = None
    message: str = ""
    executed_price: float = 0.0
    executed_volume: int = 0


class Broker(ABC):
    @abstractmethod
    def buy(self, order: Order) -> OrderResult:
        ...

    @abstractmethod
    def sell(self, order: Order) -> OrderResult:
        ...


class RealBroker(Broker):
    """实盘券商接口基类 - 继承此类实现具体券商对接"""

    def __init__(self):
        self.trade_store = TradeStore()
        self._connected = False

    def connect(self) -> bool:
        raise NotImplementedError

    def buy(self, order: Order) -> OrderResult:
        raise NotImplementedError

    def sell(self, order: Order) -> OrderResult:
        raise NotImplementedError

    def get_position(self, code: str) -> Optional[dict]:
        raise NotImplementedError

    def get_account_balance(self) -> float:
        raise NotImplementedError


class XtQuantBroker(RealBroker):
    """迅投QMT券商接口

    需安装: pip install xtquant
    使用方式:
        1. 在券商开通QMT权限
        2. 运行QMT终端，启动量化交易
        3. xtquant会自动连接QMT终端
    """

    def __init__(self, account_id: str = "", password: str = ""):
        super().__init__()
        self.account_id = account_id
        self.password = password

    def connect(self) -> bool:
        try:
            from xtquant import xtdata
            xtdata.connect()
            self._connected = True
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def buy(self, order: Order) -> OrderResult:
        try:
            from xtquant import xttrader
            from xtquant.xttype import StockAccount

            account = StockAccount(self.account_id)
            # 异步下单，返回订单ID
            order_id = xttrader.trade.order_stock(
                account, order.code, 1, order.price, order.volume,
                quote_type=1, order_type=0,
            )
            self.trade_store.save_order(order)
            return OrderResult(
                success=True, order_id=order_id,
                executed_price=order.price, executed_volume=order.volume,
                message="QMT下单成功",
            )
        except ImportError:
            return OrderResult(success=False, message="需安装xtquant")
        except Exception as e:
            return OrderResult(success=False, message=f"QMT下单失败: {e}")

    def sell(self, order: Order) -> OrderResult:
        try:
            from xtquant import xttrader
            from xtquant.xttype import StockAccount

            account = StockAccount(self.account_id)
            order_id = xttrader.trade.order_stock(
                account, order.code, 2, order.price, order.volume,
                quote_type=1, order_type=0,
            )
            self.trade_store.save_order(order)
            return OrderResult(
                success=True, order_id=order_id,
                executed_price=order.price, executed_volume=order.volume,
                message="QMT卖单成功",
            )
        except ImportError:
            return OrderResult(success=False, message="需安装xtquant")
        except Exception as e:
            return OrderResult(success=False, message=f"QMT卖单失败: {e}")

    def get_position(self, code: str) -> Optional[dict]:
        try:
            from xtquant import xtdata
            positions = xtdata.get_stock_position(self.account_id, code)
            return positions
        except Exception:
            return None

    def get_account_balance(self) -> float:
        try:
            from xtquant import xtdata
            balance = xtdata.get_account_balance(self.account_id)
            return balance.get("available", 0)
        except Exception:
            return 0.0


class MockBroker(Broker):
    def __init__(self):
        self.trade_store = TradeStore()
        self._trade_counter = 0

    def buy(self, order: Order) -> OrderResult:
        self._trade_counter += 1
        result = OrderResult(
            success=True,
            executed_price=order.price,
            executed_volume=order.volume,
            order_id=self._trade_counter,
            message="模拟买入成交",
        )
        executed = OrderFactory.create_market_order(
            code=order.code, name=order.name, direction="buy",
            price=order.price, volume=order.volume,
            reason=order.reason, signal_id=order.signal_id,
        )
        executed.status = "filled"
        executed.executed_at = datetime.now().isoformat()
        executed.fee = round(order.amount * 0.00025, 2)
        self.trade_store.save_order(executed)
        return result

    def sell(self, order: Order) -> OrderResult:
        self._trade_counter += 1
        result = OrderResult(
            success=True,
            executed_price=order.price,
            executed_volume=order.volume,
            order_id=self._trade_counter,
            message="模拟卖出成交",
        )
        executed = OrderFactory.create_market_order(
            code=order.code, name=order.name, direction="sell",
            price=order.price, volume=order.volume,
            reason=order.reason, signal_id=order.signal_id,
        )
        executed.status = "filled"
        executed.executed_at = datetime.now().isoformat()
        executed.fee = round(order.amount * 0.00025, 2)
        self.trade_store.save_order(executed)
        return result
