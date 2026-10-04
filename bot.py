import os
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import ccxt
import pandas as pd
import ta
import requests
import time
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

TIMEFRAME = "30m"

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "TRX/USDT", "POL/USDT", "SHIB/USDT", "LTC/USDT", "UNI/USDT",
    "ATOM/USDT", "XLM/USDT", "NEAR/USDT", "APT/USDT", "SUI/USDT",
    "ARB/USDT", "OP/USDT", "INJ/USDT", "TIA/USDT", "FIL/USDT",
    "AAVE/USDT", "GRT/USDT", "PEPE/USDT", "QNT/USDT", "FET/USDT"
]

def get_decimals(price):
    if price > 100:
        return 2
    elif price > 1:
        return 3
    elif price > 0.01:
        return 5
    else:
        return 8

def send_crypto_signal(coin_name, direction, entry, leverage, tp1, tp2, sl):
    direction_text = "LONG" if direction.lower() == "long" else "SHORT"

    text = (
        f"<b>New Call on: Weex Platform</b>\n"
        f"<i>Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}</i>\n"
        f"<b>Trade:</b> <code>{coin_name}</code>\n\n"
        f"<b>Direction:</b> <code>{direction_text}</code>\n"
        f"<b>Entry:</b> <code>{entry}</code>\n"
        f"<b>Leverage:</b> <code>{leverage}x</code>\n\n"
        f"<b>Target 1 (TP1):</b> <code>{tp1}</code>\n"
        f"<b>Target 2 (TP2):</b> <code>{tp2}</code>\n\n"
        f"<b>Stop Loss (SL):</b> <code>{sl}</code>\n"
        f"-----------\n"
        f"Trade on Weex - Win 10k 🔥\n"
        f"www.weex.com/register?vipCode=0s0t4s"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        if response.json().get('ok'):
            print(f"Signal sent for {coin_name}")
        else:
            print(f"TELEGRAM ERROR for {coin_name}: {response.json().get('description')}")
    except Exception as e:
        print(f"Network error: {e}")

def analyze_and_trade():
    print("Starting scan (30m) with EMA + MACD strategies...")
    exchange = ccxt.mexc()

    for symbol in SYMBOLS:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
            df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()

            curr_ema9 = df['ema_9'].iloc[-1]
            curr_ema21 = df['ema_21'].iloc[-1]
            prev_ema9 = df['ema_9'].iloc[-2]
            prev_ema21 = df['ema_21'].iloc[-2]

            ema_buy = (prev_ema9 < prev_ema21) and (curr_ema9 > curr_ema21)
            ema_sell = (prev_ema9 > prev_ema21) and (curr_ema9 < curr_ema21)

            macd_hist = ta.trend.macd_diff(df['close'])
            curr_macd = macd_hist.iloc[-1]
            prev_macd = macd_hist.iloc[-2]

            macd_buy = (prev_macd < 0) and (curr_macd > 0)
            macd_sell = (prev_macd > 0) and (curr_macd < 0)

            current_close = df['close'].iloc[-1]
            decimals = get_decimals(current_close)

            if ema_buy or macd_buy:
                print(f"BUY SIGNAL on {symbol}!")
                entry = round(current_close, decimals)
                tp1 = round(entry * 1.0065, decimals)
                tp2 = round(entry * 1.02, decimals)
                sl = round(entry * 0.98, decimals)
                send_crypto_signal(symbol, "LONG", str(entry), "10", str(tp1), str(tp2), str(sl))
                time.sleep(2)

            elif ema_sell or macd_sell:
                print(f"SELL SIGNAL on {symbol}!")
                entry = round(current_close, decimals)
                tp1 = round(entry * 0.9935, decimals)
                tp2 = round(entry * 0.98, decimals)
                sl = round(entry * 1.02, decimals)
                send_crypto_signal(symbol, "SHORT", str(entry), "10", str(tp1), str(tp2), str(sl))
                time.sleep(2)
            else:
                print(f"No signal for {symbol} currently.")

        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

if __name__ == "__main__":
    print("Bot started successfully...")
    analyze_and_trade()
