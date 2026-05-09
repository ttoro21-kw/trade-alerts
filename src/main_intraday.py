"""장중 모니터링 entry point. 매 10분, 2차/3차 신호 발생 시 즉시 알림."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")


def is_market_window():
    now = datetime.now(PT)
    if now.weekday() >= 5:
        return False, now
    market_open = now.replace(hour=6, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=13, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close, now


def main():
    force = os.environ.get("FORCE_RUN", "").lower() in ("1", "true", "yes")
    in_window, now = is_market_window()
    if not in_window and not force:
        print(f"[skip] Outside market window: {now.strftime('%Y-%m-%d %H:%M %Z')}")
        return
    if force:
        print(f"[force] Running outside normal window: {now.strftime('%Y-%m-%d %H:%M %Z')}")

    from analyzer import analyze_ticker
    from notifier import send_email, render_intraday_alert
    from state import (
        load_state, save_state, already_alerted_today,
        mark_alerted, cleanup_old_state,
    )
    from thresholds import TICKER_CONFIG

    state = load_state()
    cleanup_old_state(state)
    sent_count = 0

    for ticker in TICKER_CONFIG.keys():
        try:
            analysis = analyze_ticker(ticker)
        except Exception as e:
            print(f"[error] {ticker}: {e}")
            continue

        loss_tier = analysis.get("loss_tier")
        buy_tier = analysis.get("buy_tier")

        if loss_tier == "3rd_forced":
            sig = "3rd_forced"
            if not already_alerted_today(state, ticker, sig):
                subject, html = render_intraday_alert(analysis, sig)
                try:
                    send_email(subject, html)
                    mark_alerted(state, ticker, sig)
                    print(f"[sent] {ticker} {sig}")
                    sent_count += 1
                except Exception as e:
                    print(f"[email error] {ticker} {sig}: {e}")
        elif loss_tier == "2nd_alert":
            sig = "2nd_alert_loss"
            if not already_alerted_today(state, ticker, sig):
                if len(analysis["confirms_sell"]) >= 1:
                    subject, html = render_intraday_alert(analysis, sig)
                    try:
                        send_email(subject, html)
                        mark_alerted(state, ticker, sig)
                        print(f"[sent] {ticker} {sig}")
                        sent_count += 1
                    except Exception as e:
                        print(f"[email error] {ticker} {sig}: {e}")

        if buy_tier == "3rd_add":
            sig = "3rd_add"
            if not already_alerted_today(state, ticker, sig):
                subject, html = render_intraday_alert(analysis, sig)
                try:
                    send_email(subject, html)
                    mark_alerted(state, ticker, sig)
                    print(f"[sent] {ticker} {sig}")
                    sent_count += 1
                except Exception as e:
                    print(f"[email error] {ticker} {sig}: {e}")
        elif buy_tier == "2nd_alert":
            sig = "2nd_alert_buy"
            if not already_alerted_today(state, ticker, sig):
                if len(analysis["confirms_buy"]) >= 1:
                    subject, html = render_intraday_alert(analysis, sig)
                    try:
                        send_email(subject, html)
                        mark_alerted(state, ticker, sig)
                        print(f"[sent] {ticker} {sig}")
                        sent_count += 1
                    except Exception as e:
                        print(f"[email error] {ticker} {sig}: {e}")

    state["last_run"] = now.isoformat()
    save_state(state)
    print(f"[done] sent {sent_count} alerts at {now.strftime('%H:%M %Z')}")


if __name__ == "__main__":
    main()
