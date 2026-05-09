"""
State 관리 — 같은 신호를 하루에 두 번 보내지 않도록 dedup.

GitHub Actions는 run 간 메모리가 남지 않으므로 JSON 파일을 repo에 commit back.
"""

import json
import os
from datetime import datetime
from typing import Dict


STATE_FILE = "state/alert_state.json"


def load_state() -> Dict:
    if not os.path.exists(STATE_FILE):
        return {"last_run": None, "alerts_sent": {}, "last_status": {}}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"last_run": None, "alerts_sent": {}, "last_status": {}}


def save_state(state: Dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def already_alerted_today(state: Dict, ticker: str, signal_type: str) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    return signal_type in (
        state.get("alerts_sent", {})
             .get(today, {})
             .get(ticker, [])
    )


def mark_alerted(state: Dict, ticker: str, signal_type: str):
    today = datetime.now().strftime("%Y-%m-%d")
    alerts = state.setdefault("alerts_sent", {})
    today_dict = alerts.setdefault(today, {})
    ticker_list = today_dict.setdefault(ticker, [])
    if signal_type not in ticker_list:
        ticker_list.append(signal_type)


def cleanup_old_state(state: Dict, days_to_keep: int = 14):
    """N일 이전 alerts_sent 기록 삭제 (state 파일 비대화 방지)."""
    cutoff_ts = datetime.now().timestamp() - days_to_keep * 86400
    alerts = state.get("alerts_sent", {})
    for date_str in list(alerts.keys()):
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            if d.timestamp() < cutoff_ts:
                del alerts[date_str]
        except ValueError:
            pass
