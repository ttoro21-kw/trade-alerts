"""
Core analysis: 추세 분류 (5-state) + signal tier computation.

종가 대신 5일 EMA 사용 (single-day spike에 흔들리지 않게).
ATR/ADX/거래량/DI 등 지표를 종합하여 신호 확인.
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
    """yfinance로 OHLCV 데이터 fetch. period: 6mo면 6개월치 일봉."""
    df = yf.download(ticker, period=period, interval=interval,
                     progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (14일 default)."""
    high, low, close = df['High'], df['Low'], df['Close']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_adx(df: pd.DataFrame, period: int = 14):
    """ADX, +DI, -DI 계산."""
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
    """
    5-state 추세 분류:
      - rising (상승중)
      - falling (하강중)
      - rise_then_fall (상승후 하강중) → 추격손절 후보
      - fall_then_rise (하강후 상승중) → 추격매수 후보
      - sideways (횡보중)
    + weak_rising / weak_falling (보조)
    """
    cfg = TICKER_CONFIG[ticker]

    # 5일 EMA로 noise 제거된 종가 시리즈 사용
    close_ema = df['Close'].ewm(span=EMA_SMOOTHING_DAYS, adjust=False).mean()

    # MA20 기울기 (최근 5거래일 변화율, %/주)
    ma20 = close_ema.rolling(20).mean()
    if len(ma20.dropna()) < 6:
        return {"status": "insufficient_data"}
    ma20_slope_weekly = (ma20.iloc[-1] - ma20.iloc[-6]) / ma20.iloc[-6] * 100

    # 분할 선형회귀 — 최근 60일을 전반/후반으로 나눠 기울기 비교 (반전 판별 핵심)
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

    # ADX (추세 강도)
    adx, plus_di, minus_di = compute_adx(df)
    adx_now = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
    plus_di_now = float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else 0.0
    minus_di_now = float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else 0.0

    # 60일 high-low 밴드 (횡보 판별 보조)
    high_60d = recent.max()
    low_60d = recent.min()
    band_pct = (high_60d - low_60d) / low_60d * 100

    threshold = cfg["ma20_slope_threshold_weekly_pct"]
    consolidation_band = cfg["consolidation_band_pct"]

    # 분류 우선순위: 횡보 → 반전 → 명확한 추세 → 약한 추세
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
    """최근 PEAK_TROUGH_LOOKBACK_DAYS 거래일 동안의 5일 EMA 기준 고점/저점."""
    close_ema = df['Close'].ewm(span=EMA_SMOOTHING_DAYS, adjust=False).mean()
    recent = close_ema.tail(PEAK_TROUGH_LOOKBACK_DAYS)
    return (
        float(recent.max()),
        float(recent.min()),
        str(recent.idxmax().date()),
        str(recent.idxmin().date()),
    )


def compute_signals(df: pd.DataFrame, ticker: str) -> Dict:
    """현재 가격이 어느 신호 단계에 있는지 + 확인 필터 결과."""
    cfg = TICKER_CONFIG[ticker]
    close_ema = df['Close'].ewm(span=EMA_SMOOTHING_DAYS, adjust=False).mean()
    current_price = float(close_ema.iloc[-1])
    last_close = float(df['Close'].iloc[-1])

    peak, trough, peak_date, trough_date = compute_peak_trough(df)
    dist_from_peak_pct = (current_price - peak) / peak * 100
    dist_from_trough_pct = (current_price - trough) / trough * 100

    # 거래량 surge (최근 5일 평균 / 20일 평균)
    vol_5d_avg = df['Volume'].tail(5).mean()
    vol_20d_avg = df['Volume'].tail(20).mean()
    vol_ratio = float(vol_5d_avg / vol_20d_avg) if vol_20d_avg > 0 else 1.0

    # EMA cross
    ema5 = float(df['Close'].ewm(span=5, adjust=False).mean().iloc[-1])
    ema20 = float(df['Close'].ewm(span=20, adjust=False).mean().iloc[-1])
    ema5_above_20 = ema5 > ema20

    # ADX components
    _, plus_di, minus_di = compute_adx(df)
    plus_di_now = float(plus_di.iloc[-1]) if not pd.isna(plus_di.iloc[-1]) else 0.0
    minus_di_now = float(minus_di.iloc[-1]) if not pd.isna(minus_di.iloc[-1]) else 0.0

    # 손절 단계 결정 (고점 대비)
    ts = cfg["trailing_stop"]
    loss_tier = None
    if dist_from_peak_pct <= ts["forced_pct"]:
        loss_tier = "3rd_forced"
    elif dist_from_peak_pct <= ts["alert_pct"]:
        loss_tier = "2nd_alert"
    elif dist_from_peak_pct <= ts["watch_pct"]:
        loss_tier = "1st_watch"

    # 매수 단계 결정 (저점 대비)
    tb = cfg["trailing_buy"]
    buy_tier = None
    if dist_from_trough_pct >= tb["add_pct"]:
        buy_tier = "3rd_add"
    elif dist_from_trough_pct >= tb["alert_pct"]:
        buy_tier = "2nd_alert"
    elif dist_from_trough_pct >= tb["watch_pct"]:
        buy_tier = "1st_watch"

    # 반전 신호 확인 필터
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
        "current_price": current_price,
        "last_close": last_close,
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
    """종목 하나의 전체 분석 결과 반환 (추세 분류 + 신호 단계)."""
    df = fetch_data(ticker)
    trend = classify_trend(df, ticker)
    signals = compute_signals(df, ticker)
    signals["trend"] = trend
    return signals
