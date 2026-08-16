"""Minimal Binance USD-M Futures REST client (demo-fapi / fapi)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class BinanceFapiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


class BinanceFapi:
    def __init__(self, api_key: str, api_secret: str, base_url: str):
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")
        self.base_url = base_url.rstrip("/")

    def _sign(self, params: dict[str, Any]) -> str:
        qs = urllib.parse.urlencode(params, doseq=True)
        return hmac.new(self.api_secret, qs.encode("utf-8"), hashlib.sha256).hexdigest()

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        params = dict(params or {})
        headers = {"User-Agent": "scalping-backtest-demo/1.0"}
        if signed:
            if not self.api_key or not self.api_secret:
                raise RuntimeError("API key/secret required for signed endpoints")
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 5000
            params["signature"] = self._sign(params)
            headers["X-MBX-APIKEY"] = self.api_key
        elif self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        qs = urllib.parse.urlencode(params, doseq=True)
        url = f"{self.base_url}{path}"
        data = None
        if method.upper() == "GET":
            if qs:
                url = f"{url}?{qs}"
        else:
            data = qs.encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise BinanceFapiError(e.code, body) from e

    # ---- public ----
    def ping(self) -> Any:
        return self._request("GET", "/fapi/v1/ping")

    def exchange_info(self) -> Any:
        return self._request("GET", "/fapi/v1/exchangeInfo")

    def klines(self, symbol: str, interval: str = "1m", limit: int = 500) -> list:
        return self._request(
            "GET",
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": int(limit)},
        )

    def ticker_price(self, symbol: str) -> float:
        data = self._request("GET", "/fapi/v1/ticker/price", {"symbol": symbol})
        return float(data["price"])

    # ---- private ----
    def balance(self) -> list:
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def account(self) -> dict:
        return self._request("GET", "/fapi/v2/account", signed=True)

    def position_risk(self, symbol: str | None = None) -> list:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/fapi/v2/positionRisk", params, signed=True)

    def change_leverage(self, symbol: str, leverage: int) -> Any:
        return self._request(
            "POST",
            "/fapi/v1/leverage",
            {"symbol": symbol, "leverage": int(leverage)},
            signed=True,
        )

    def leverage_bracket(self, symbol: str | None = None) -> Any:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/fapi/v1/leverageBracket", params, signed=True)

    def change_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> Any:
        return self._request(
            "POST",
            "/fapi/v1/marginType",
            {"symbol": symbol, "marginType": margin_type},
            signed=True,
        )

    def new_order(self, **params: Any) -> Any:
        return self._request("POST", "/fapi/v1/order", params, signed=True)

    def cancel_all(self, symbol: str) -> Any:
        return self._request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol}, signed=True)
