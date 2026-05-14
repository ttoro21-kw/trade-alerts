"""Core analysis: 추세 분류 + signal tier computation.

시나리오 C: 두 lookback 저점 모두 계산. 단계는 40일 기준.
ADX 7일 변화 추적 추가.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Tuple

import pandas as pd
import numpy as np
import yfinance as yf

from thresholds import (
    TICKER_CONFIG,
    PEAK_TROUGH_LOOKBACK_DAYS,
    TROUGH_INFO_LOOKBACK_DAYS,
    TREND_LOOKBACK_DAYS,
    EMA_SMOOTHING_DAYS,
    VOLUME_SURGE_THRESHOLD,
    ADX_TREND_THRESHOLD,
    LATE_ENTRY_MULTIPLIER,
    LATE_EXIT_MULTIPLIER,
    SUPPRESS_BUY_ON_TRENDS,
    SUPPRESS_SELL_ON_TRENDS,
)

PT = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")

ADX_CHANGE_LOOKBACK_DAYS = 7  # ADX 변화량 측정 기간


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

    # ADX 7일 전 값
    adx_7d_ago = None
    if len(adx.dropna()) > ADX_CHANGE_LOOKBACK_DAYS:
        val = adx.iloc[-(ADX_CHANGE_LOOKBACK_DAYS + 1)]
        if not pd.isna(val):
            adx_7d_ago = float(val)
    adx_change_7d = (adx_now - adx_7d_ago) if adx_7d_ago is not None else None

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
        "adx_7d_ago": adx_7d_ago,
        "adx_change_7d": adx_change_7d,
        "plus_di": plus_di_now,
        "minus_di": minus_di_now,
        "band_pct": float(band_pct),
    }


def compute_peak_trough(df: pd.DataFrame) -> Dict:
    """40일 윈도우 (메인) + 20일 윈도우 (정보용) 모두 계산."""
    close = df['Close']

    peak_window_40 = close.tail(PEAK_TROUGH_LOOKBACK_DAYS)
    trough_window_20 = close.tail(TROUGH_INFO_LOOKBACK_DAYS)

    return {
        "peak_40d": float(peak_window_40.max()),
        "peak_40d_date": str(peak_window_40.idxmax().date()),
        "trough_40d": float(peak_window_40.min()),
        "trough_40d_date": str(peak_window_40.idxmin().date()),
        "trough_20d": float(trough_window_20.min()),
        "trough_20d_date": str(trough_window_20.idxmin().date()),
    }


def compute_signals(df: pd.DataFrame, ticker: str, trend: Dict) -> Dict:
    cfg = TICKER_CONFIG[ticker]
    close = df['Close']

    last_close = float(close.iloc[-1])
    last_close_date = str(close.index[-1].date())

    pt = compute_peak_trough(df)
    peak = pt["peak_40d"]
    trough_40d = pt["trough_40d"]
    trough_20d = pt["trough_20d"]

    dist_from_peak_pct = (last_close - peak) / peak * 100
    dist_from_trough_40d_pct = (last_close - trough_40d) / trough_40d * 100
    dist_from_trough_20d_pct = (last_close - trough_20d) / trough_20d * 100

    vol_5d_avg = df['Volume'].tail(5).mean()
    vol_20d_avg = df['Volume'].tail(20).mean()
    vol_ratio = float(vol_5d_avg / vol_20d_avg) if vol_20d_avg > 0 else 1.0

    ema5 = float(close.ewm(span=5, adjust=False).mean().iloc[-1])
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema5_above_20 = ema5 > ema20

    _, plus_di, minus_di = compute_adx(df)
    plus_di_now = float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else 0.0
    minus_di_now = float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else 0.0

    # 매수 단계 결정 — 40일 저점 기준
    tb = cfg["trailing_buy"]
    trend_status = trend.get("status", "")

    late_entry = (
        dist_from_trough_40d_pct > tb["add_pct"] * LATE_ENTRY_MULTIPLIER
        or trend_status in SUPPRESS_BUY_ON_TRENDS
    )

    buy_tier = None
    if late_entry:
        buy_tier = "late_entry"
    elif dist_from_trough_40d_pct >= tb["add_pct"]:
        buy_tier = "3rd_add"
    elif dist_from_trough_40d_pct >= tb["alert_pct"]:
        buy_tier = "2nd_alert"
    elif dist_from_trough_40d_pct >= tb["watch_pct"]:
        buy_tier = "1st_watch"

    # 손절 단계 결정 — 40일 고점 기준
    ts = cfg["trailing_stop"]
    late_exit = (
        dist_from_peak_pct < ts["forced_pct"] * LATE_EXIT_MULTIPLIER
        or trend_status in SUPPRESS_SELL_ON_TRENDS
    )

    loss_tier = None
    if late_exit:
        loss_tier = "late_exit"
    elif dist_from_peak_pct <= ts["forced_pct"]:
        loss_tier = "3rd_forced"
    elif dist_from_peak_pct <= ts["alert_pct"]:
        loss_tier = "2nd_alert"
    elif dist_from_peak_pct <= ts["watch_pct"]:
        loss_tier = "1st_watch"

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
        "peak_date": pt["peak_40d_date"],
        "trough": trough_40d,
        "trough_date": pt["trough_40d_date"],
        "trough_40d": trough_40d,
        "trough_40d_date": pt["trough_40d_date"],
        "trough_20d": trough_20d,
        "trough_20d_date": pt["trough_20d_date"],
        "dist_from_peak_pct": dist_from_peak_pct,
        "dist_from_trough_pct": dist_from_trough_40d_pct,
        "dist_from_trough_40d_pct": dist_from_trough_40d_pct,
        "dist_from_trough_20d_pct": dist_from_trough_20d_pct,
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
            "buy_watch": trough_40d * (1 + tb["watch_pct"]/100),
            "buy_alert": trough_40d * (1 + tb["alert_pct"]/100),
            "buy_add": trough_40d * (1 + tb["add_pct"]/100),
        },
    }


def analyze_ticker(ticker: str) -> Dict:
    df = fetch_data(ticker)
    trend = classify_trend(df, ticker)
    signals = compute_signals(df, ticker, trend)
    signals["trend"] = trend

    last_dt = df.index[-1].to_pydatetime()
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=ET)
    now_pt = datetime.now(PT)
    expected_date = now_pt.date()
    while expected_date.weekday() >= 5:
        expected_date -= timedelta(days=1)
    age_days = (expected_date - last_dt.date()).days
    signals["data_stale"] = age_days >= 1
    signals["data_age_days"] = age_days

    return signals
