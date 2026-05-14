from pydantic import BaseModel
import json
from dotenv import load_dotenv
from datetime import datetime
from market import get_share_price
from database import write_account, read_account, write_log, make_key

load_dotenv(override=True)

DEFAULT_INITIAL_BALANCE = 20_000.0
SPREAD = 0.002
LOCAL_SESSION_ID = "local"


class Transaction(BaseModel):
    symbol: str
    quantity: int
    price: float
    timestamp: str
    rationale: str

    def total(self) -> float:
        return self.quantity * self.price

    def __repr__(self):
        return f"{abs(self.quantity)} shares of {self.symbol} at {self.price} each."


class Account(BaseModel):
    name: str
    session_id: str = LOCAL_SESSION_ID
    balance: float
    strategy: str
    holdings: dict[str, int]
    transactions: list[Transaction]
    portfolio_value_time_series: list[tuple[str, float]]

    @property
    def key(self) -> str:
        return make_key(self.name, self.session_id)

    @property
    def log_key(self) -> str:
        return self.key

    @classmethod
    def get(cls, name: str, session_id: str = LOCAL_SESSION_ID, initial_balance: float = DEFAULT_INITIAL_BALANCE):
        key = make_key(name, session_id)
        fields = read_account(key)
        if not fields:
            fields = {
                "name": name.lower(),
                "session_id": session_id,
                "balance": initial_balance,
                "strategy": "",
                "holdings": {},
                "transactions": [],
                "portfolio_value_time_series": [],
            }
            write_account(key, fields)
        else:
            fields.setdefault("session_id", session_id)
        return cls(**fields)

    def save(self):
        write_account(self.key, self.model_dump())

    def reset(self, strategy: str, initial_balance: float = DEFAULT_INITIAL_BALANCE):
        self.balance = initial_balance
        self.strategy = strategy
        self.holdings = {}
        self.transactions = []
        self.portfolio_value_time_series = []
        self.save()

    def deposit(self, amount: float):
        if amount <= 0:
            raise ValueError("Deposit amount must be positive.")
        self.balance += amount
        self.save()

    def withdraw(self, amount: float):
        if amount > self.balance:
            raise ValueError("Insufficient funds for withdrawal.")
        self.balance -= amount
        self.save()

    def buy_shares(self, symbol: str, quantity: int, rationale: str) -> str:
        price = get_share_price(symbol)
        buy_price = price * (1 + SPREAD)
        total_cost = buy_price * quantity

        if total_cost > self.balance:
            raise ValueError("Insufficient funds to buy shares.")
        elif price == 0:
            raise ValueError(f"Unrecognized symbol {symbol}")

        self.holdings[symbol] = self.holdings.get(symbol, 0) + quantity
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        transaction = Transaction(
            symbol=symbol, quantity=quantity, price=buy_price, timestamp=timestamp, rationale=rationale
        )
        self.transactions.append(transaction)

        self.balance -= total_cost
        self.save()
        write_log(self.log_key, "account", f"Bought {quantity} of {symbol}")
        return "Completed. Latest details:\n" + self.report()

    def sell_shares(self, symbol: str, quantity: int, rationale: str) -> str:
        if self.holdings.get(symbol, 0) < quantity:
            raise ValueError(f"Cannot sell {quantity} shares of {symbol}. Not enough shares held.")

        price = get_share_price(symbol)
        sell_price = price * (1 - SPREAD)
        total_proceeds = sell_price * quantity

        self.holdings[symbol] -= quantity
        if self.holdings[symbol] == 0:
            del self.holdings[symbol]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        transaction = Transaction(
            symbol=symbol, quantity=-quantity, price=sell_price, timestamp=timestamp, rationale=rationale
        )
        self.transactions.append(transaction)

        self.balance += total_proceeds
        self.save()
        write_log(self.log_key, "account", f"Sold {quantity} of {symbol}")
        return "Completed. Latest details:\n" + self.report()

    def calculate_portfolio_value(self):
        total_value = self.balance
        for symbol, quantity in self.holdings.items():
            total_value += get_share_price(symbol) * quantity
        return total_value

    def calculate_profit_loss(self, portfolio_value: float):
        initial_spend = sum(transaction.total() for transaction in self.transactions)
        return portfolio_value - initial_spend - self.balance

    def get_holdings(self):
        return self.holdings

    def list_transactions(self):
        return [transaction.model_dump() for transaction in self.transactions]

    def report(self) -> str:
        portfolio_value = self.calculate_portfolio_value()
        self.portfolio_value_time_series.append((datetime.now().strftime("%Y-%m-%d %H:%M:%S"), portfolio_value))
        self.save()
        pnl = self.calculate_profit_loss(portfolio_value)
        data = self.model_dump()
        data["total_portfolio_value"] = portfolio_value
        data["total_profit_loss"] = pnl
        write_log(self.log_key, "account", "Retrieved account details")
        return json.dumps(data)

    def get_strategy(self) -> str:
        write_log(self.log_key, "account", "Retrieved strategy")
        return self.strategy

    def change_strategy(self, strategy: str) -> str:
        self.strategy = strategy
        self.save()
        write_log(self.log_key, "account", "Changed strategy")
        return "Changed strategy"
