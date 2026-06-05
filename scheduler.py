"""
매크로 데이터 수집 스케줄러
15분마다 fetch_macro_data.main()을 실행하고 결과를 fetch_log.txt에 기록합니다.
"""

import schedule
import time
import datetime
import traceback
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 같은 폴더의 fetch_macro_data를 import할 수 있도록 경로 추가
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fetch_macro_data import main as fetch_main
from alert_bot import check_and_alert

LOG_PATH = os.path.join(BASE_DIR, "fetch_log.txt")
INTERVAL_MINUTES = 15


def log(message: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def job():
    log("▶ 수집 시작")
    try:
        fetch_main()
        log("✅ 수집 성공")
        try:
            check_and_alert()
        except Exception:
            error_detail = traceback.format_exc().strip().splitlines()[-1]
            log(f"⚠️  경보 체크 실패: {error_detail}")
    except Exception:
        error_detail = traceback.format_exc().strip().splitlines()[-1]
        log(f"❌ 수집 실패: {error_detail}")
        # 전체 스택 트레이스도 로그에 기록
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(traceback.format_exc() + "\n")


def main():
    log(f"🚀 스케줄러 시작 — {INTERVAL_MINUTES}분 간격")

    # 시작 즉시 1회 실행
    job()

    # 이후 15분마다 반복
    schedule.every(INTERVAL_MINUTES).minutes.do(job)

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
