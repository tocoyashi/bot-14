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

# قائمة بيضاء بأزواج Futures الموثوقة
WHITELIST = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "LINK/USDT",
    "TRX/USDT", "LTC/USDT", "UNI/USDT", "ATOM/USDT", "XLM/USDT",
    "NEAR/USDT", "APT/USDT", "SUI/USDT", "ARB/USDT", "OP/USDT",
    "INJ/USDT", "FIL/USDT", "AAVE/USDT", "QNT/USDT", "FET/USDT",
    "RENDER/USDT", "TIA/USDT", "SEI/USDT", "PYTH/USDT", "STRK/USDT"
]

def get_top_25_symbols(exchange):
    """جلب أفضل 25 زوجاً من القائمة البيضاء حسب حجم التداول على MEXC"""
    try:
        tickers = exchange.fetch_tickers()
        valid_pairs = []
        
        for symbol, ticker in tickers.items():
            if symbol in WHITELIST:
                volume = ticker.get('quoteVolume', 0) or ticker.get('baseVolume', 0)
                if volume and volume > 0:
                    valid_pairs.append((symbol, volume))
        
        valid_pairs.sort(key=lambda x: x[1], reverse=True)
        return [pair[0] for pair in valid_pairs[:25]]
        
    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return WHITELIST[:25]

def get_decimals(price):
    if price > 100:
        return 2
    elif price > 1:
        return 3
    elif price > 0.01:
        return 5
    else:
        return 8

def format_price(price, decimals):
    """التأكد من استخدام النقطة كفاصل عشري"""
    return str(round(price, decimals))

def send_signal(coin_name, direction, entry, tp1, tp2, tp3, sl):
    """إرسال إشارة واحدة بتنسيق موحد"""
    direction_text = "Long" if direction.lower() == "long" else "Short"
    
    text = f"""📝 NEW SIGNAL

Pair: {coin_name}
Signal Type: Regular ({direction_text})
Leverage: 10x Cross
Exchanges:
Binance Futures, ByBit USDT

Entry  : {entry} 

Take Profit :
TP1: {tp1}
TP2: {tp2}
TP3: {tp3}

 Stop loss: {sl}

 • • • • • • • • • • • • • • • • • • • • •
Crypto Hunter©

L E A K E D B Y: @BULLS_SIGNALS"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": text}
    
    try:
        response = requests.post(url, json=payload)
        if response.json().get('ok'):
            print(f"✅ Signal sent for {coin_name}")
            return True
        else:
            print(f"❌ Telegram error: {response.json().get('description')}")
            return False
    except Exception as e:
        print(f"Network error: {e}")
        return False

def analyze_and_trade():
    print("Starting scan (15m)...")
    exchange = ccxt.mexc()
    
    SYMBOLS = get_top_25_symbols(exchange)
    if not SYMBOLS:
        print("No symbols found. Exiting.")
        return
    
    print(f"Scanning {len(SYMBOLS)} pairs: {SYMBOLS}")
    
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
            
            # حساب الأسعار للصفقات الطويلة (LONG/BUY)
            if (ema_buy or macd_buy) and volume_confirm and rsi_not_overbought:
                print(f"🟢 BUY candidate: {symbol} @ {current_close} | RSI: {current_rsi:.1f}")
                
                entry = round(current_close, decimals)
                tp1 = round(entry * 1.009, decimals)
                tp2 = round(entry * 1.028, decimals)
                tp3 = round(entry * 1.048, decimals)
                sl = round(entry * (1 - 0.0325), decimals)
                
                # فحص صحة الأسعار قبل الإرسال
                if tp1 <= current_close:
                    print(f"⚠️ Skipping {symbol}: TP1 ({tp1}) <= current price ({current_close})")
                    continue
                if sl >= current_close:
                    print(f"⚠️ Skipping {symbol}: SL ({sl}) >= current price ({current_close})")
                    continue
                
                s_entry = format_price(entry, decimals)
                s_tp1 = format_price(tp1, decimals)
                s_tp2 = format_price(tp2, decimals)
                s_tp3 = format_price(tp3, decimals)
                s_sl = format_price(sl, decimals)
                
                send_signal(symbol, "long", s_entry, s_tp1, s_tp2, s_tp3, s_sl)
                time.sleep(2)
                
            # حساب الأسعار للصفقات القصيرة (SHORT/SELL)
            elif (ema_sell or macd_sell) and volume_confirm and rsi_not_oversold:
                print(f"🔴 SELL candidate: {symbol} @ {current_close} | RSI: {current_rsi:.1f}")
                
                entry = round(current_close, decimals)
                tp1 = round(entry * 0.991, decimals)
                tp2 = round(entry * 0.972, decimals)
                tp3 = round(entry * 0.952, decimals)
                sl = round(entry * (1 + 0.0325), decimals)
                
                # فحص صحة الأسعار قبل الإرسال
                if tp1 >= current_close:
                    print(f"⚠️ Skipping {symbol}: TP1 ({tp1}) >= current price ({current_close})")
                    continue
                if sl <= current_close:
                    print(f"⚠️ Skipping {symbol}: SL ({sl}) <= current price ({current_close})")
                    continue
                
                s_entry = format_price(entry, decimals)
                s_tp1 = format_price(tp1, decimals)
                s_tp2 = format_price(tp2, decimals)
                s_tp3 = format_price(tp3, decimals)
                s_sl = format_price(sl, decimals)
                
                send_signal(symbol, "short", s_entry, s_tp1, s_tp2, s_tp3, s_sl)
                time.sleep(2)
                
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

if __name__ == "__main__":
    print("Bot started...")
    analyze_and_trade()
    print("Scan finished.")
