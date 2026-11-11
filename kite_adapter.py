"""Read-only Kite Connect adapter. Order placement is disabled in advisory mode."""
import os, datetime as dt
import pandas as pd
import store

class KiteAdapter:
    def __init__(self, access_token: str | None = None):
        from kiteconnect import KiteConnect  # imported here so tests run without it
        self.kite = KiteConnect(api_key=os.environ["KITE_API_KEY"])
        self.kite.set_access_token(access_token or os.environ["KITE_ACCESS_TOKEN"])
        self._instr = None

    def instruments(self) -> pd.DataFrame:
        if self._instr is None:
            self._instr = pd.DataFrame(self.kite.instruments("NSE"))
        return self._instr

    def equity_symbols(self) -> set[str]:
        df = self.instruments()
        return set(df[df["instrument_type"] == "EQ"]["tradingsymbol"])

    def instrument_token(self, symbol: str) -> int:
        df = self.instruments()
        row = df[(df["tradingsymbol"] == symbol) & (df["instrument_type"] == "EQ")]
        if row.empty:
            raise ValueError(f"{symbol} is not an NSE equity symbol")
        return int(row.iloc[0]["instrument_token"])

    def get_quote(self, symbol: str) -> dict:
        key = f"NSE:{symbol}"
        return self.kite.quote([key])[key]

    def get_historical(self, symbol: str, interval: str, days: int) -> pd.DataFrame:
        token = self.instrument_token(symbol)
        end = dt.datetime.now(store.IST)
        rows = self.kite.historical_data(token, end - dt.timedelta(days=days), end, interval)
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    def place_order(self, *args, **kwargs):
        raise RuntimeError("Advisory mode: order placement is disabled in this kit.")
