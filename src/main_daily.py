"""일일 리포트 entry point — 3회/일 (PT 8 AM, 11 AM, 1:30 PM)."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")


def is_daily_window():
    """3개의 windows 중 하나에 진입했는지 확인. 진입 시 (True, label, now) 반환."""
    now = datetime.now(PT)
    if now.weekday() >= 5:
        return False, None, now

    now_min = now.hour * 60 + now.minute
    # 각 window는 target time ± 7분
    windows = [
        (8 * 60, "08:00 PT 장초반 리포트"),
        (11 * 60, "11:00 PT 장중후반 리포트"),
        (13 * 60 + 30, "13:30 PT 장후 리포트"),
    ]
    for target_min, label in windows:
        if abs(now_min - target_min) <= 7:
            return True, label, now
    return False, None, now


def main():
    force = os.environ.get("FORCE_RUN", "").lower() in ("1", "true", "yes")
    in_window, label, now = is_daily_window()

    if not in_window and not force:
        print(f"[skip] Not in any daily window: {now.strftime('%Y-%m-%d %H:%M %Z')}")
        return
    if force:
        label = label or "강제 실행 (force_run)"
        print(f"[force] Running outside normal window: {now.strftime('%Y-%m-%d %H:%M %Z')}")
    else:
        print(f"[run] {label}: {now.strftime('%Y-%m-%d %H:%M %Z')}")

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
        subject, html = render_daily_report(analyses, status_changes, window_label=label)
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
