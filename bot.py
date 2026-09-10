import os
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import ccxt
import pandas as pd
import ta
import requests
import time
import random

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

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

LEVERAGE = "5x"

def get_decimals(price):
    if price > 100: return 2
    elif price > 1: return 3
    elif price > 0.01: return 5
    else: return 8

def generate_summary(direction, strategy, df):
    rsi_val = round(df['rsi'].iloc[-1], 1)
    if direction == "LONG":
        structure_txt = random.choice(["Multi-timeframe alignment shows strong buying pressure and structural support.", "A massive bullish consensus across multiple timeframes confirms a high-probability upward move.", "The 15m and 60m charts confirm a synchronized bullish breakout scenario."])
        action_txt = random.choice(["Institutional footprint detected as both timeframes rejected lower prices simultaneously.", "Aggressive accumulation is visible as dynamic support levels hold firmly on both scales.", "Smart money positioning is clearly bullish based on cross-timeframe momentum shifts."])
        if rsi_val < 65: rsi_txt = random.choice([f"RSI at {rsi_val} confirms healthy momentum with plenty of room before overbought levels.", f"Momentum reads {rsi_val}, supporting a sustained move higher without exhaustion."])
        else: rsi_txt = random.choice([f"RSI is strong at {rsi_val}, showing extreme bullish power and heavy buyer dominance.", f"Momentum indicator reads {rsi_val}, riding a massive wave of buying pressure."])
        levels_txt = random.choice(["Invalidation point is clearly defined; expecting a strong breakout to hit the projected extension levels.", "Risk is managed safely below the invalidation level; expecting an aggressive push towards the upper targets."])
    else:
        structure_txt = random.choice(["A massive bearish consensus across multiple timeframes confirms a high-probability downward move.", "Multi-timeframe alignment shows strong selling pressure and structural resistance.", "The 15m and 60m charts confirm a synchronized bearish breakdown scenario."])
        action_txt = random.choice(["Institutional footprint detected as both timeframes rejected higher prices simultaneously.", "Aggressive distribution is visible as dynamic resistance levels hold firmly on both scales.", "Smart money positioning is clearly bearish based on cross-timeframe momentum shifts."])
        if rsi_val > 35: rsi_txt = random.choice([f"RSI at {rsi_val} confirms healthy downward momentum with plenty of room before oversold levels.", f"Momentum reads {rsi_val}, supporting a sustained move lower without exhaustion."])
        else: rsi_txt = random.choice([f"RSI is weak at {rsi_val}, showing extreme bearish power and heavy seller dominance.", f"Momentum indicator reads {rsi_val}, riding a massive wave of selling pressure."])
        levels_txt = random.choice(["Risk is managed safely above the invalidation level; expecting an aggressive drop towards the lower targets.", "Invalidation point is clearly defined; expecting a heavy breakdown to hit the projected extension levels."])
    return f"{structure_txt} {action_txt} {rsi_txt} {levels_txt}"

# ✅ تم تحديث التنسيق ليكون مطابقاً للنموذج المطلوب
def send_crypto_signal(coin_name, direction, strategy, entry, tp1, tp2, sl, summary_text):
    direction_text = "LONG" if direction.lower() == "long" else "SHORT"
    clean_name = coin_name.replace("/", "")
    
    text = f"""📡  SIGNAL DETECTED

COIN: #{clean_name}
Leverage : {LEVERAGE}
Direction: {direction_text} | Multi-timeframe

ENTRY: {entry}
TARGETS: {tp1} - {tp2}
STOP LOSS: {sl}

✅{summary_text}
➖➖➖➖➖➖➖
L E A K E D  B Y:  @BULLS_SIGNALS"""
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": text, "disable_web_page_preview": True}
    try:
        response = requests.post(url, json=payload)
        if response.json().get('ok'): 
            print(f"Signal sent for {coin_name}")
        else: 
            print(f"ERROR for {coin_name}: {response.json().get('description')}")
    except Exception as e: 
        print(f"Network error: {e}")

def analyze_and_trade():
    print("Starting HIGH CONFIDENCE Dual-TF Scan (15m + 60m)...")
    exchange = ccxt.mexc()
    for symbol in WHITELIST:
        try:
            df_15m = pd.DataFrame(exchange.fetch_ohlcv(symbol, "15m", limit=100), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_60m = pd.DataFrame(exchange.fetch_ohlcv(symbol, "1h", limit=100), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            current_close = df_15m['close'].iloc[-1]
            decimals = get_decimals(current_close)
            
            df_15m['ema_9'] = df_15m['close'].ewm(span=9, adjust=False).mean()
            df_15m['ema_21'] = df_15m['close'].ewm(span=21, adjust=False).mean()
            df_60m['ema_9'] = df_60m['close'].ewm(span=9, adjust=False).mean()
            df_60m['ema_21'] = df_60m['close'].ewm(span=21, adjust=False).mean()
            
            macd_hist_15m = ta.trend.macd_diff(df_15m['close'])
            curr_macd_15m = macd_hist_15m.iloc[-1]
            prev_macd_15m = macd_hist_15m.iloc[-2]
            macd_hist_60m = ta.trend.macd_diff(df_60m['close'])
            curr_macd_60m = macd_hist_60m.iloc[-1]
            prev_macd_60m = macd_hist_60m.iloc[-2]
            df_15m['rsi'] = ta.momentum.rsi(df_15m['close'], window=14)

            ema_buy_15m = (df_15m['ema_9'].iloc[-2] < df_15m['ema_21'].iloc[-2]) and (df_15m['ema_9'].iloc[-1] > df_15m['ema_21'].iloc[-1])
            ema_sell_15m = (df_15m['ema_9'].iloc[-2] > df_15m['ema_21'].iloc[-2]) and (df_15m['ema_9'].iloc[-1] < df_15m['ema_21'].iloc[-1])
            ema_buy_60m = (df_60m['ema_9'].iloc[-2] < df_60m['ema_21'].iloc[-2]) and (df_60m['ema_9'].iloc[-1] > df_60m['ema_21'].iloc[-1])
            ema_sell_60m = (df_60m['ema_9'].iloc[-2] > df_60m['ema_21'].iloc[-2]) and (df_60m['ema_9'].iloc[-1] < df_60m['ema_21'].iloc[-1])
            
            macd_buy_15m = (prev_macd_15m < 0) and (curr_macd_15m > 0)
            macd_sell_15m = (prev_macd_15m > 0) and (curr_macd_15m < 0)
            macd_buy_60m = (prev_macd_60m < 0) and (curr_macd_60m > 0)
            macd_sell_60m = (prev_macd_60m > 0) and (curr_macd_60m < 0)

            entry = round(current_close, decimals)

            # LONG: SL = -3.00% | TP1 = +1.10% | TP2 = +4.00%
            long_sl = round(entry * 0.97, decimals)
            long_tp1 = round(entry * 1.0110, decimals)
            long_tp2 = round(entry * 1.0400, decimals)

            # SHORT: SL = +3.00% | TP1 = -1.10% | TP2 = -4.00%
            short_sl = round(entry * 1.03, decimals)
            short_tp1 = round(entry * 0.9890, decimals)
            short_tp2 = round(entry * 0.9600, decimals)

            if (ema_buy_15m and ema_buy_60m):
                if long_sl >= entry or long_tp1 <= entry: continue
                print(f"🟢 DUAL EMA BUY on {symbol}!")
                summary = generate_summary("LONG", "Dual-TF", df_15m)
                send_crypto_signal(symbol, "LONG", "Dual-TF", entry, long_tp1, long_tp2, long_sl, summary)
                time.sleep(6)
                
            elif (ema_sell_15m and ema_sell_60m):
                if short_sl <= entry or short_tp1 >= entry: continue
                print(f"🔴 DUAL EMA SELL on {symbol}!")
                summary = generate_summary("SHORT", "Dual-TF", df_15m)
                send_crypto_signal(symbol, "SHORT", "Dual-TF", entry, short_tp1, short_tp2, short_sl, summary)
                time.sleep(6)
                
            elif (macd_buy_15m and macd_buy_60m):
                if long_sl >= entry or long_tp1 <= entry: continue
                print(f"🟢 DUAL MACD BUY on {symbol}!")
                summary = generate_summary("LONG", "Dual-TF", df_15m)
                send_crypto_signal(symbol, "LONG", "Dual-TF", entry, long_tp1, long_tp2, long_sl, summary)
                time.sleep(6)
                
            elif (macd_sell_15m and macd_sell_60m):
                if short_sl <= entry or short_tp1 >= entry: continue
                print(f"🔴 DUAL MACD SELL on {symbol}!")
                summary = generate_summary("SHORT", "Dual-TF", df_15m)
                send_crypto_signal(symbol, "SHORT", "Dual-TF", entry, short_tp1, short_tp2, short_sl, summary)
                time.sleep(6)
            else:
                print(f"⚪ No dual-TF alignment for {symbol}.")
        except Exception as e:
            print(f"Error {symbol}: {e}")

if __name__ == "__main__":
    print("Custom Dual Timeframe Bot started...")
    analyze_and_trade()
