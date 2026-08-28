#!/usr/bin/env python3
"""
MEXC Trading Signal Bot — Ultra Precision Edition
Fixed: Dynamic SL | Corrected Structure | Spread Filter | Wick Filter | Signal Tracking
"""

import os
import json
import asyncio
import logging
from datetime import datetime, time as dt_time
from pathlib import Path
from collections import Counter

import ccxt
import pandas as pd
import numpy as np
from telegram import Bot

# ================= Configuration =================
BOT_TOKEN = os.environ.get('BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')

TIMEFRAME = '15m'
HTF_TIMEFRAME = '4h'           # فريم واحد للاتجاه الكبير
TOP_N_COINS = 25
LEVERAGE = 12

# Targets
TP1_PERC = 0.85
TP2_PERC = 1.98
TP3_PERC = 3.50
TP4_PERC = 5.50

# ⚡ SL ديناميكي بناءً على ATR
ATR_SL_MULTIPLIER = 2.5
MIN_SL_PERC = 1.5
MAX_SL_PERC = 3.5

# Filters
TREND_FILTER = True
FILTER_MOMENTUM_STRENGTH = True
FILTER_ATR_MINIMUM = True
ATR_MIN_PERCENT = 0.15
RSI_FILTER = True
RSI_PERIOD = 14
RSI_LONG_MAX = 70
RSI_SHORT_MIN = 30
VOLUME_FILTER = True
VOL_MIN_RATIO = 1.0
ADX_FILTER = True
ADX_PERIOD = 14
ADX_MIN = 18
ALLOW_MOMENTUM_BREAK = True
MOM_BREAK_THRESHOLD = 1.0

HTF_FILTER = True
HTF_MAX_DEVIATION = 2.5
CONFIRMATION_CANDLE = True
CONFIRM_MAX_OPPOSITE = 0.6
NEWS_TIME_FILTER = True

# NEW: Spread Filter
SPREAD_FILTER = True
MAX_SPREAD_PCT = 0.15          # 0.15% سقف السبريد

# NEW: Wick Filter — يتجنب الشموع بظل طويل عكسي
WICK_FILTER = True
MAX_WICK_RATIO = 2.0           # الظل العكسي يجب ألا يتجاوز 2x جسم الشمعة

# Structure
STRUCTURE_FILTER = True
STRUCTURE_LOOKBACK = 20

# Cooldown
COOLDOWN_FILE = Path('cooldown.json')
COOLDOWN_HOURS = 4

# Signal tracking
SIGNALS_LOG = Path('signals_log.json')

STABLECOINS = ['USDC/USDT', 'TUSD/USDT', 'DAI/USDT', 'FDUSD/USDT', 'USDP/USDT', 'PYUSD/USDT']
BLACKLIST = ['USD1/USDT', 'USDE/USDT', 'ISEK/USDT', 'MBG/USDT', 'AIX/USDT',
             'XPLK/USDT', '9BIT/USDT', 'CYS/USDT', 'USDGOUSDT', 'GOLD/USDT']

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler("logs/signal_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ================= Helpers =================

def _fmt(price):
    if price >= 1000:   return f"{price:,.2f}"
    elif price >= 1:    return f"{price:,.4f}"
    else:              return f"{price:,.6f}"


def is_high_impact_time():
    if not NEWS_TIME_FILTER:
        return False
    now = datetime.utcnow()
    weekday = now.weekday()
    t = now.time()
    if weekday == 4 and dt_time(12, 0) <= t <= dt_time(13, 45):
        return True
    if weekday == 2 and dt_time(18, 0) <= t <= dt_time(19, 45):
        return True
    if weekday in (1, 2) and dt_time(12, 30) <= t <= dt_time(13, 45):
        return True
    return False


def calculate_adx(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, min_periods=period).mean()
    return adx


def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    return 100 - (100 / (1 + avg_gain / avg_loss))


# FIXED: direction parameter is used correctly
def find_nearest_structure(df, direction, lookback=20):
    """Find nearest swing high (for SHORT) or swing low (for LONG)."""
    recent = df.tail(lookback)
    if direction == "LONG":
        return recent['low'].min()
    else:
        return recent['high'].max()


def build_signal_message(symbol, direction, entry_price, sl_price, confidence_score, rr):
    pair = symbol.replace('/', '')
    if direction == "LONG":
        tp1 = entry_price * (1 + TP1_PERC / 100)
        tp2 = entry_price * (1 + TP2_PERC / 100)
        tp3 = entry_price * (1 + TP3_PERC / 100)
        tp4 = entry_price * (1 + TP4_PERC / 100)
    else:
        tp1 = entry_price * (1 - TP1_PERC / 100)
        tp2 = entry_price * (1 - TP2_PERC / 100)
        tp3 = entry_price * (1 - TP3_PERC / 100)
        tp4 = entry_price * (1 - TP4_PERC / 100)

    if confidence_score >= 85:
        quality = "🟢 PREMIUM"
    elif confidence_score >= 70:
        quality = "🟡 STANDARD"
    else:
        quality = "🟠 BASIC"

    return f"""NEW SIGNAL💡

COIN: ${pair}
Direction: {direction}
Quality: {quality} ({confidence_score}/100)
R:R: {rr}:1
Entry: {_fmt(entry_price)}
 • • • • • • • • • • • • • • • • • • • • • • • • • • • •
Target 1: {_fmt(tp1)}☑️
Target 2: {_fmt(tp2)}☑️
Target 3: {_fmt(tp3)}☑️
Target 4: {_fmt(tp4)}☑️

🚫 Stop Loss: {_fmt(sl_price)}

LEVERAGE: {LEVERAGE}x 
 • • • • • • • • • • • • • • • • • • • • • • • • • • • •
Crypto Hunter©

L E A K E D B Y: @BULLS_SIGNALS"""


def _fast_linreg_endpoint(series, window=20):
    vals = series.values.astype(float)
    n = len(vals)
    result = np.full(n, np.nan)
    if n < window:
        return pd.Series(result, index=series.index)
    y = np.arange(window, dtype=float)
    sum_y = y.sum()
    sum_y2 = (y ** 2).sum()
    denom = window * sum_y2 - sum_y ** 2
    weighted_sum = np.convolve(vals, y[::-1], mode='valid')
    rolling_sum = np.convolve(vals, np.ones(window), mode='valid')
    slopes = (window * weighted_sum - rolling_sum * sum_y) / denom
    x_means = rolling_sum / window
    intercepts = x_means - slopes * sum_y / window
    result[window - 1:] = slopes * (window - 1) + intercepts
    return pd.Series(result, index=series.index)


# ================= Data Fetching =================

def get_mexc_data(symbol, timeframe, limit=151):
    exchange = ccxt.mexc({'enableRateLimit': True})
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df


def get_htf_ema20(symbol, tf='4h'):
    try:
        exchange = ccxt.mexc({'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=30)
        if len(ohlcv) < 20:
            return None
        df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        ema20 = df['c'].ewm(span=20, adjust=False).mean().iloc[-1]
        return ema20
    except Exception:
        return None


def get_spread(symbol):
    """Returns spread as percentage of mid price."""
    try:
        exchange = ccxt.mexc({'enableRateLimit': True})
        ticker = exchange.fetch_ticker(symbol)
        bid = ticker.get('bid', 0)
        ask = ticker.get('ask', 0)
        if bid and ask and ask > 0:
            mid = (bid + ask) / 2
            spread = (ask - bid) / mid * 100
            return spread
    except Exception:
        pass
    return 0


def get_top_mexc_coins(limit=25):
    logger.info(f"Fetching top {limit} coins from MEXC...")
    exchange = ccxt.mexc({'enableRateLimit': True})
    try:
        tickers = exchange.fetch_tickers()
        usdt_pairs = []
        for symbol, ticker in tickers.items():
            if symbol.endswith('/USDT') and symbol not in STABLECOINS and symbol not in BLACKLIST:
                vol = ticker.get('quoteVolume') or 0
                if vol > 500000:
                    usdt_pairs.append({'symbol': symbol, 'volume': vol})
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
        return [p['symbol'] for p in usdt_pairs[:limit]]
    except Exception as e:
        logger.error(f"Error fetching coins: {e}")
        return []


# ================= Cooldown & Logs =================

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
        logger.error(f"Cooldown save error: {e}")


def is_on_cooldown(symbol, cooldown_data):
    if symbol not in cooldown_data:
        return False
    try:
        last_time = datetime.fromisoformat(cooldown_data[symbol])
        return (datetime.now() - last_time).total_seconds() / 3600 < COOLDOWN_HOURS
    except Exception:
        return False


def log_signal(signal):
    """Track sent signals for performance review."""
    data = []
    if SIGNALS_LOG.exists():
        try:
            with open(SIGNALS_LOG, 'r') as f:
                data = json.load(f)
        except Exception:
            pass
    data.append({
        'timestamp': datetime.now().isoformat(),
        'symbol': signal['symbol'],
        'direction': signal['direction'],
        'entry': signal['entry'],
        'sl': signal['sl'],
        'tp1': signal['tp1'],
        'tp4': signal['tp4'],
        'confidence': signal['confidence'],
        'reason': signal['reason']
    })
    try:
        with open(SIGNALS_LOG, 'w') as f:
            json.dump(data[-500:], f, indent=2)  # Keep last 500
    except Exception as e:
        logger.error(f"Signal log error: {e}")


# ================= Signal Engine =================

class SignalEngine:
    def __init__(self, bb_length=20, bb_mult=2.0, kc_length=20, kc_mult=1.5):
        self.bb_length = bb_length
        self.bb_mult = bb_mult
        self.kc_length = kc_length
        self.kc_mult = kc_mult

    def true_range(self, high, low, close):
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    def analyze(self, df):
        data = df.copy()
        bb_basis = data['close'].rolling(window=self.bb_length).mean()
        bb_dev = self.bb_mult * data['close'].rolling(window=self.bb_length).std()
        upper_bb = bb_basis + bb_dev
        lower_bb = bb_basis - bb_dev
        kc_ma = data['close'].rolling(window=self.kc_length).mean()
        tr = self.true_range(data['high'], data['low'], data['close'])
        range_ma = tr.rolling(window=self.kc_length).mean()
        upper_kc = kc_ma + range_ma * self.kc_mult
        lower_kc = kc_ma - range_ma * self.kc_mult
        squeeze_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)

        highest_high = data['high'].rolling(window=self.kc_length).max()
        lowest_low = data['low'].rolling(window=self.kc_length).min()
        close_ma = data['close'].rolling(window=self.kc_length).mean()
        avg_val = ((highest_high + lowest_low) / 2 + close_ma) / 2
        momentum = _fast_linreg_endpoint(data['close'] - avg_val, self.kc_length)

        squeeze_groups = (squeeze_on != squeeze_on.shift()).cumsum()
        squeeze_duration = squeeze_on.groupby(squeeze_groups).cumsum()
        mom_rolling_std = momentum.rolling(window=100).std()
        mom_threshold = (mom_rolling_std * 0.5).fillna(0)
        momentum_strong = momentum.abs() > mom_threshold

        mom_break_threshold = mom_rolling_std * MOM_BREAK_THRESHOLD
        mom_break_long = (momentum > mom_break_threshold) & (momentum > momentum.shift(1))
        mom_break_short = (momentum < -mom_break_threshold) & (momentum < momentum.shift(1))

        atr = tr.rolling(window=14).mean()
        atr_pct = (atr / data['close']) * 100
        rsi = calculate_rsi(data['close'], RSI_PERIOD)
        vol_sma = data['volume'].rolling(window=20).mean()
        ema_trend = data['close'].ewm(span=50, adjust=False).mean()
        adx = calculate_adx(data, ADX_PERIOD)

        data['squeeze_on'] = squeeze_on
        data['squeeze_duration'] = squeeze_duration
        data['momentum'] = momentum
        data['momentum_increasing'] = momentum > momentum.shift(1)
        data['momentum_strong'] = momentum_strong
        data['mom_break_long'] = mom_break_long
        data['mom_break_short'] = mom_break_short
        data['atr'] = atr
        data['atr_pct'] = atr_pct
        data['rsi'] = rsi
        data['vol_sma'] = vol_sma
        data['ema_trend'] = ema_trend
        data['adx'] = adx
        return data

    def generate_signal(self, df, symbol="", htf_ema=None, structure_level=None, spread_pct=0):
        data = self.analyze(df)
        data['signal'] = 0

        squeeze_on_safe = data['squeeze_on'].fillna(False).astype(bool)
        mom_inc_safe = data['momentum_increasing'].fillna(False).astype(bool)

        if len(data) < 4:
            return None, "Not enough data", 0

        signal_candle = data.iloc[-3]
        confirm_candle = data.iloc[-2]

        # NEW: Spread Filter
        if SPREAD_FILTER and spread_pct > MAX_SPREAD_PCT:
            return None, f"Spread too high ({spread_pct:.3f}%)", 0

        # NEW: Wick Filter on signal candle
        if WICK_FILTER:
            body = abs(signal_candle['close'] - signal_candle['open'])
            if body > 0:
                if signal_candle['close'] > signal_candle['open']:  # green candle
                    upper_wick = signal_candle['high'] - signal_candle['close']
                    lower_wick = signal_candle['open'] - signal_candle['low']
                else:  # red candle
                    upper_wick = signal_candle['high'] - signal_candle['open']
                    lower_wick = signal_candle['close'] - signal_candle['low']
                # Reject if opposite wick is too long
                # (simplified: max wick vs body)
                max_wick = max(upper_wick, lower_wick)
                if max_wick / body > MAX_WICK_RATIO:
                    return None, f"Wick too long ({max_wick/body:.1f}x body)", 0

        signal_type = None
        reason = "No signal"
        confidence = 50

        # MODE A: Squeeze Release
        squeeze_release = (squeeze_on_safe.shift(1) == True) & (squeeze_on_safe == False)
        has_squeeze_release = squeeze_release.iloc[-3] if len(squeeze_release) >= 3 else False

        if has_squeeze_release:
            is_long = signal_candle['momentum'] > 0 and mom_inc_safe.iloc[-3]
            is_short = signal_candle['momentum'] < 0 and not mom_inc_safe.iloc[-3]
            if is_long or is_short:
                signal_type = 1 if is_long else -1
                reason = "Squeeze Release"
                confidence += 15

        # MODE B: Momentum Break
        elif ALLOW_MOMENTUM_BREAK:
            if signal_candle['mom_break_long'] and mom_inc_safe.iloc[-3]:
                signal_type = 1
                reason = "Momentum Break LONG"
                confidence += 10
            elif signal_candle['mom_break_short'] and not mom_inc_safe.iloc[-3]:
                signal_type = -1
                reason = "Momentum Break SHORT"
                confidence += 10
            else:
                reason = "No squeeze release + No momentum break"
        else:
            reason = "No squeeze release"

        if signal_type is None:
            return None, reason, 0

        direction = "LONG" if signal_type == 1 else "SHORT"

        # HTF Filter (4h EMA20)
        if HTF_FILTER and htf_ema is not None:
            diff_pct = (signal_candle['close'] - htf_ema) / htf_ema * 100
            if direction == "LONG" and diff_pct < -HTF_MAX_DEVIATION:
                return None, f"{reason} → HTF too bearish ({diff_pct:.1f}%)", 0
            if direction == "SHORT" and diff_pct > HTF_MAX_DEVIATION:
                return None, f"{reason} → HTF too bullish ({diff_pct:.1f}%)", 0
            if (direction == "LONG" and diff_pct > 0) or (direction == "SHORT" and diff_pct < 0):
                confidence += 5

        # Confirmation Candle
        if CONFIRMATION_CANDLE:
            if direction == "LONG":
                change = (confirm_candle['close'] - confirm_candle['open']) / confirm_candle['open'] * 100
                if change < -CONFIRM_MAX_OPPOSITE:
                    return None, f"{reason} → Confirm candle bearish ({change:.2f}%)", 0
            else:
                change = (confirm_candle['close'] - confirm_candle['open']) / confirm_candle['open'] * 100
                if change > CONFIRM_MAX_OPPOSITE:
                    return None, f"{reason} → Confirm candle bullish ({change:.2f}%)", 0

        # FIXED: Structure Filter uses correct direction
        if STRUCTURE_FILTER and structure_level is not None:
            if direction == "LONG":
                dist_to_struct = (signal_candle['close'] - structure_level) / signal_candle['close'] * 100
                if dist_to_struct < 0.5:
                    return None, f"{reason} → Too close to structure support ({dist_to_struct:.2f}%)", 0
            else:
                dist_to_struct = (structure_level - signal_candle['close']) / signal_candle['close'] * 100
                if dist_to_struct < 0.5:
                    return None, f"{reason} → Too close to structure resistance ({dist_to_struct:.2f}%)", 0

        # Original Filters
        if FILTER_MOMENTUM_STRENGTH and not signal_candle['momentum_strong']:
            return None, f"{reason} → Momentum too weak", 0
        else:
            confidence += 5

        if TREND_FILTER:
            if direction == "LONG" and signal_candle['close'] <= signal_candle['ema_trend']:
                return None, f"{reason} → Price below EMA50", 0
            if direction == "SHORT" and signal_candle['close'] >= signal_candle['ema_trend']:
                return None, f"{reason} → Price above EMA50", 0
            confidence += 5

        if FILTER_ATR_MINIMUM and signal_candle['atr_pct'] < ATR_MIN_PERCENT:
            return None, f"{reason} → ATR% {signal_candle['atr_pct']:.3f} < {ATR_MIN_PERCENT}", 0
        else:
            confidence += 5

        if RSI_FILTER:
            if direction == "LONG" and signal_candle['rsi'] > RSI_LONG_MAX:
                return None, f"{reason} → RSI {signal_candle['rsi']:.1f} > {RSI_LONG_MAX}", 0
            if direction == "SHORT" and signal_candle['rsi'] < RSI_SHORT_MIN:
                return None, f"{reason} → RSI {signal_candle['rsi']:.1f} < {RSI_SHORT_MIN}", 0
            confidence += 5

        if VOLUME_FILTER:
            vol_ratio = signal_candle['volume'] / signal_candle['vol_sma'] if signal_candle['vol_sma'] > 0 else 0
            if vol_ratio < VOL_MIN_RATIO:
                return None, f"{reason} → Volume {vol_ratio:.2f}x < {VOL_MIN_RATIO}x", 0
            confidence += 5

        if ADX_FILTER and signal_candle['adx'] < ADX_MIN:
            return None, f"{reason} → ADX {signal_candle['adx']:.1f} < {ADX_MIN}", 0
        else:
            confidence += 5

        entry = signal_candle['close']

        # ⚡ Dynamic SL based on ATR
        atr_pct = signal_candle['atr_pct']
        sl_pct = max(MIN_SL_PERC, min(MAX_SL_PERC, atr_pct * ATR_SL_MULTIPLIER))
        sl = entry * (1 - sl_pct/100) if direction == "LONG" else entry * (1 + sl_pct/100)

        # Calculate R:R
        if direction == "LONG":
            tp4 = entry * (1 + TP4_PERC / 100)
        else:
            tp4 = entry * (1 - TP4_PERC / 100)
        risk = abs(entry - sl)
        reward = abs(tp4 - entry)
        rr = round(reward / risk, 1) if risk > 0 else 0

        return {
            'symbol': symbol,
            'direction': direction,
            'entry': entry,
            'sl': sl,
            'sl_pct': round(sl_pct, 2),
            'reason': reason,
            'confidence': min(100, confidence),
            'rr': rr,
            'tp1': entry * (1 + TP1_PERC / 100) if direction == "LONG" else entry * (1 - TP1_PERC / 100),
            'tp2': entry * (1 + TP2_PERC / 100) if direction == "LONG" else entry * (1 - TP2_PERC / 100),
            'tp3': entry * (1 + TP3_PERC / 100) if direction == "LONG" else entry * (1 - TP3_PERC / 100),
            'tp4': tp4,
        }, "PASS", min(100, confidence)


# ================= Telegram =================

async def send_alert(bot, message):
    if not CHANNEL_ID:
        logger.warning("CHANNEL_ID not set!")
        return
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="HTML", disable_web_page_preview=True)
        await asyncio.sleep(1.5)
    except Exception as e:
        logger.error(f"Send error: {e}")


async def scan_and_send():
    if is_high_impact_time():
        logger.info("High-impact news time — skipping scan")
        return

    if not BOT_TOKEN or not CHANNEL_ID:
        logger.error("BOT_TOKEN and CHANNEL_ID must be set!")
        return

    logger.info("Starting ULTRA PRECISION scan...")
    bot = Bot(token=BOT_TOKEN)

    coins = get_top_mexc_coins(TOP_N_COINS)
    if not coins:
        logger.error("Could not fetch coins from MEXC.")
        return

    # Pre-fetch HTF EMAs and spreads
    logger.info("Pre-fetching HTF EMAs and spreads...")
    htf_emas = {}
    spreads = {}
    for sym in coins:
        htf_emas[sym] = get_htf_ema20(sym, HTF_TIMEFRAME)
        spreads[sym] = get_spread(sym)
        await asyncio.sleep(0.2)

    cooldown_data = load_cooldown()
    engine = SignalEngine()
    sent = 0
    rejected = {}

    for symbol in coins:
        try:
            if is_on_cooldown(symbol, cooldown_data):
                continue

            df = get_mexc_data(symbol, TIMEFRAME, limit=151)

            # Structure
            struct_level = None
            if STRUCTURE_FILTER:
                try:
                    struct_df = get_mexc_data(symbol, TIMEFRAME, limit=STRUCTURE_LOOKBACK + 5)
                    # We need direction first — will pass None and handle inside engine
                    # Actually we need a quick direction guess or skip structure
                    # Better: compute structure after knowing direction? No, engine decides.
                    # Simplified: pass both possible levels
                    struct_low = struct_df['low'].tail(STRUCTURE_LOOKBACK).min()
                    struct_high = struct_df['high'].tail(STRUCTURE_LOOKBACK).max()
                except Exception:
                    struct_low = struct_high = None
            else:
                struct_low = struct_high = None

            # First pass to get direction
            signal, reason, conf = engine.generate_signal(
                df, symbol,
                htf_ema=htf_emas.get(symbol),
                structure_level=None,
                spread_pct=spreads.get(symbol, 0)
            )

            if signal is None:
                rejected[symbol] = reason
                logger.info(f"  ❌ {symbol}: {reason}")
                continue

            # Second pass with correct structure level
            if STRUCTURE_FILTER:
                correct_struct = struct_low if signal['direction'] == "LONG" else struct_high
                signal, reason, conf = engine.generate_signal(
                    df, symbol,
                    htf_ema=htf_emas.get(symbol),
                    structure_level=correct_struct,
                    spread_pct=spreads.get(symbol, 0)
                )
                if signal is None:
                    rejected[symbol] = reason
                    logger.info(f"  ❌ {symbol}: {reason}")
                    continue

            if signal['confidence'] < 60:
                logger.info(f"  🟡 {symbol}: Confidence too low ({signal['confidence']})")
                rejected[symbol] = f"Low confidence ({signal['confidence']})"
                continue

            cooldown_data[symbol] = datetime.now().isoformat()
            sent += 1

            msg = build_signal_message(
                signal['symbol'], signal['direction'],
                signal['entry'], signal['sl'], signal['confidence'], signal['rr']
            )
            await send_alert(bot, msg)
            log_signal(signal)
            logger.info(f"  ✅ {symbol}: {signal['direction']} — {signal['reason']} (Conf: {signal['confidence']}, SL: {signal['sl_pct']}%, RR: {signal['rr']}:1)")

        except Exception as e:
            logger.warning(f"  ⚠️ {symbol}: {e}")

    save_cooldown(cooldown_data)
    logger.info(f"Done. Sent: {sent} | Rejected: {len(rejected)}")

    if sent == 0:
        summary = "🟡 No signals found.\n\nTop reasons:\n"
        for r, c in Counter(rejected.values()).most_common(3):
            summary += f"• {r}: {c}\n"
        logger.info(summary)


# ================= Main =================

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set!")
        return
    asyncio.run(scan_and_send())


if __name__ == '__main__':
    main()
