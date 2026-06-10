#!/usr/bin/env python3
"""Check the latest gold price from TradingView public scanner data."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


TRADINGVIEW_SCAN_URL = "https://scanner.tradingview.com/global/scan"
DEFAULT_SYMBOLS = [
    "OANDA:XAUUSD",
    "FOREXCOM:XAUUSD",
    "FX_IDC:XAUUSD",
    "TVC:GOLD",
]


def ssl_context(insecure: bool = False) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()

    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()

    return ssl.create_default_context(cafile=certifi.where())


def fetch_quote(symbols: list[str], insecure: bool = False) -> dict[str, Any]:
    payload = {
        "symbols": {"tickers": symbols, "query": {"types": []}},
        "columns": [
            "name",
            "description",
            "exchange",
            "type",
            "subtype",
            "close",
            "change",
            "change_abs",
            "currency",
            "update_mode",
        ],
    }

    request = urllib.request.Request(
        TRADINGVIEW_SCAN_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "gold-price-checker/1.0",
            "Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/7iq3bDfZ/",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=20, context=ssl_context(insecure=insecure)
        ) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"TradingView HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot connect to TradingView: {exc.reason}") from exc

    data = json.loads(body)
    rows = data.get("data") or []
    if not rows:
        raise RuntimeError("TradingView returned no quote rows.")

    for row in rows:
        values = row.get("d") or []
        if len(values) >= 6 and values[5] is not None:
            return {"symbol": row.get("s"), "values": values}

    raise RuntimeError("TradingView returned rows, but none included a latest price.")


def format_quote(row: dict[str, Any]) -> dict[str, Any]:
    values = row["values"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "checked_at_utc": now,
        "source": "TradingView scanner",
        "chart_url": "https://www.tradingview.com/chart/7iq3bDfZ/",
        "symbol": row["symbol"],
        "name": values[0],
        "description": values[1],
        "exchange": values[2],
        "instrument_type": values[3],
        "close": values[5],
        "change_percent": values[6],
        "change_abs": values[7],
        "currency": values[8],
        "update_mode": values[9],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch latest gold price data from TradingView."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help="TradingView tickers to try, in priority order.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification. Use only for local testing behind a corporate proxy.",
    )
    args = parser.parse_args()

    try:
        row = fetch_quote(args.symbols, insecure=args.insecure)
        quote = format_quote(row)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(quote, ensure_ascii=False, indent=2))
        return 0

    print(f"Gold price: {quote['close']} {quote['currency']}")
    print(f"Symbol: {quote['symbol']} ({quote['description']})")
    print(f"Change: {quote['change_abs']} ({quote['change_percent']}%)")
    print(f"Checked at UTC: {quote['checked_at_utc']}")
    print(f"Source: {quote['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
