"""이메일 알림 (Gmail SMTP).

GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_RECIPIENT 환경변수 필요.
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
    "late_exit": "⚫ 매도 늦음",
}
BUY_TIER_LABEL = {
    "1st_watch": "🟢 1차 관찰",
    "2nd_alert": "🟡 2차 매수",
    "3rd_add": "🔴 3차 추가",
    "late_entry": "⚫ 진입 늦음",
}


def format_adx_change(adx_now, adx_change_7d):
    """ADX 값 + 7일 변화량 + 화살표 + 색상 HTML 생성."""
    if adx_now is None or adx_now == 0:
        return "<span style='color:#888;'>—</span>"

    adx_str = f"<b>{adx_now:.1f}</b>"
    if adx_change_7d is None:
        change_str = "<span style='font-size:10px;color:#888;'>(7d 데이터 부족)</span>"
    else:
        ch = adx_change_7d
        if ch >= 3.0:
            arrow = "↗"
            color = "#c0392b"
            suffix = " 🔴"
        elif ch >= 1.0:
            arrow = "↗"
            color = "#e67e22"
            suffix = ""
        elif ch > -1.0:
            arrow = "→"
            color = "#666"
            suffix = ""
        elif ch > -3.0:
            arrow = "↘"
            color = "#16a085"
            suffix = ""
        else:
            arrow = "↘"
            color = "#2980b9"
            suffix = " 🔵"
        sign = "+" if ch >= 0 else ""
        change_str = (
            f"<span style='font-size:11px;color:{color};'>"
            f"{arrow} {sign}{ch:.1f}{suffix}</span>"
        )
    return f"{adx_str}<br>{change_str}"


def send_email(subject: str, html_body: str, plain_body: str = ""):
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
    ticker = analysis["ticker"]
    price = analysis["current_price"]
    close_date = analysis.get("last_close_date", "")

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
    else:
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
    <tr><td style="padding:5px 12px 5px 0;"><b>현재가 (종가 {close_date})</b></td><td>${price:.2f}</td></tr>
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


def render_daily_report(analyses: List[Dict], status_changes: Dict, window_label: str = "") -> Tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")

    ref_close_date = ""
    if analyses:
        ref_close_date = analyses[0].get("last_close_date", "")

    stale_banner = ""
    stale_count = sum(1 for a in analyses if a.get("data_stale"))
    if stale_count > 0:
        max_age = max((a.get("data_age_days", 0) for a in analyses), default=0)
        stale_banner = (
            '<div style="background:#fef3c7;border-left:4px solid #f59e0b;'
            'padding:10px 14px;margin:8px 0;color:#78350f;font-size:13px;">'
            f'⚠️ <b>데이터 lag 경고</b>: yfinance에서 fetch한 종가가 직전 거래일 대비 {max_age}일 lag. '
            f'{stale_count}/{len(analyses)} 종목이 stale. 실제 brokerage 가격과 차이 가능 — '
            '다음 cron 실행 시 자동 갱신.</div>'
        )

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

        peak_date = a.get("peak_date", "")
        trough_40d_date = a.get("trough_40d_date", a.get("trough_date", ""))
        trough_20d_date = a.get("trough_20d_date", "")
        dist_peak = a.get("dist_from_peak_pct", 0)
        dist_trough_40d = a.get("dist_from_trough_40d_pct", a.get("dist_from_trough_pct", 0))
        dist_trough_20d = a.get("dist_from_trough_20d_pct", 0)

        vol_ratio = a.get('vol_ratio', 1.0)
        if vol_ratio >= 1.30:
            vol_color = "#27ae60"
            vol_emoji = "🔥"
        elif vol_ratio >= 1.10:
            vol_color = "#16a085"
            vol_emoji = "↑"
        elif vol_ratio < 0.80:
            vol_color = "#888"
            vol_emoji = "↓"
        else:
            vol_color = "#666"
            vol_emoji = ""

        adx_now = trend.get("adx", 0)
        adx_change_7d = trend.get("adx_change_7d")
        adx_cell = format_adx_change(adx_now, adx_change_7d)

        rows.append(f"""
<tr>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;"><b>{ticker}</b></td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">${a['current_price']:.2f}</td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">{emoji} {status_ko}{change_marker}</td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">${a['peak']:.2f}<br><span style='font-size:10px;color:#888;'>{peak_date} / {dist_peak:+.1f}%</span></td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">${a['trough_40d']:.2f}<br><span style='font-size:10px;color:#888;'>{trough_40d_date} / {dist_trough_40d:+.1f}%</span></td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;background:#f5f5f5;">${a['trough_20d']:.2f}<br><span style='font-size:10px;color:#888;'>{trough_20d_date} / {dist_trough_20d:+.1f}%</span></td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">{loss_label}</td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">{buy_label}</td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;color:{vol_color};"><b>{vol_ratio:.2f}×</b> {vol_emoji}</td>
  <td style="padding:6px 8px;border-bottom:1px solid #eee;">{adx_cell}</td>
</tr>""")

    threshold_rows = []
    for a in analyses:
        t = a["thresholds"]
        peak = a['peak']
        trough = a.get('trough_40d', a['trough'])
        sw_pct = (t['stop_watch'] - peak) / peak * 100
        sa_pct = (t['stop_alert'] - peak) / peak * 100
        sf_pct = (t['stop_forced'] - peak) / peak * 100
        bw_pct = (t['buy_watch'] - trough) / trough * 100
        ba_pct = (t['buy_alert'] - trough) / trough * 100
        bd_pct = (t['buy_add'] - trough) / trough * 100
        threshold_rows.append(f"""
<tr>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;"><b>{a['ticker']}</b></td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;">${t['stop_watch']:.2f}<br><span style='font-size:10px;color:#888;'>{sw_pct:+.1f}%</span></td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;color:#e67e22;">${t['stop_alert']:.2f}<br><span style='font-size:10px;color:#888;'>{sa_pct:+.1f}%</span></td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;color:#c0392b;"><b>${t['stop_forced']:.2f}</b><br><span style='font-size:10px;color:#888;'>{sf_pct:+.1f}%</span></td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;">${t['buy_watch']:.2f}<br><span style='font-size:10px;color:#888;'>{bw_pct:+.1f}%</span></td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;color:#16a085;">${t['buy_alert']:.2f}<br><span style='font-size:10px;color:#888;'>{ba_pct:+.1f}%</span></td>
  <td style="padding:4px 8px;border-bottom:1px solid #eee;color:#27ae60;"><b>${t['buy_add']:.2f}</b><br><span style='font-size:10px;color:#888;'>{bd_pct:+.1f}%</span></td>
</tr>""")

    # window_label 시간대 prefix 추출
    window_short = ""
    if "장초반" in window_label:
        window_short = "장초반"
    elif "장중후반" in window_label:
        window_short = "장중후반"
    elif "장후" in window_label:
        window_short = "장후"
    elif window_label:
        window_short = "수시"

    subject_prefix = f"[일일 리포트{' ' + window_short if window_short else ''}]"
    subject = f"{subject_prefix} {today} — {len(analyses)} 종목 추세/신호"

    header_window_label = f'<span style="color:#3498db;font-size:14px;"> — {window_label}</span>' if window_label else ''

    html = f"""<html><body style="font-family:-apple-system,sans-serif; max-width:900px;">
<h2 style="margin-bottom:4px;">일일 추세/신호 리포트{header_window_label}</h2>
<p style="color:#666; margin-top:0;">발송일 {today} · 데이터 기준일 <b>{ref_close_date}</b> 종가</p>
{stale_banner}

<table style="border-collapse:collapse; width:100%; font-size:13px;">
<thead style="background:#2c3e50; color:white;">
<tr>
  <th style="padding:8px;text-align:left;">종목</th>
  <th style="padding:8px;text-align:left;">종가</th>
  <th style="padding:8px;text-align:left;">추세</th>
  <th style="padding:8px;text-align:left;">고점 (40일)<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>일자/대비</span></th>
  <th style="padding:8px;text-align:left;">저점 (40일)<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>일자/대비</span></th>
  <th style="padding:8px;text-align:left;background:#34495e;">저점 (20일)<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>일자/대비 (참고)</span></th>
  <th style="padding:8px;text-align:left;">손절 단계</th>
  <th style="padding:8px;text-align:left;">매수 단계</th>
  <th style="padding:8px;text-align:left;">거래량<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>(5d/20d)</span></th>
  <th style="padding:8px;text-align:left;">ADX<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>변화 (7d)</span></th>
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
  <th style="padding:6px 8px;text-align:left;">손절 1차<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>(고점대비)</span></th>
  <th style="padding:6px 8px;text-align:left;">손절 2차<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>(고점대비)</span></th>
  <th style="padding:6px 8px;text-align:left;">손절 3차<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>(고점대비)</span></th>
  <th style="padding:6px 8px;text-align:left;">매수 1차<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>(40일 저점대비)</span></th>
  <th style="padding:6px 8px;text-align:left;">매수 2차<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>(40일 저점대비)</span></th>
  <th style="padding:6px 8px;text-align:left;">매수 3차<br><span style='font-size:9px;font-weight:normal;color:#bbb;'>(40일 저점대비)</span></th>
</tr>
</thead>
<tbody>
{"".join(threshold_rows)}
</tbody>
</table>

<div style="background:#f0f8ff;border-left:4px solid #3498db;padding:10px 14px;margin-top:24px;font-size:12px;color:#2c3e50;">
<b>표 해석 가이드</b><br>
- <b>저점 (40일)</b>: 시장 사이클 전체 관점 — 매수/손절 <b>단계 결정 기준</b><br>
- <b>저점 (20일)</b>: 최근 swing 관점 — 단기 진입 기회 <b>참고용</b> (단계에 영향 X)<br>
- <b>⚫ 진입 늦음</b>: 40일 저점 대비 이미 너무 올랐거나 rising 추세 진입 → 신규 매수 부적합<br>
- <b>⚫ 매도 늦음</b>: 40일 고점 대비 이미 너무 떨어졌거나 falling 추세 진입 → 손절 의미 약함<br>
- 20일 저점 대비 거리%가 작으면 단기 swing trader는 추가 진입 검토 가능
</div>

<div style="background:#fef9e7;border-left:4px solid #f39c12;padding:10px 14px;margin-top:12px;font-size:12px;color:#2c3e50;">
<b>ADX 변화 (7일) 해석</b><br>
- 🔴 <b>+3.0 이상</b>: 추세 빠르게 강화 — 과열 주의, mean reversion 압력 증가<br>
- <span style="color:#e67e22;">↗ +1.0~+3.0</span>: 추세 점진적 강화 (정상)<br>
- <span style="color:#666;">→ ±1.0 이내</span>: 변화 미미 (현 상태 유지)<br>
- <span style="color:#16a085;">↘ -1.0~-3.0</span>: 추세 점진적 약화 (반전 신호 형성 가능)<br>
- 🔵 <b>-3.0 이하</b>: 추세 빠르게 약화 — 반전 임박 가능성, 진입/이탈 신중
</div>

<p style="color:#888;font-size:11px;margin-top:16px;">
모든 가격은 raw 종가 기준 (brokerage 화면과 일치). 추세 분류는 5일 EMA 기반.
2차/3차 신호는 거래량/DI cross/EMA cross 확인 필터 거쳐 발송 → noise 자동 차단.
거래량 1.30× 이상이면 confirmation 필터의 volume_surge 충족.
</p>
</body></html>"""
    return subject, html
