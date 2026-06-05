"""
텔레그램 경보 봇
macro_data.json을 읽어 이상 신호 발생 시 텔레그램 채널로 경보를 발송합니다.
같은 경보는 1시간 내 중복 발송하지 않습니다.
"""

import json
import os
import datetime
import urllib.request
import urllib.error
import urllib.parse

try:
    from dotenv import load_dotenv
except ImportError:
    raise SystemExit("python-dotenv 패키지가 필요합니다: pip install python-dotenv")

# 스크립트와 같은 폴더의 .env 로드
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID   = os.getenv("CHAT_ID", "")

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_PATH      = os.path.join(BASE_DIR, "macro_data.json")
STATE_PATH     = os.path.join(BASE_DIR, "alert_state.json")  # 중복 방지용 타임스탬프 저장
COOLDOWN_HOURS = 1

# 경보 키 목록 (state 파일에서 각 항목별로 마지막 발송 시각을 추적)
ALERT_KEYS = ["ext_risk_high", "spread_inversion", "usd_krw_high"]


# ── 외인 위험도 계산 (dashboard와 동일한 공식) ──────────────────────────
def calc_ext_risk(us_10y: float, kr_base_rate: float, usd_krw: float) -> float:
    r_diff  = us_10y - kr_base_rate
    fx_pred = usd_krw * (1 + r_diff * 0.05)
    risk    = 50 + r_diff * 10 + (fx_pred - 1300) * 0.03
    return max(0.0, min(100.0, risk))


# ── state 파일 로드 / 저장 ────────────────────────────────────────────────
def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {key: None for key in ALERT_KEYS}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ── 쿨다운 체크 ──────────────────────────────────────────────────────────
def is_cooled_down(state: dict, key: str) -> bool:
    """마지막 발송 후 COOLDOWN_HOURS 이상 지났으면 True."""
    last = state.get(key)
    if last is None:
        return True
    delta = datetime.datetime.now() - datetime.datetime.fromisoformat(last)
    return delta.total_seconds() >= COOLDOWN_HOURS * 3600


# ── 텔레그램 메시지 발송 ─────────────────────────────────────────────────
def send_telegram(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[alert_bot] ⚠️  BOT_TOKEN / CHAT_ID 미설정 — 메시지 스킵:\n{text}")
        return False

    url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req     = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            result = json.loads(res.read().decode("utf-8"))
            return result.get("ok", False)
    except urllib.error.URLError as e:
        print(f"[alert_bot] ❌ 텔레그램 전송 실패: {e}")
        return False


# ── 경보 메시지 포맷 ─────────────────────────────────────────────────────
def fmt_alert(title: str, value: str, threshold: str, detail: str) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"🚨 <b>[매크로 경보]</b> {title}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"현재값  : <b>{value}</b>\n"
        f"기준치  : {threshold}\n"
        f"설명     : {detail}\n"
        f"시각     : {now}"
    )


# ── 메인 체크 함수 (scheduler에서 호출) ─────────────────────────────────
def check_and_alert():
    # 데이터 로드
    if not os.path.exists(DATA_PATH):
        print("[alert_bot] macro_data.json 없음 — 스킵")
        return

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    us_10y    = data["us_10y_yield"]
    kr_base   = data["kr_base_rate"]
    usd_krw   = data["usd_krw"]
    spread    = data["spread_10y_2y"]
    ext_risk  = calc_ext_risk(us_10y, kr_base, usd_krw)

    state = load_state()
    sent_any = False

    alerts = [
        (
            "ext_risk_high",
            ext_risk > 70,
            fmt_alert(
                "외인 위험도 임계치 초과",
                f"{ext_risk:.1f}점",
                "70점 초과",
                f"미한금리차 {us_10y - kr_base:+.2f}%p · 환율 {usd_krw:,.0f}원 → 외국인 자금 이탈 위험"
            ),
        ),
        (
            "spread_inversion",
            spread <= -0.1,
            fmt_alert(
                "장단기 금리 역전",
                f"{spread:+.3f}%p",
                "-0.1%p 이하",
                f"10Y {us_10y:.3f}% vs 2Y {data['us_2y_yield']:.3f}% — 역사적 경기침체 선행지표"
            ),
        ),
        (
            "usd_krw_high",
            usd_krw > 1400,
            fmt_alert(
                "원달러 환율 급등",
                f"{usd_krw:,.0f}원",
                "1,400원 초과",
                f"한미금리차 {data['rate_diff_us_kr']:+.2f}%p — 원화 약세 지속 시 외인 매도 압력"
            ),
        ),
    ]

    for key, triggered, message in alerts:
        if triggered and is_cooled_down(state, key):
            ok = send_telegram(message)
            status = "발송 완료" if ok else "발송 실패(설정 확인)"
            print(f"[alert_bot] [{key}] {status}")
            state[key] = datetime.datetime.now().isoformat()
            sent_any = True
        elif triggered:
            remaining = COOLDOWN_HOURS * 3600 - (
                datetime.datetime.now() - datetime.datetime.fromisoformat(state[key])
            ).total_seconds()
            print(f"[alert_bot] [{key}] 쿨다운 중 (잔여 {int(remaining // 60)}분)")
        else:
            # 조건 해제되면 state 초기화 → 다음 번 재트리거 허용
            state[key] = None

    if sent_any:
        save_state(state)
    else:
        save_state(state)  # 쿨다운 해제 반영을 위해 항상 저장


if __name__ == "__main__":
    check_and_alert()
