"""
거시경제 데이터 수집 스크립트
yfinance + 한국은행 ECOS API로 주요 지표를 수집하여 macro_data.json에 저장합니다.
"""

import json
import csv
import datetime
import urllib.request
import urllib.error
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

try:
    import yfinance as yf
except ImportError:
    raise SystemExit("yfinance 패키지가 필요합니다: pip install yfinance")

# ==========================================
# 설정
# ==========================================

OUTPUT_PATH  = os.path.join(os.path.dirname(__file__), "macro_data.json")
HISTORY_PATH = os.path.join(os.path.dirname(__file__), "history.csv")
HISTORY_COLS = ["date", "us10y", "us2y", "krw", "kospi", "kr_base", "spread", "rate_diff"]

ECOS_API_KEY = "sample"

FALLBACKS = {
    "us_10y":    4.48,
    "us_2y":     4.80,
    "usd_krw":   1380.0,
    "kospi":     2700.0,
    "kr_base":   3.50,
}

# ==========================================
# 수집 함수
# ==========================================

def fetch_yfinance(ticker: str, label: str, fallback: float) -> float:
    """yfinance에서 최신 종가를 가져옵니다. 실패 시 fallback 반환."""
    try:
        data = yf.Ticker(ticker).history(period="5d")
        if data.empty:
            raise ValueError("빈 데이터")
        value = round(float(data["Close"].dropna().iloc[-1]), 4)
        print(f"  ✅ {label}: {value}")
        return value
    except Exception as e:
        print(f"  ⚠️  {label} 수집 실패 ({e}) → fallback {fallback} 사용")
        return fallback


def fetch_kr_base_rate(fallback: float) -> float:
    """
    한국은행 ECOS API (통계코드 722Y001, 아이템코드 0101000)에서
    기준금리를 가져옵니다. 실패 시 fallback 반환.
    """
    today = datetime.date.today()
    # 최근 3개월 범위로 조회하여 가장 최근 값을 사용
    start = (today - datetime.timedelta(days=90)).strftime("%Y%m")
    end = today.strftime("%Y%m")
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_API_KEY}/json/kr"
        f"/1/5/722Y001/MM/{start}/{end}/0101000"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as res:
            body = json.loads(res.read().decode("utf-8"))
        rows = body.get("StatisticSearch", {}).get("row", [])
        if not rows:
            raise ValueError("빈 응답")
        value = round(float(rows[-1]["DATA_VALUE"]), 2)
        print(f"  ✅ 한국 기준금리: {value}%")
        return value
    except Exception as e:
        print(f"  ⚠️  한국 기준금리 수집 실패 ({e}) → fallback {fallback} 사용")
        return fallback


# ==========================================
# 메인
# ==========================================

def main():
    print("=" * 50)
    print("📡 거시경제 데이터 수집 시작")
    print("=" * 50)

    us_10y  = fetch_yfinance("^TNX",  "미 국채 10년물 금리", FALLBACKS["us_10y"])
    us_2y   = fetch_yfinance("^IRX",  "미 국채 2년물 금리",  FALLBACKS["us_2y"])
    usd_krw = fetch_yfinance("KRW=X", "원달러 환율",         FALLBACKS["usd_krw"])
    kospi   = fetch_yfinance("^KS11", "코스피 지수",         FALLBACKS["kospi"])
    kr_base = fetch_kr_base_rate(FALLBACKS["kr_base"])

    # 파생값
    spread_10y_2y = round(us_10y - us_2y, 4)       # 장단기 스프레드
    rate_diff_us_kr = round(us_10y - kr_base, 4)   # 한미 금리차 (10Y 기준)

    print()
    print(f"  📐 장단기 스프레드 (10Y-2Y): {spread_10y_2y:+.2f}%p")
    print(f"  📐 한미 금리차 (미 10Y - 한국 기준): {rate_diff_us_kr:+.2f}%p")

    result = {
        "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "us_10y_yield":    us_10y,
        "us_2y_yield":     us_2y,
        "usd_krw":         usd_krw,
        "kospi":           kospi,
        "kr_base_rate":    kr_base,
        "spread_10y_2y":   spread_10y_2y,
        "rate_diff_us_kr": rate_diff_us_kr,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    _append_history(result)

    print()
    print(f"✅ 저장 완료: {OUTPUT_PATH}")
    print(f"✅ 이력 추가: {HISTORY_PATH}")
    print("=" * 50)


def _append_history(result: dict):
    """수집 결과를 history.csv에 한 행 추가한다. 파일 없으면 헤더 포함 생성."""
    row = {
        "date":      result["fetched_at"],
        "us10y":     result["us_10y_yield"],
        "us2y":      result["us_2y_yield"],
        "krw":       result["usd_krw"],
        "kospi":     result["kospi"],
        "kr_base":   result["kr_base_rate"],
        "spread":    result["spread_10y_2y"],
        "rate_diff": result["rate_diff_us_kr"],
    }
    write_header = not os.path.exists(HISTORY_PATH)
    with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_COLS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


if __name__ == "__main__":
    main()