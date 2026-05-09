"""
일일 리포트 entry point — 장 마감 30분 후 (PT 1:30 PM).

전 종목 추세 상태, 신호 단계, 임계 가격을 종합한 이메일 발송.
상태 변화가 있는 경우 highlight.
"""

import sys
from datetime import datetime
from zoneinfo import ZoneInfo


PT = ZoneInfo("America/Los_Angeles")


def is_daily_window():
    """PT 1:30 PM 전후 ±7분 윈도우 평일."""
    now = datetime.now(PT)
    if now.weekday() >= 5:
        return False, now
    target_min = 13 * 60 + 30  # 1:30 PM
    now_min = now.hour * 60 + now.minute
    return abs(now_min - target_min) <= 7, now


def main():
    in_window, now = is_daily_window()
    if not in_window:
        print(f"[skip] Not in 1:30 PM PT window: {now.strftime('%Y-%m-%d %H:%M %Z')}")
        return

    from analyzer import analyze_ticker
    from notifier import send_email, render_daily_report
    from state import load_state, save_state, cleanup_old_state
    from thresholds import TICKER_CONFIG

    state = load_state()
    cleanup_old_state(state)

    analyses = []
    status_changes = {}
    last_status = state.get("last_status", {})

    for ticker in TICKER_CONFIG.keys():
        try:
            a = analyze_ticker(ticker)
            analyses.append(a)
            current_status = a["trend"].get("status")
            old_status = last_status.get(ticker)
            if old_status and old_status != current_status:
                status_changes[ticker] = {"old": old_status, "new": current_status}
            state.setdefault("last_status", {})[ticker] = current_status
        except Exception as e:
            print(f"[error] {ticker}: {e}")

    if analyses:
        subject, html = render_daily_report(analyses, status_changes)
        try:
            send_email(subject, html)
            print(f"[sent] daily report ({len(analyses)} tickers, "
                  f"{len(status_changes)} status changes)")
        except Exception as e:
            print(f"[email error] daily report: {e}")

    state["last_run"] = now.isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
