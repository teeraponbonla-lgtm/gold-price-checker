# Gold Price Checker

Small Python script and GitHub Actions workflow for checking the latest gold price from TradingView public scanner data.

The script prioritizes `OANDA:XAUUSD`, then falls back to `FOREXCOM:XAUUSD`, `FX_IDC:XAUUSD`, and `TVC:GOLD`.

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

## Run on GitHub

1. Put these files in a GitHub repository.
2. Push the repository.
3. Open **Actions**.
4. Select **Check latest gold price**.
5. Click **Run workflow**.

The workflow also runs every 30 minutes.

## Notes

The TradingView chart URL is kept as the referer/source context:

```text
https://www.tradingview.com/chart/7iq3bDfZ/
```

The chart layout ID does not reliably expose its current symbol without logging in or driving a browser session, so the script uses TradingView's public scanner endpoint for gold market symbols instead.
