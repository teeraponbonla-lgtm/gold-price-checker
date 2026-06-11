#!/usr/bin/env python3
"""Check the latest gold price from TradingView public scanner data."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


TRADINGVIEW_SCAN_URL = "https://scanner.tradingview.com/global/scan"
BASE_COLUMNS = [
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
]
TIMEFRAMES = [
    ("M15", "15"),
    ("M30", "30"),
    ("H1", "60"),
    ("H4", "240"),
    ("D1", ""),
]
INDICATOR_COLUMNS = [
    "SMA20",
    "SMA21",
    "SMA50",
    "SMA100",
    "SMA200",
    "RSI",
    "Stoch.K",
    "Stoch.D",
    "MACD.macd",
    "MACD.signal",
]
TRADINGVIEW_COLUMNS = BASE_COLUMNS + [
    f"{column}|{interval}" if interval else column
    for _, interval in TIMEFRAMES
    for column in INDICATOR_COLUMNS
]
DEFAULT_SYMBOLS = [
    "OANDA:XAUUSD",
    "FOREXCOM:XAUUSD",
    "FX_IDC:XAUUSD",
    "TVC:GOLD",
]
TELEGRAM_GROUP_ENV_NAMES = [
    "TELEGRAM_GROUP_CHAT_ID_001",
    "TELEGRAM_GROUP_CHAT_ID_002",
    "TELEGRAM_GROUP_CHAT_ID_003",
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
        "columns": TRADINGVIEW_COLUMNS,
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
        if len(values) >= len(TRADINGVIEW_COLUMNS) and values[5] is not None:
            return {"symbol": row.get("s"), "values": values}

    raise RuntimeError(
        "TradingView returned rows, but none included the full price and indicator set."
    )


def analyze_signals(ma_dict: dict, rsi_val: float | None, stoch_dict: dict, macd_dict: dict) -> dict[str, str]:
    signals = {"ma": "WAIT", "rsi": "WAIT", "stoch": "WAIT", "macd": "WAIT"}

    # 1. เงื่อนไข MA ทั้ง 20,21,50,100,200 อยู่เรียงกันไม่ได้พันกันอยู่ในราคาเดียวกัน
    ma_vals = [ma_dict['ma20'], ma_dict['ma21'], ma_dict['ma50'], ma_dict['ma100'], ma_dict['ma200']]
    if all(v is not None for v in ma_vals):
        if ma_vals[0] > ma_vals[1] > ma_vals[2] > ma_vals[3] > ma_vals[4]:
            signals["ma"] = "BUY"
        elif ma_vals[0] < ma_vals[1] < ma_vals[2] < ma_vals[3] < ma_vals[4]:
            signals["ma"] = "SELL"

    # 2. เงื่อนไข Stochastic Oscillator (Stoch K/D)
    k, d = stoch_dict['k'], stoch_dict['d']
    if k is not None and d is not None:
        if k < d and d >= 80:
            signals["stoch"] = "SELL"
        elif k > d and d <= 20:
            signals["stoch"] = "BUY"

    # 3. เงื่อนไข Relative Strength Index (RSI)
    if rsi_val is not None:
        if rsi_val >= 70:
            signals["rsi"] = "SELL"
        elif rsi_val <= 30:
            signals["rsi"] = "BUY"

    # 4. เงื่อนไข MACD (Moving Average Convergence Divergence)
    m_val, sig, hist = macd_dict['macd'], macd_dict['signal'], macd_dict['histogram']
    if all(v is not None for v in (m_val, sig, hist)):
        if m_val > sig and hist > 0:
            signals["macd"] = "BUY"
        elif m_val < sig and hist < 0:
            signals["macd"] = "SELL"

    return signals


def format_quote(row: dict[str, Any]) -> dict[str, Any]:
    values = row["values"]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    indicators = {}
    offset = len(BASE_COLUMNS)
    for label, _ in TIMEFRAMES:
        frame_values = values[offset : offset + len(INDICATOR_COLUMNS)]
        macd = frame_values[8]
        macd_signal = frame_values[9]
        
        frame_ma = {
            "ma20": frame_values[0],
            "ma21": frame_values[1],
            "ma50": frame_values[2],
            "ma100": frame_values[3],
            "ma200": frame_values[4],
        }
        frame_rsi = frame_values[5]
        frame_stoch = {
            "k": frame_values[6],
            "d": frame_values[7],
        }
        frame_macd = {
            "macd": macd,
            "signal": macd_signal,
            "histogram": macd - macd_signal if macd is not None and macd_signal is not None else None,
        }

        signals = analyze_signals(frame_ma, frame_rsi, frame_stoch, frame_macd)

        indicators[label] = {
            "ma": frame_ma,
            "rsi": frame_rsi,
            "stoch": frame_stoch,
            "macd": frame_macd,
            "signals": signals,
        }
        offset += len(INDICATOR_COLUMNS)

    return {
        "checked_at_utc": now,
        "source":