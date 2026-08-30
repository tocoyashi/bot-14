import os
import ssl

import ccxt
import pandas as pd
import ta
import requests
import time
from datetime import datetime

# ─── متغيرات البيئة ───────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

TIMEFRAME = "15m"

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "TRX/USDT", "POL/USDT", "SHIB/USDT", "LTC/USDT", "UNI/USDT",
    "ATOM/USDT", "XLM/USDT", "NEAR/USDT", "APT/USDT", "SUI/USDT",
    "ARB/USDT", "OP/USDT", "INJ/USDT", "TIA/USDT", "FIL/USDT",
    "AAVE/USDT", "GRT/USDT", "PEPE/USDT", "QNT/USDT", "FET/USDT"
]

SEPARATOR = " • • • • • • • • • • • • • • • • • • • • • • • • • • • • "

# ─── إعدادات TP و SL ─────────────────────────────────────────
TP1_PERCENT = 0.009    # الهدف الأول ثابت 0.9%
MAX_SL_PERCENT = 0.03  # وقف الخسارة الأقصى 3%


def get_decimals(price):
    if price > 100:
        return 2
    elif price > 1:
        return 3
    elif price > 0.01:
        return 5
    else:
        return 8


def get_quality_label(score):
    if score >= 85:
        return "PREMIUM", "\U0001f7e2"
    elif score >= 70:
        return "STRONG", "\U0001f7e1"
    elif score >= 55:
        return "MODERATE", "\U0001f7e0"
    else:
        return "BASIC", "\u26aa"


def calculate_quality_score(
    ema_cross: bool,
    macd_conf: bool,
    volume_conf: bool,
    rsi_conf: bool,
    trend_4h_aligned: bool,
) -> int:
    """حساب درجة جودة الإشارة من 100
    • تقاطع EMA          → 25 نقطة
    • تأكيد MACD         → 20 نقطة
    • تأكيد الحجم        → 20 نقطة
    • RSI في نطاق صحي    → 15 نقطة
    • توافق 4H           → 20 نقطة
    """
    score = 0
    if ema_cross:
        score += 25
    if macd_conf:
        score += 20
    if volume_conf:
        score += 20
    if rsi_conf:
        score += 15
    if trend_4h_aligned:
        score += 20
    return score


def send_crypto_signal(coin_name, direction, quality_score, entry, tp1, tp2, tp3, tp4, sl, rr_ratio):
    """إرسال إشارة بصيغتها الجديدة"""

    coin_display = "$" + coin_name.replace("/", "")
    quality_label, quality_emoji = get_quality_label(quality_score)
    quality_text = f"{quality_emoji} {quality_label} ({quality_score}/100)"
    sep = SEPARATOR

    text = f"""NEW SIGNAL\U0001f4a1

COIN: {coin_display}
Direction: {direction.upper()}
Quality: {quality_text}
R:R: {rr_ratio}:1
Entry: {entry}
{sep}
Target 1: {tp1}\u2611\ufe0f
Target 2: {tp2}\u2611\ufe0f
Target 3: {tp3}\u2611\ufe0f
Target 4: {tp4}\u2611\ufe0f

\U0001f6ab Stop Loss: {sl}

LEVERAGE: 12x 
{sep}
Crypto Hunter\u00a9

L E A K E D B Y: @BULLS_SIGNALS"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.json().get("ok"):
            print(f"\u2705 Signal sent for {coin_name} | Quality: {quality_score}/100 | R:R {rr_ratio}:1")
        else:
            print(f"TELEGRAM ERROR for {coin_name}: {response.json().get('description')}")
    except Exception as e:
        print(f"Network error: {e}")


def check_4h_trend(exchange, symbol, direction):
    """ترشيح الاتجاه العام على إطار 4 ساعات
    صاعد  → السعر فوق EMA50 و EMA50 فوق EMA200
    هابط  → السعر تحت EMA50 و EMA50 تحت EMA200
    """
    try:
        ohlcv_4h = exchange.fetch_ohlcv(symbol, "4h", limit=100)
        df_4h = pd.DataFrame(
            ohlcv_4h, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

        df_4h["ema_50"] = df_4h["close"].ewm(span=50, adjust=False).mean()
        df_4h["ema_200"] = df_4h["close"].ewm(span=200, adjust=False).mean()

        price = df_4h["close"].iloc[-1]
        ema50 = df_4h["ema_50"].iloc[-1]
        ema200 = df_4h["ema_200"].iloc[-1]

        if direction == "LONG":
            return price > ema50 and ema50 > ema200
        else:
            return price < ema50 and ema50 < ema200

    except Exception as e:
        print(f"4H trend check error for {symbol}: {e}")
        return False


def analyze_and_trade():
    print("Starting ADVANCED scan (15m) with EMA + MACD + Vol + RSI + 4H Trend Filter...")
    exchange = ccxt.mexc({"enableRateLimit": True, "timeout": 30000})

    for symbol in SYMBOLS:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )

            # ── EMA 9 / 21 ─────────────────────────────────
            df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
            df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()

            curr_ema9 = df["ema_9"].iloc[-1]
            curr_ema21 = df["ema_21"].iloc[-1]
            prev_ema9 = df["ema_9"].iloc[-2]
            prev_ema21 = df["ema_21"].iloc[-2]

            ema_buy = (prev_ema9 < prev_ema21) and (curr_ema9 > curr_ema21)
            ema_sell = (prev_ema9 > prev_ema21) and (curr_ema9 < curr_ema21)

            # ── Volume (SMA 20) ────────────────────────────
            df["vol_sma"] = df["volume"].rolling(window=20).mean()
            current_vol = df["volume"].iloc[-1]
            avg_vol = df["vol_sma"].iloc[-1]
            volume_confirm = current_vol > (avg_vol * 1.2)

            # ── RSI (14) ───────────────────────────────────
            df["rsi"] = ta.momentum.rsi(df["close"], window=14)
            current_rsi = df["rsi"].iloc[-1]
            rsi_safe_long = 30 < current_rsi < 75
            rsi_safe_short = 25 < current_rsi < 70

            # ── MACD Histogram ────────────────────────────
            macd_hist = ta.trend.macd_diff(df["close"])
            curr_macd = macd_hist.iloc[-1]
            prev_macd = macd_hist.iloc[-2]

            macd_buy = (curr_macd > 0) and (curr_macd > prev_macd)
            macd_sell = (curr_macd < 0) and (curr_macd < prev_macd)

            # ── ATR ───────────────────────────────────────
            df["atr"] = ta.volatility.average_true_range(
                df["high"], df["low"], df["close"], window=14
            )
            atr_value = df["atr"].iloc[-1]

            current_close = df["close"].iloc[-1]
            decimals = get_decimals(current_close)

            # ─────────────────────────────────────────────────
            #  LONG
            # ─────────────────────────────────────────────────
            if (ema_buy or macd_buy) and volume_confirm:

                trend_ok = check_4h_trend(exchange, symbol, "LONG")
                if not trend_ok:
                    print(f"\u26a0\ufe0f {symbol} BUY skipped \u2014 4H trend NOT bullish")
                    continue

                if not rsi_safe_long:
                    print(f"\u26a0\ufe0f {symbol} BUY skipped \u2014 RSI {current_rsi:.1f} not safe")
                    continue

                score = calculate_quality_score(
                    ema_cross=ema_buy,
                    macd_conf=macd_buy,
                    volume_confirm=volume_confirm,
                    rsi_conf=True,
                    trend_4h_aligned=True,
                )

                entry = round(current_close, decimals)

                # SL: الأصغر بين (ATR×2) و (3% من السعر)
                atr_sl_distance = atr_value * 2.0
                max_sl_distance = current_close * MAX_SL_PERCENT
                sl_distance = min(atr_sl_distance, max_sl_distance)
                sl = round(current_close - sl_distance, decimals)
                risk = entry - sl

                # TP1 ثابت 0.9% | باقي الأهداف ديناميكية
                tp1 = round(entry * (1 + TP1_PERCENT), decimals)
                tp2 = round(entry + (risk * 2.5), decimals)
                tp3 = round(entry + (risk * 4.0), decimals)
                tp4 = round(entry + (risk * 5.5), decimals)

                reward = tp4 - entry
                rr = round(reward / risk, 1) if risk > 0 else 0

                send_crypto_signal(
                    symbol, "LONG", score, str(entry),
                    str(tp1), str(tp2), str(tp3), str(tp4), str(sl), rr
                )
                time.sleep(2)

            # ─────────────────────────────────────────────────
            #  SHORT
            # ─────────────────────────────────────────────────
            elif (ema_sell or macd_sell) and volume_confirm:

                trend_ok = check_4h_trend(exchange, symbol, "SHORT")
                if not trend_ok:
                    print(f"\u26a0\ufe0f {symbol} SELL skipped \u2014 4H trend NOT bearish")
                    continue

                if not rsi_safe_short:
                    print(f"\u26a0\ufe0f {symbol} SELL skipped \u2014 RSI {current_rsi:.1f} not safe")
                    continue

                score = calculate_quality_score(
                    ema_cross=ema_sell,
                    macd_conf=macd_sell,
                    volume_confirm=volume_confirm,
                    rsi_conf=True,
                    trend_4h_aligned=True,
                )

                entry = round(current_close, decimals)

                # SL: الأصغر بين (ATR×2) و (3% من السعر)
                atr_sl_distance = atr_value * 2.0
                max_sl_distance = current_close * MAX_SL_PERCENT
                sl_distance = min(atr_sl_distance, max_sl_distance)
                sl = round(current_close + sl_distance, decimals)
                risk = sl - entry

                # TP1 ثابت 0.9% | باقي الأهداف ديناميكية
                tp1 = round(entry * (1 - TP1_PERCENT), decimals)
                tp2 = round(entry - (risk * 2.5), decimals)
                tp3 = round(entry - (risk * 4.0), decimals)
                tp4 = round(entry - (risk * 5.5), decimals)

                reward = entry - tp4
                rr = round(reward / risk, 1) if risk > 0 else 0

                send_crypto_signal(
                    symbol, "SHORT", score, str(entry),
                    str(tp1), str(tp2), str(tp3), str(tp4), str(sl), rr
                )
                time.sleep(2)

        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")


if __name__ == "__main__":
    print("Bot started successfully on GitHub Actions...")
    analyze_and_trade()
    print("Scan finished. Waiting for next GitHub trigger...")
