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
TIMEFRAME = "15m"

def get_top_25_symbols(exchange):
    """جلب أفضل 25 زوجاً على MEXC حسب حجم التداول"""
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = []
        
        for symbol, ticker in tickers.items():
            if symbol.endswith("/USDT"):
                volume = ticker.get('quoteVolume', 0) or ticker.get('baseVolume', 0)
                if volume and volume > 0:
                    usdt_pairs.append((symbol, volume))
        
        # ترتيب تنازلي حسب الحجم واختيار أفضل 25
        usdt_pairs.sort(key=lambda x: x[1], reverse=True)
        top_25 = [pair[0] for pair in usdt_pairs[:25]]
        return top_25
        
    except Exception as e:
        print(f"Error fetching top symbols: {e}")
        return []

def get_decimals(price):
    if price > 100:
        return 2
    elif price > 1:
        return 3
    elif price > 0.01:
        return 5
    else:
        return 8

def send_crypto_signal(coin_name, direction, entry1, leverage, tp1, tp2, tp3, tp4, sl):
    text = f"""📝 NEW SIGNAL

Pair: {coin_name}
Direction: {direction.upper()}

Entry  : {entry1} 
Leverage: {leverage}x Cross

Take Profit :
TP1: {tp1}
TP2: {tp2}
TP3: {tp3}
TP4: {tp4}

 SL: {sl}

 • • • • • • • • • • • • • • • • • • • • •
Crypto Hunter©

L E A K E D B Y: @BULLS_SIGNALS"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.json().get('ok'):
            print(f"✅ Signal sent for {coin_name}")
        else:
            print(f"TELEGRAM ERROR for {coin_name}: {response.json().get('description')}")
    except Exception as e:
        print(f"Network error: {e}")

def analyze_and_trade():
    print("Starting scan (15m) with EMA + MACD + Vol + RSI...")
    exchange = ccxt.mexc()
    
    # جلب أفضل 25 عملة ديناميكياً حسب حجم التداول
    SYMBOLS = get_top_25_symbols(exchange)
    if not SYMBOLS:
        print("Could not fetch top symbols. Exiting.")
        return
    
    print(f"Top 25 pairs by volume: {SYMBOLS}")
    
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

            df['vol_sma'] = df['volume'].rolling(window=20).mean()
            current_vol = df['volume'].iloc[-1]
            avg_vol = df['vol_sma'].iloc[-1]
            volume_confirm = current_vol > (avg_vol * 1.2)

            df['rsi'] = ta.momentum.rsi(df['close'], window=14)
            current_rsi = df['rsi'].iloc[-1]
            rsi_not_overbought = current_rsi < 75
            rsi_not_oversold = current_rsi > 25

            macd_hist = ta.trend.macd_diff(df['close'])
            curr_macd = macd_hist.iloc[-1]
            prev_macd = macd_hist.iloc[-2]
            
            macd_buy = (curr_macd > 0) and (curr_macd > prev_macd)
            macd_sell = (curr_macd < 0) and (curr_macd < prev_macd)

            current_close = df['close'].iloc[-1]
            decimals = get_decimals(current_close)
            
            if (ema_buy or macd_buy) and volume_confirm and rsi_not_overbought:
                print(f"🟢 STRONG BUY on {symbol} | RSI: {current_rsi:.1f}")
                
                entry1 = round(current_close, decimals)
                
                tp1 = round(entry1 * 1.0065, decimals)
                tp2 = round(entry1 * 1.017, decimals)
                tp3 = round(entry1 * 1.032, decimals)
                tp4 = round(entry1 * 1.058, decimals)
                sl = round(entry1 * (1 - 0.0325), decimals)  # وقف الخسارة 3.25%
                
                send_crypto_signal(symbol, "LONG", str(entry1), "15", str(tp1), str(tp2), str(tp3), str(tp4), str(sl))
                time.sleep(2)
                
            elif (ema_sell or macd_sell) and volume_confirm and rsi_not_oversold:
                print(f"🔴 STRONG SELL on {symbol} | RSI: {current_rsi:.1f}")
                
                entry1 = round(current_close, decimals)
                
                tp1 = round(entry1 * 0.9935, decimals)
                tp2 = round(entry1 * 0.983, decimals)
                tp3 = round(entry1 * 0.968, decimals)
                tp4 = round(entry1 * 0.942, decimals)
                sl = round(entry1 * (1 + 0.0325), decimals)  # وقف الخسارة 3.25%
                
                send_crypto_signal(symbol, "SHORT", str(entry1), "15", str(tp1), str(tp2), str(tp3), str(tp4), str(sl))
                time.sleep(2)
                
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

if __name__ == "__main__":
    print("Bot started successfully on GitHub Actions...")
    analyze_and_trade()
    print("Scan finished. Waiting for next GitHub trigger...")
