import os
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import ccxt
import pandas as pd
import numpy as np
import requests
import time
import json
from datetime import datetime
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ================= Configuration =================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN') or os.environ.get('BOT_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')

TIMEFRAME_ENTRY = '15m'
TIMEFRAME_TREND = '1h'
TOP_N_COINS = 20
LEVERAGE = 12

# ✅ وقف خسارة ثابت 6%
SL_PERCENT = 6.0

# Targets (8 levels) — من 0.85% إلى 10% بفاصل ثابت 1.307%
TP_PERCENTAGES = [0.85, 2.157143, 3.464286, 4.771429, 6.078571, 7.385714, 8.692857, 10.0]

# Risk / Entries
ENTRY2_ATR_MULT = 0.5

# Quality Filters
MIN_ATR_PERCENT = 0.03
VOLUME_LOOKBACK = 20
COOLDOWN_HOURS = 1
COOLDOWN_FILE = Path('cooldown.json')

# ✅ قائمة بيضاء بأزواج Futures الموثوقة فقط
WHITELIST = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "TRX/USDT", "LTC/USDT", "UNI/USDT", "ATOM/USDT", "XLM/USDT",
    "NEAR/USDT", "APT/USDT", "SUI/USDT", "ARB/USDT", "OP/USDT",
    "INJ/USDT", "FIL/USDT", "AAVE/USDT", "QNT/USDT", "FET/USDT",
    "RENDER/USDT", "TIA/USDT", "SEI/USDT", "PYTH/USDT", "STRK/USDT",
    "WLD/USDT", "ENA/USDT", "WIF/USDT", "BONK/USDT", "PEPE/USDT",
    "SHIB/USDT", "FLOKI/USDT", "BOME/USDT", "W/USDT", "JUP/USDT"
]

STABLECOINS = ['USDC/USDT', 'TUSD/USDT', 'DAI/USDT', 'FDUSD/USDT', 'USDP/USDT', 'PYUSD/USDT']
BLACKLIST = ['WXT/USDT', 'ANTFUN/USDT', 'UPC/USDT', 'RAIN/USDT', 'USD1/USDT', 'USDE/USDT', 'BEAT/USDT', 'AKE/USDT', 'MY/USDT', 'MBG/USDT', 'AIX/USDT', 'XPLK/USDT', 'ZAY/USDT', '9BIT/USDT', 'CYS/USDT', 'GOLD/USDT']


def _fmt(price):
    if price >= 1000:   return f"{price:,.2f}"
    elif price >= 1:    return f"{price:,.4f}"
    else:              return f"{price:,.6f}"


def load_cooldown():
    if COOLDOWN_FILE.exists():
        try:
            with open(COOLDOWN_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cooldown(data):
    try:
        with open(COOLDOWN_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save cooldown: {e}")


def is_on_cooldown(symbol, cooldown_data):
    if symbol not in cooldown_data:
        return False
    try:
        last_time = datetime.fromisoformat(cooldown_data[symbol])
        elapsed = (datetime.now() - last_time).total_seconds() / 3600
        return elapsed < COOLDOWN_HOURS
    except Exception:
        return False


def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHANNEL_ID:
        print("Missing TELEGRAM_TOKEN or CHANNEL_ID")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHANNEL_ID,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        if not r.json().get('ok'):
            print(f"Telegram error: {r.json().get('description')}")
    except Exception as e:
        print(f"Network error sending Telegram: {e}")


def get_mexc_data(symbol, timeframe, limit=150):
    exchange = ccxt.mexc({'enableRateLimit': True})
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df


def get_top_mexc_coins(limit=50):
    print(f"Fetching top {limit} coins by volume from MEXC...")
    exchange = ccxt.mexc({'enableRateLimit': True})
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = []
        for symbol, ticker in tickers.items():
            # ✅ فقط الأزواج الموجودة في WHITELIST
            if symbol in WHITELIST:
                vol = ticker.get('quoteVolume') or 0
                if vol > 200000:
                    usdt_pairs.append({'symbol': symbol, 'volume': vol})
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
        top = [p['symbol'] for p in usdt_pairs[:limit]]
        print(f"Top coins: {top[:5]} ... ({len(top)} total)")
        return top
    except Exception as e:
        print(f"Error fetching coins: {e}")
        return []


def calculate_atr(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def analyze_symbol(symbol):
    try:
        df_15m = get_mexc_data(symbol, TIMEFRAME_ENTRY, limit=150)
        df_1h = get_mexc_data(symbol, TIMEFRAME_TREND, limit=100)

        if len(df_15m) < 50 or len(df_1h) < 50:
            return None

        # === Trend Filter on 1H ===
        df_1h['ema50'] = df_1h['close'].ewm(span=50, adjust=False).mean()
        price_1h = df_1h['close'].iloc[-1]
        ema50_1h = df_1h['ema50'].iloc[-1]
        trend_bullish = price_1h > ema50_1h
        trend_bearish = price_1h < ema50_1h

        # === Indicators on 15m ===
        df_15m['ema9'] = df_15m['close'].ewm(span=9, adjust=False).mean()
        df_15m['ema21'] = df_15m['close'].ewm(span=21, adjust=False).mean()

        # RSI
        delta = df_15m['close'].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df_15m['rsi'] = 100 - (100 / (1 + rs))

        # MACD Histogram
        ema12 = df_15m['close'].ewm(span=12, adjust=False).mean()
        ema26 = df_15m['close'].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        df_15m['macd_hist'] = macd_line - signal_line

        # ATR & Volume
        df_15m['atr'] = calculate_atr(df_15m, 14)
        df_15m['atr_pct'] = (df_15m['atr'] / df_15m['close']) * 100
        df_15m['vol_sma'] = df_15m['volume'].rolling(window=VOLUME_LOOKBACK).mean()

        # Current values
        ema9 = df_15m['ema9'].iloc[-1]
        ema21 = df_15m['ema21'].iloc[-1]
        ema9_prev = df_15m['ema9'].iloc[-2]
        ema21_prev = df_15m['ema21'].iloc[-2]
        rsi = df_15m['rsi'].iloc[-1]
        macd_hist = df_15m['macd_hist'].iloc[-1]
        macd_hist_prev = df_15m['macd_hist'].iloc[-2]
        atr = df_15m['atr'].iloc[-1]
        atr_pct = df_15m['atr_pct'].iloc[-1]
        vol_now = df_15m['volume'].iloc[-1]
        vol_avg = df_15m['vol_sma'].iloc[-1]
        current_price = df_15m['close'].iloc[-1]

        # === Quality Filters ===
        if pd.isna(atr_pct) or atr_pct < MIN_ATR_PERCENT:
            print(f"  {symbol}: ATR too low ({atr_pct:.3f}%)")
            return None

        if pd.isna(vol_avg) or vol_now < vol_avg * 0.3:
            print(f"  {symbol}: Volume too low")
            return None

        if pd.isna(rsi) or pd.isna(macd_hist):
            print(f"  {symbol}: Indicators not ready")
            return None

        # === Strategy: Smart Trend Pullback ===
        confidence = 50
        direction = None

        # LONG
        if trend_bullish:
            ema_aligned = ema9 > ema21
            ema_cross = (ema9_prev <= ema21_prev) and (ema9 > ema21)
            macd_ok = macd_hist > macd_hist_prev or macd_hist > 0
            rsi_ok = 30 < rsi < 75

            if ema_aligned and macd_ok and rsi_ok:
                direction = "LONG"
                confidence = 65
                if ema_cross: confidence += 10
                if rsi < 60: confidence += 5
                if vol_now > vol_avg * 1.2: confidence += 5
                if macd_hist > 0: confidence += 5

        # SHORT
        elif trend_bearish:
            ema_aligned = ema9 < ema21
            ema_cross = (ema9_prev >= ema21_prev) and (ema9 < ema21)
            macd_ok = macd_hist < macd_hist_prev or macd_hist < 0
            rsi_ok = 25 < rsi < 70

            if ema_aligned and macd_ok and rsi_ok:
                direction = "SHORT"
                confidence = 65
                if ema_cross: confidence += 10
                if rsi > 40: confidence += 5
                if vol_now > vol_avg * 1.2: confidence += 5
                if macd_hist < 0: confidence += 5

        if direction is None:
            print(f"  {symbol}: No signal (Trend: {'UP' if trend_bullish else 'DOWN'}, EMA9/21: {ema9:.2f}/{ema21:.2f}, RSI: {rsi:.1f}, MACD: {macd_hist:.4f})")
            return None

        confidence = min(95, confidence)
        if confidence < 60:
            print(f"  {symbol}: Confidence too low ({confidence}%)")
            return None

        # === Build Signal — Pullback Entries ===
        if direction == "LONG":
            # ✅ Entry1 عند EMA 9 (منطقة الارتداد)
            if current_price > ema9:
                entry1 = ema9
                entry2 = ema9 - (atr * ENTRY2_ATR_MULT)
            else:
                entry1 = current_price
                entry2 = current_price - (atr * ENTRY2_ATR_MULT)

            entry_low = min(entry1, entry2)
            entry_high = max(entry1, entry2)

            # ✅ وقف خسارة ثابت 6% أسفل أدنى نقطة دخول
            sl = entry_low * (1 - SL_PERCENT / 100)

            # ✅ الأهداف الثمانية من أعلى نقطة دخول
            tps = [entry_high * (1 + p / 100) for p in TP_PERCENTAGES]

        else:
            # ✅ Entry1 عند EMA 9 (منطقة الارتداد)
            if current_price < ema9:
                entry1 = ema9
                entry2 = ema9 + (atr * ENTRY2_ATR_MULT)
            else:
                entry1 = current_price
                entry2 = current_price + (atr * ENTRY2_ATR_MULT)

            entry_low = min(entry1, entry2)
            entry_high = max(entry1, entry2)

            # ✅ وقف خسارة ثابت 6% فوق أعلى نقطة دخول
            sl = entry_high * (1 + SL_PERCENT / 100)

            # ✅ الأهداف الثمانية من أدنى نقطة دخول
            tps = [entry_low * (1 - p / 100) for p in TP_PERCENTAGES]

        return {
            'symbol': symbol,
            'direction': direction,
            'entry1': entry1,
            'entry2': entry2,
            'sl': sl,
            'tps': tps,
            'confidence': confidence,
            'atr_pct': atr_pct,
            'sl_pct': SL_PERCENT
        }

    except Exception as e:
        print(f"  {symbol}: Error - {e}")
        return None


def build_message(signal):
    pair = signal['symbol'].replace('/', '')
    direction = signal['direction']

    tp_lines = "\n".join(
        f"TP{i+1} - {_fmt(tp)}" for i, tp in enumerate(signal['tps'])
    )

    msg = f"""{pair} 🚀

Position: {direction}
Leverage: Cross {LEVERAGE}x 
Entry: {_fmt(signal['entry1'])}  -  {_fmt(signal['entry2'])}

SL: {_fmt(signal['sl'])}

Targets
{tp_lines}

Trade on Weex - Win up to 10k 🔥
www.weex.com/register?vipCode=0s0t4s"""

    return msg


def main():
    print("=" * 50)
    print("BULLS SIGNALS — Trend Following Bot (v3.0)")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    if not TELEGRAM_TOKEN or not CHANNEL_ID:
        print("ERROR: TELEGRAM_TOKEN and CHANNEL_ID must be set!")
        return

    top_coins = get_top_mexc_coins(TOP_N_COINS)
    if not top_coins:
        print("No coins fetched. Aborting.")
        return

    cooldown_data = load_cooldown()
    signals_sent = 0
    skipped_cooldown = 0
    skipped_filter = 0

    print("\nScanning coins...")
    for symbol in top_coins:
        try:
            if is_on_cooldown(symbol, cooldown_data):
                skipped_cooldown += 1
                print(f"  {symbol}: On cooldown")
                continue

            time.sleep(0.6)
            signal = analyze_symbol(symbol)

            if signal is None:
                skipped_filter += 1
                continue

            msg = build_message(signal)
            send_telegram(msg)
            cooldown_data[symbol] = datetime.now().isoformat()
            signals_sent += 1
            print(f"  ✅ SIGNAL SENT: {symbol} {signal['direction']} (Conf: {signal['confidence']}%, SL: {signal['sl_pct']:.2f}%)")
            time.sleep(1.5)

        except Exception as e:
            print(f"  {symbol}: Exception - {e}")

    save_cooldown(cooldown_data)
    print(f"\n🏁 Done. Signals: {signals_sent} | Cooldown skipped: {skipped_cooldown} | Filter skipped: {skipped_filter}")


if __name__ == "__main__":
    main()
