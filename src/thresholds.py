"""
종목별 임계값 설정.
"""

TICKER_CONFIG = {
    "ASML": {
        "category": "large_cap",
        "ma20_slope_threshold_weekly_pct": 1.0,
        "consolidation_band_pct": 8.0,
        "trailing_stop": {
            "watch_pct": -5.0,
            "alert_pct": -8.0,
            "forced_pct": -12.0,
        },
        "trailing_buy": {
            "watch_pct": 3.0,
            "alert_pct": 5.0,
            "add_pct": 8.0,
        },
        "atr_multiplier": 2.5,
    },
    "AMAT": {
        "category": "large_cap",
        "ma20_slope_threshold_weekly_pct": 1.2,
        "consolidation_band_pct": 9.0,
        "trailing_stop": {
            "watch_pct": -6.0,
            "alert_pct": -9.0,
            "forced_pct": -13.0,
        },
        "trailing_buy": {
            "watch_pct": 4.0,
            "alert_pct": 6.0,
            "add_pct": 9.0,
        },
        "atr_multiplier": 3.0,
    },
    "LRCX": {
        "category": "large_cap",
        "ma20_slope_threshold_weekly_pct": 1.2,
        "consolidation_band_pct": 9.0,
        "trailing_stop": {
            "watch_pct": -6.0,
            "alert_pct": -9.0,
            "forced_pct": -13.0,
        },
        "trailing_buy": {
            "watch_pct": 4.0,
            "alert_pct": 6.0,
            "add_pct": 9.0,
        },
        "atr_multiplier": 3.0,
    },
    "NVDA": {
        "category": "high_vol_large_cap",
        "ma20_slope_threshold_weekly_pct": 1.5,
        "consolidation_band_pct": 11.0,
        "trailing_stop": {
            "watch_pct": -7.0,
            "alert_pct": -11.0,
            "forced_pct": -15.0,
        },
        "trailing_buy": {
            "watch_pct": 5.0,
            "alert_pct": 7.0,
            "add_pct": 11.0,
        },
        "atr_multiplier": 3.0,
    },
    "TQQQ": {
        "category": "leveraged_3x",
        "ma20_slope_threshold_weekly_pct": 2.5,
        "consolidation_band_pct": 16.0,
        "trailing_stop": {
            "watch_pct": -10.0,
            "alert_pct": -15.0,
            "forced_pct": -20.0,
        },
        "trailing_buy": {
            "watch_pct": 6.0,
            "alert_pct": 10.0,
            "add_pct": 15.0,
        },
        "atr_multiplier": 3.0,
    },
    "SOXL": {
        "category": "leveraged_3x",
        "ma20_slope_threshold_weekly_pct": 3.5,
        "consolidation_band_pct": 22.0,
        "trailing_stop": {
            "watch_pct": -15.0,
            "alert_pct": -22.0,
            "forced_pct": -30.0,
        },
        "trailing_buy": {
            "watch_pct": 8.0,
            "alert_pct": 13.0,
            "add_pct": 20.0,
        },
        "atr_multiplier": 3.0,
    },
}

# 공통 lookback 윈도우
PEAK_TROUGH_LOOKBACK_DAYS = 40   # 손절/매수 단계 결정용 (메인)
TROUGH_INFO_LOOKBACK_DAYS = 20   # 정보 표시 전용 (단기 swing 참고)
TREND_LOOKBACK_DAYS = 60
EMA_SMOOTHING_DAYS = 5

# 반전 신호 확인 필터 임계값
VOLUME_SURGE_THRESHOLD = 1.30
ADX_TREND_THRESHOLD = 20

# 시나리오 C 옵션 — 시기 늦음 표시
LATE_ENTRY_MULTIPLIER = 2.0   # 거리%가 buy_add × 2 초과 시 "진입 늦음"
LATE_EXIT_MULTIPLIER = 2.0    # 거리%가 stop_forced × 2 초과 시 "매도 늦음"
SUPPRESS_BUY_ON_TRENDS = {"rising", "weak_rising"}
SUPPRESS_SELL_ON_TRENDS = {"falling", "weak_falling"}
