"""
이메일 알림 (Gmail SMTP).

GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_RECIPIENT 환경변수 필요.
Gmail App Password 생성: https://myaccount.google.com/apppasswords
"""

import smtplib
import os
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Tuple


STATUS_EMOJI = {
    "rising": "📈", "falling": "📉",
    "rise_then_fall": "⚠️", "fall_then_rise": "🌱",
    "sideways": "➡️",
    "weak_rising": "↗️", "weak_falling": "↘️",
    "insufficient_data": "❓",
}

STATUS_KO = {
    "rising": "상승중", "falling": "하강중",
    "rise_then_fall": "상승후 하강중", "fall_then_rise": "하강후 상승중",
    "sideways": "횡보중",
    "weak_rising": "약상승", "weak_falling": "약하강",
    "insufficient_data": "데이터 부족",
}

LOSS_TIER_LABEL = {
    "1st_watch": "🟢 1차 관찰",
    "2nd_alert": "🟡 2차 손절",
    "3rd_forced": "🔴 3차 강제",
}
BUY_TIER_LABEL = {
    "1st_watch": "🟢 1차 관찰",
    "2nd_alert": "🟡 2차 매수",
    "3rd_add": "🔴 3차 추가",
}


def send_email(subject: str, html_body: str, plain_body: str = ""):
    """Gmail SMTP로 이메일 전송."""
    sender = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("ALERT_RECIPIENT", sender)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient

    if plain_body:
        msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender, password)
        server.send_message(msg)


def render_intraday_alert(analysis: Dict, signal_type: str) -> Tuple[str, str]:
    """장중 긴급 알림 (2차/3차 신호용)."""
    ticker = analysis["ticker"]
    price = analysis["current_price"]

    if signal_type in ("2nd_alert_loss", "3rd_forced"):
        ref_price = analysis["peak"]
        ref_date = analysis["peak_date"]
        dist = analysis["dist_from_peak_pct"]
        confirms = analysis["confirms_sell"]
        ref_label = "고점"
        if signal_type == "3rd_forced":
            title = "🔴 3차 강제 손절"
            action = "<b>즉시 손절 검토</b> — 손실폭 보호 한계 도달"
            threshold_key = "stop_forced"
        else:
            title = "🟡 2차 손절 신호"
            action = "<b>손절 검토</b> — 추세 반전 가능성"
            threshold_key = "stop_alert"
        color = "#c0392b"
    else:  # 2nd_alert_buy or 3rd_add
        ref_price = analysis["trough"]
        ref_date = analysis["trough_date"]
        dist = analysis["dist_from_trough_pct"]
        confirms = analysis["confirms_buy"]
        ref_label = "저점"
        if signal_type == "3rd_add":
            title = "🟢 3차 추가 매수"
            action = "<b>추가 분할 매수 검토</b> — 강한 반등 확인"
            threshold_key = "buy_add"
        else:
            title = "🟢 2차 매수 신호"
            action = "<b>분할 매수 검토</b> — 반등 진행"
            threshold_key = "buy_alert"
        color = "#27ae60"

    confirm_count = len(confirms)
    if confirm_count >= 2:
        strength = "🔴 강함 (필터 2+ 충족)"
    elif confirm_count == 1:
        strength = "🟡 보통 (필터 1개)"
    else:
        strength = "⚪ 약함 (필터 0)"

    confirm_str = ", ".join(confirms) if confirms else "(없음)"

    subject = f"[{ticker}] {title} — ${price:.2f} ({dist:+.1f}% from {ref_label})"

    html = f"""<html><body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif; max-width:600px;">
<div style="border-left:4px solid {color}; padding:12px 16px; background:#f9f9f9;">
  <h2 style="margin:0 0 12px 0; color:{color};">{title} — {ticker}</h2>
  <table style="border-collapse:collapse; width:100%;">
    <tr><td style="padding:5px 12px 5px 0;"><b>현재가</b></td><td>${price:.2f}</td></tr>
    <tr><td style="padding:5px 12px 5px 0;"><b>{ref_label} (40일)</b></td><td>${ref_price:.2f} <span style="color:#888;">({ref_date})</span></td></tr>
    <tr><td style="padding:5px 12px 5px 0;"><b>{ref_label} 대비</b></td><td><b style="color:{color};">{dist:+.2f}%</b></td></tr>
    <tr><td style="padding:5px 12px 5px 0;"><b>임계 가격</b></td><td>${analysis["thresholds"][threshold_key]:.2f}</td></tr>
    <tr><td style="padding:5px 12px 5px 0;"><b>확인 필터</b></td><td>{confirm_str}</td></tr>
    <tr><td style="padding:5px 12px 5px 0;"><b>신호 강도</b></td><td>{strength}</td></tr>
    <tr><td style="padding:5px 12px 5px 0;"><b>권고</b></td><td>{action}</td></tr>
  </table>
</div>
<p style="color:#666; font-size:11px; margin-top:12px;">
거래량 5d/20d: {analysis["vol_ratio"]:.2f}× &nbsp;|&nbsp;
+DI: {analysis["plus_di"]:.1f} / -DI: {analysis["minus_di"]:.1f} &nbsp;|&nbsp;
5EMA {">" if analysis["ema5_above_20"] else "<"} 20EMA<br>
검출 시각: {datetime.now().strftime("%Y-%m-%d %H:%M")} PT
</p>
</body></html>"""
    return subject, html


def render_daily_report(analyses: List[Dict], status_changes: Dict) -> Tuple[str, str]:
    """일일 종합 리포트 (장 마감 30분 후)."""
    today = datetime.now().strftime("%Y-%m-%d")

    rows = []
    for a in analyses:
        ticker = a["ticker"]
        trend = a["trend"]
        status = trend.get("status", "n/a")
        emoji = STATUS_EMOJI.get(status, "")
        status_ko = STATUS_KO.get(status, status)

        change_marker = ""
        if ticker in status_changes:
            old = status_changes[ticker].get("old", "n/a")
            change_marker = (
                f"<br><span style='color:#c00;font-size:10px;'>"
                f"(변경: {STATUS_KO.get(old, old)} → {status_ko})</span>"
            )

        loss_tier = a.get("loss_tier") or "—"
        buy_tier = a.get("buy_tier") or "—"
        loss_label = LOSS_TIER_LABEL.get(loss_tier, "—")
        buy_label = BUY_TIER_LABEL.get(buy_tier, "—")

        rows.append(f"""
<tr>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;"><b>{ticker}</b></td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">${a['current_price']:.2f}</td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">{emoji} {status_ko}{change_marker}</td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">${a['peak']:.2f}<br><span style='font-size:10px;color:#888;'>{a['dist_from_peak_pct']:+.1f}%</span></td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">${a['trough']:.2f}<br><span style='font-size:10px;color:#888;'>{a['dist_from_trough_pct']:+.1f}%</span></td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">{loss_label}</td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">{buy_label}</td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">{trend.get('adx', 0):.1f}</td>
</tr>""")

    threshold_rows = []
    for a in analyses:
        t = a["thresholds"]
        threshold_rows.append(f"""
<tr>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;"><b>{a['ticker']}</b></td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;">${t['stop_watch']:.2f}</td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;color:#e67e22;">${t['stop_alert']:.2f}</td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;color:#c0392b;"><b>${t['stop_forced']:.2f}</b></td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;">${t['buy_watch']:.2f}</td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;color:#16a085;">${t['buy_alert']:.2f}</td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;color:#27ae60;"><b>${t['buy_add']:.2f}</b></td>
</tr>""")

    subject = f"[일일 리포트] {today} — 6 종목 추세/신호"
    html = f"""<html><body style="font-family:-apple-system,sans-serif; max-width:760px;">
<h2 style="margin-bottom:4px;">일일 추세/신호 리포트</h2>
<p style="color:#666; margin-top:0;">{today} (PT 1:30 PM 기준)</p>

<table style="border-collapse:collapse; width:100%; font-size:13px;">
<thead style="background:#2c3e50; color:white;">
<tr>
  <th style="padding:8px;text-align:left;">종목</th>
  <th style="padding:8px;text-align:left;">현재가</th>
  <th style="padding:8px;text-align:left;">추세</th>
  <th style="padding:8px;text-align:left;">고점/대비</th>
  <th style="padding:8px;text-align:left;">저점/대비</th>
  <th style="padding:8px;text-align:left;">손절 단계</th>
  <th style="padding:8px;text-align:left;">매수 단계</th>
  <th style="padding:8px;text-align:left;">ADX</th>
</tr>
</thead>
<tbody>
{"".join(rows)}
</tbody>
</table>

<h3 style="margin-top:28px;">상세 임계 가격</h3>
<table style="border-collapse:collapse; width:100%; font-size:12px;">
<thead style="background:#34495e; color:white;">
<tr>
  <th style="padding:6px 8px;text-align:left;">종목</th>
  <th style="padding:6px 8px;text-align:left;">손절 1차</th>
  <th style="padding:6px 8px;text-align:left;">손절 2차</th>
  <th style="padding:6px 8px;text-align:left;">손절 3차</th>
  <th style="padding:6px 8px;text-align:left;">매수 1차</th>
  <th style="padding:6px 8px;text-align:left;">매수 2차</th>
  <th style="padding:6px 8px;text-align:left;">매수 3차</th>
</tr>
</thead>
<tbody>
{"".join(threshold_rows)}
</tbody>
</table>

<p style="color:#888;font-size:11px;margin-top:24px;">
범례: 추세 상태는 5일 EMA 종가 기준 60일 윈도우의 분할 회귀 + ADX + MA20 기울기로 분류.
손절/매수 단계는 최근 40거래일 고점/저점 대비 현재가 위치.
2차/3차 신호 도달 시 장중 별도 알림 발송됨.
</p>
</body></html>"""
    return subject, html
