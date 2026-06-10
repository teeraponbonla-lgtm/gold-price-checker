# Gold Price Checker

Small Python script and GitHub Actions workflow for checking the latest gold price and technical indicators from TradingView public scanner data.

The script prioritizes `OANDA:XAUUSD`, then falls back to `FOREXCOM:XAUUSD`, `FX_IDC:XAUUSD`, and `TVC:GOLD`.

Included indicators for M15, H1, H4, and D1:

- MA20, MA21, MA50, MA100, MA200
- RSI
- Stoch K/D
- MACD, signal, histogram

## Run locally

```powershell
python check_gold_price.py
python check_gold_price.py --json
```

If local Python is behind a corporate TLS proxy and fails with `CERTIFICATE_VERIFY_FAILED`, test locally with:

```powershell
python check_gold_price.py --json --insecure
```

Use `--insecure` for local testing only. The GitHub Actions workflow uses normal TLS verification.

## Telegram

The script sends Telegram messages automatically when these environment variables are set:

```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
TELEGRAM_GROUP_CHAT_ID_001
TELEGRAM_GROUP_CHAT_ID_002
TELEGRAM_GROUP_CHAT_ID_003
```

Only `TELEGRAM_TOKEN` and at least one chat id are required. To test the price check without sending Telegram:

```powershell
python check_gold_price.py --json --no-telegram
```

## Run on GitHub

1. Put these files in a GitHub repository.
2. Push the repository.
3. Open **Actions**.
4. Select **Check latest gold price**.
5. Click **Run workflow**.

Set these GitHub repository secrets before running the workflow:

```text
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
TELEGRAM_GROUP_CHAT_ID_001
TELEGRAM_GROUP_CHAT_ID_002
TELEGRAM_GROUP_CHAT_ID_003
```

The workflow also runs every 30 minutes.

## Notes

The TradingView chart URL is kept as the referer/source context:

```text
https://www.tradingview.com/chart/7iq3bDfZ/
```

The chart layout ID does not reliably expose its current symbol without logging in or driving a browser session, so the script uses TradingView's public scanner endpoint for gold market symbols instead.
