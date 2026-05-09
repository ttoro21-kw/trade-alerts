"""Core analysis: 추세 분류 + signal tier computation.

Display 및 tier 결정은 raw 종가 기준 (사용자 brokerage 화면과 일치).
추세 분류 (rising/falling/sideways)는 5일 EMA 사용 (방향성 smoother).
Confirmation 필터에 5d/20d EMA cross 포함 → noise 제거.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from typing import Dict, Tuple

from thresholds import (
    TICKER_CONFIG,
    PEAK_TROUGH_LOOKBACK_DAYS,
    TREND_LOOKBACK_DAYS,
    EMA_SMOOTHING_DAYS,
    VOLUME_SURGE_THRESHOLD,
    ADX_TREND_THRESHOLD,
)


def fetch_data(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval=interval,
                     progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df['High'], df['Low'], df['Close']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_adx(df: pd.DataFrame, period: int = 14):
    high, low, close = df['High'], df['Low'], df['Close']
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx, plus_di, minus_di


def classify_trend(df: pd.DataFrame, ticker: str) -> Dict:
    """5-state 추세 분류. EMA 기반 — 방향 smooth하게 읽기."""
    cfg = TICKER_CONFIG[ticker]
    close_ema = df['Close'].ewm(span=EMA_SMOOTHING_DAYS, adjust=False).mean()

    ma20 = close_ema.rolling(20).mean()
    if len(ma20.dropna()) < 6:
        return {"status": "insufficient_data"}
    ma20_slope_weekly = (ma20.iloc[-1] - ma20.iloc[-6]) / ma20.iloc[-6] * 100

    recent = close_ema.tail(TREND_LOOKBACK_DAYS).dropna()
    if len(recent) < 30:
        return {"status": "insufficient_data"}

    half = len(recent) // 2
    first_half = recent.iloc[:half].values
    second_half = recent.iloc[half:].values

    slope1 = np.polyfit(np.arange(len(first_half)), first_half, 1)[0] / first_half.mean() * 100
    slope2 = np.polyfit(np.arange(len(second_half)), second_half, 1)[0] / second_half.mean() * 100
    slope1_weekly = slope1 * 5
    slope2_weekly = slope2 * 5

    adx, plus_di, minus_di = compute_adx(df)
    adx_now = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
    plus_di_now = float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else 0.0
    minus_di_now = float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else 0.0

    high_60d = recent.max()
    low_60d = recent.min()
    band_pct = (high_60d - low_60d) / low_60d * 100

    threshold = cfg["ma20_slope_threshold_weekly_pct"]
    consolidation_band = cfg["consolidation_band_pct"]

    if (abs(ma20_slope_weekly) < threshold * 0.5
            and abs(slope1_weekly) < threshold * 0.4
            and abs(slope2_weekly) < threshold * 0.4
            and adx_now < ADX_TREND_THRESHOLD
            and band_pct <= consolidation_band):
        status = "sideways"
    elif slope1_weekly > 0 and slope2_weekly < -threshold * 0.3:
        status = "rise_then_fall"
    elif slope1_weekly < 0 and slope2_weekly > threshold * 0.3:
        status = "fall_then_rise"
    elif (ma20_slope_weekly > threshold and slope1_weekly > 0
            and slope2_weekly > 0 and adx_now >= ADX_TREND_THRESHOLD):
        status = "rising"
    elif (ma20_slope_weekly < -threshold and slope1_weekly < 0
            and slope2_weekly < 0 and adx_now >= ADX_TREND_THRESHOLD):
        status = "falling"
    elif ma20_slope_weekly > threshold * 0.3:
        status = "weak_rising"
    elif ma20_slope_weekly < -threshold * 0.3:
        status = "weak_falling"
    else:
        status = "sideways"

    return {
        "status": status,
        "ma20_slope_weekly_pct": float(ma20_slope_weekly),
        "slope1_weekly_pct": float(slope1_weekly),
        "slope2_weekly_pct": float(slope2_weekly),
        "adx": adx_now,
        "plus_di": plus_di_now,
        "minus_di": minus_di_now,
        "band_pct": float(band_pct),
    }


def compute_peak_trough(df: pd.DataFrame) -> Tuple[float, float, str, str]:
    """최근 PEAK_TROUGH_LOOKBACK_DAYS 거래일 동안의 raw 종가 기준 고점/저점."""
    close = df['Close']
    recent = close.tail(PEAK_TROUGH_LOOKBACK_DAYS)
    return (
        float(recent.max()),
        float(recent.min()),
        str(recent.idxmax().date()),
        str(recent.idxmin().date()),
    )


def compute_signals(df: pd.DataFrame, ticker: str) -> Dict:
    """현재가, 거리%, 신호 단계 모두 raw 종가 기준."""
    cfg = TICKER_CONFIG[ticker]
    close = df['Close']

    last_close = float(close.iloc[-1])
    last_close_date = str(close.index[-1].date())

    peak, trough, peak_date, trough_date = compute_peak_trough(df)
    dist_from_peak_pct = (last_close - peak) / peak * 100
    dist_from_trough_pct = (last_close - trough) / trough * 100

    # 거래량 surge
    vol_5d_avg = df['Volume'].tail(5).mean()
    vol_20d_avg = df['Volume'].tail(20).mean()
    vol_ratio = float(vol_5d_avg / vol_20d_avg) if vol_20d_avg > 0 else 1.0

    # 5d EMA vs 20d EMA cross — 확인 필터
    ema5 = float(close.ewm(span=5, adjust=False).mean().iloc[-1])
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema5_above_20 = ema5 > ema20

    # ADX components
    _, plus_di, minus_di = compute_adx(df)
    plus_di_now = float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else 0.0
    minus_di_now = float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else 0.0

    # Tier 결정 — raw 종가 거리% 기준 (이메일 표시값과 일치)
    ts = cfg["trailing_stop"]
    loss_tier = None
    if dist_from_peak_pct <= ts["forced_pct"]:
        loss_tier = "3rd_forced"
    elif dist_from_peak_pct <= ts["alert_pct"]:
        loss_tier = "2nd_alert"
    elif dist_from_peak_pct <= ts["watch_pct"]:
        loss_tier = "1st_watch"

    tb = cfg["trailing_buy"]
    buy_tier = None
    if dist_from_trough_pct >= tb["add_pct"]:
        buy_tier = "3rd_add"
    elif dist_from_trough_pct >= tb["alert_pct"]:
        buy_tier = "2nd_alert"
    elif dist_from_trough_pct >= tb["watch_pct"]:
        buy_tier = "1st_watch"

    confirms_buy = []
    if vol_ratio >= VOLUME_SURGE_THRESHOLD:
        confirms_buy.append("volume_surge")
    if plus_di_now > minus_di_now:
        confirms_buy.append("plus_di_cross")
    if ema5_above_20:
        confirms_buy.append("ema5_above_20")

    confirms_sell = []
    if vol_ratio >= VOLUME_SURGE_THRESHOLD:
        confirms_sell.append("volume_surge")
    if minus_di_now > plus_di_now:
        confirms_sell.append("minus_di_cross")
    if not ema5_above_20:
        confirms_sell.append("ema5_below_20")

    return {
        "ticker": ticker,
        "current_price": last_close,
        "last_close": last_close,
        "last_close_date": last_close_date,
        "peak": peak,
        "peak_date": peak_date,
        "trough": trough,
        "trough_date": trough_date,
        "dist_from_peak_pct": dist_from_peak_pct,
        "dist_from_trough_pct": dist_from_trough_pct,
        "loss_tier": loss_tier,
        "buy_tier": buy_tier,
        "vol_ratio": vol_ratio,
        "ema5_above_20": ema5_above_20,
        "plus_di": plus_di_now,
        "minus_di": minus_di_now,
        "confirms_buy": confirms_buy,
        "confirms_sell": confirms_sell,
        "thresholds": {
            "stop_watch": peak * (1 + ts["watch_pct"]/100),
            "stop_alert": peak * (1 + ts["alert_pct"]/100),
            "stop_forced": peak * (1 + ts["forced_pct"]/100),
            "buy_watch": trough * (1 + tb["watch_pct"]/100),
            "buy_alert": trough * (1 + tb["alert_pct"]/100),
            "buy_add": trough * (1 + tb["add_pct"]/100),
        },
    }


def analyze_ticker(ticker: str) -> Dict:
    df = fetch_data(ticker)
    trend = classify_trend(df, ticker)
    signals = compute_signals(df, ticker)
    signals["trend"] = trend
    return signals
