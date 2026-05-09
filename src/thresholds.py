"""
종목별 임계값 설정 (Per-ticker threshold configuration).

각 종목의 변동성 특성을 반영하여 차등 적용:
- Large-cap (ASML, AMAT, LRCX): ATR 약 2-3%, 표준 임계값
- High-vol large-cap (NVDA): ATR 약 3%, 약간 큰 임계값
- 3x leveraged ETF (TQQQ, SOXL): ATR 4-7%, 큰 buffer 필요

수정 시 해당 종목의 최근 60일 ATR(14) / Price 비율로 보정 권장.
"""

TICKER_CONFIG = {
    "ASML": {
        "category": "large_cap",
        "ma20_slope_threshold_weekly_pct": 1.0,  # ±1.0%/주 -- 추세 분류용
        "consolidation_band_pct": 8.0,           # 60일 high-low 밴드 < 8% → 횡보 후보
        "trailing_stop": {                        # 고점 대비 (음수)
            "watch_pct": -5.0,
            "alert_pct": -8.0,
            "forced_pct": -12.0,
        },
        "trailing_buy": {                         # 저점 대비 (양수)
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
PEAK_TROUGH_LOOKBACK_DAYS = 40   # 추격 stop/buy 기준점 (고점/저점)
TREND_LOOKBACK_DAYS = 60         # 추세 분류 기준 (~2개월)
EMA_SMOOTHING_DAYS = 5           # 종가 noise 제거용 5일 EMA

# 반전 신호 확인 필터 임계값
VOLUME_SURGE_THRESHOLD = 1.30    # 최근 5d 평균 거래량 / 20d 평균 > 1.3x
ADX_TREND_THRESHOLD = 20         # ADX < 20: 추세 약함, ≥ 25: 명확한 추세
