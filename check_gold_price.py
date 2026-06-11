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
# เพิ่ม M30 เข้ามาในรายการ
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
    """ประมวลผลเงื่อนไขต่างๆ เพื่อหาจุดเข้า BUY / SELL / WAIT"""
    signals = {"ma": "WAIT", "rsi": "WAIT", "stoch": "WAIT", "macd": "WAIT"}

    # 1. เงื่อนไข MA: เรียงตัวกันไม่ได้พันกัน
    ma_vals = [ma_dict['ma20'], ma_dict['ma21'], ma_dict['ma50'], ma_dict['ma100'], ma_dict['ma200']]
    if all(v is not None for v in ma_vals):
        if ma_vals[0] > ma_vals[1] > ma_vals[2] > ma_vals[3] > ma_vals[4]:
            signals["ma"] = "BUY"
        elif ma_vals[0] < ma_vals[1] < ma_vals[2] < ma_vals[3] < ma_vals[4]:
            signals["ma"] = "SELL"

    # 2. เงื่อนไข RSI
    if rsi_val is not None:
        if rsi_val >= 70:
            signals["rsi"] = "SELL"
        elif rsi_val <= 30:
            signals["rsi"] = "BUY"

    # 3. เงื่อนไข Stochastic
    k, d = stoch_dict['k'], stoch_dict['d']
    if k is not None and d is not None:
        if k < d and d >= 80:  # ตัดลงในโซน Overbought
            signals["stoch"] = "SELL"
        elif k > d and d <= 20:  # ตัดขึ้นในโซน Oversold
            signals["stoch"] = "BUY"

    # 4. เงื่อนไข MACD
    m_val, sig, hist = macd_dict['macd'], macd_dict['signal'], macd_dict['histogram']
    if all(v is not None for v in (m_val, sig, hist)):
        if m_val < sig and hist < 0:
            signals["macd"] = "SELL"
        elif m_val > sig and hist > 0:
            signals["macd"] = "BUY"

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

        # ประมวลผลสัญญาณ
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
        "timeframes": indicators,
    }


def fmt_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.{digits}f}"


def signal_icon(status: str) -> str:
    """แปลงข้อความสถานะเป็นไอคอนสีให้ดูง่ายขึ้น"""
    if status == "BUY": return "🟢BUY"
    if status == "SELL": return "🔴SELL"
    return "⚪WAIT"


def telegram_message(quote: dict[str, Any]) -> str:
    checked_at_th = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime(
        "%d/%m/%Y %H:%M"
    )
    change_abs = quote["change_abs"]
    change_percent = quote["change_percent"]
    
    message = (
        "AI GOLD PRICE CHECKER\n\n"
        f"เวลาไทย: {checked_at_th}\n"
        f"ราคา: {fmt_number(quote['close'], 3)} {quote['currency']}\n"
        f"เปลี่ยนแปลง: {change_abs:+.3f} ({change_percent:+.2f}%)\n"
        f"Symbol: {quote['symbol']} ({quote['description']})\n"
        f"Exchange: {quote['exchange']}\n"
    )
    
    # เพิ่มส่วนสรุปสัญญาณไว้ใต้ Exchange ทันที
    message += "\n📊 สรุปสัญญาณเทคนิค:\n"
    for label, _ in TIMEFRAMES:
        sigs = quote["timeframes"][label]["signals"]
        message += f"[{label}] MA:{signal_icon(sigs['ma'])} | STOCH:{signal_icon(sigs['stoch'])} | RSI:{signal_icon(sigs['rsi'])} | MACD:{signal_icon(sigs['macd'])}\n"

    for label, _ in TIMEFRAMES:
        frame = quote["timeframes"][label]
        ma = frame["ma"]
        stoch = frame["stoch"]
        macd = frame["macd"]
        message += (
            f"\n\nTF {label}\n"
            f"MA20/21/50: {fmt_number(ma['ma20'])} / "
            f"{fmt_number(ma['ma21'])} / {fmt_number(ma['ma50'])}\n"
            f"MA100/200: {fmt_number(ma['ma100'])} / {fmt_number(ma['ma200'])}\n"
            f"RSI: {fmt_number(frame['rsi'])}\n"
            f"Stoch K/D: {fmt_number(stoch['k'])} / {fmt_number(stoch['d'])}\n"
            f"MACD: {fmt_number(macd['macd'])}, "
            f"Signal: {fmt_number(macd['signal'])}, "
            f"Hist: {fmt_number(macd['histogram'])}"
        )

    message += f"\n\nSource: {quote['source']}\nChart: {quote['chart_url']}"
    return message


def send_telegram_message(text: str, insecure: bool = False) -> int:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_ids = [os.environ.get("TELEGRAM_CHAT_ID")]
    chat_ids.extend(os.environ.get(name) for name in TELEGRAM_GROUP_ENV_NAMES)
    chat_ids = [chat_id for chat_id in chat_ids if chat_id]

    if not token:
        print("Telegram skipped: TELEGRAM_TOKEN is not set.")
        return 0
    if not chat_ids:
        print("Telegram skipped: no TELEGRAM_CHAT_ID or group chat ids are set.")
        return 0

    sent = 0
    for chat_id in chat_ids:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode(
            "utf-8"
        )
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=20, context=ssl_context(insecure=insecure)
            ) as response:
                response.read()
            print(f"Telegram sent to {chat_id}.")
            sent += 1
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"Telegram failed for {chat_id}: HTTP {exc.code} {detail}")
        except urllib.error.URLError as exc:
            print(f"Telegram failed for {chat_id}: {exc.reason}")

    return sent


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
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Do not send the result to Telegram even when Telegram environment variables are set.",
    )
    args = parser.parse_args()

    try:
        row = fetch_quote(args.symbols, insecure=args.insecure)
        quote = format_quote(row)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not args.no_telegram:
        send_telegram_message(telegram_message(quote), insecure=args.insecure)

    if args.json:
        print(json.dumps(quote, ensure_ascii=False, indent=2))
        return 0

    print(f"Gold price: {quote['close']} {quote['currency']}")
    print(f"Symbol: {quote['symbol']} ({quote['description']})")
    print(f"Change: {quote['change_abs']} ({quote['change_percent']}%)")
    
    print("\n[Technical Signals Summary]")
    for label, _ in TIMEFRAMES:
        sigs = quote["timeframes"][label]["signals"]
        print(f"[{label}] MA: {sigs['ma']}, STOCH: {sigs['stoch']}, RSI: {sigs['rsi']}, MACD: {sigs['macd']}")
    
    print("\n[Details]")
    for label, _ in TIMEFRAMES:
        frame = quote["timeframes"][label]
        print(
            f"TF {label}: "
            f"MA20={fmt_number(frame['ma']['ma20'])}, "
            f"MA21={fmt_number(frame['ma']['ma21'])}, "
            f"MA50={fmt_number(frame['ma']['ma50'])}, "
            f"MA100={fmt_number(frame['ma']['ma100'])}, "
            f"MA200={fmt_number(frame['ma']['ma200'])}, "
            f"RSI={fmt_number(frame['rsi'])}, "
            f"Stoch={fmt_number(frame['stoch']['k'])}/{fmt_number(frame['stoch']['d'])}, "
            f"MACD={fmt_number(frame['macd']['macd'])}, "
            f"Signal={fmt_number(frame['macd']['signal'])}, "
            f"Hist={fmt_number(frame['macd']['histogram'])}"
        )
    print(f"\nChecked at UTC: {quote['checked_at_utc']}")
    print(f"Source: {quote['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
