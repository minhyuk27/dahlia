#!/usr/bin/env python3
"""
큐 자동 보충 — 항상 50개(pending) 유지
우선순위: 사용자 추가(priority=0) → 자동 추가(priority=100, 최신 출시순)
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR  = Path.home() / "dahlia"
LEDGER_DB = BASE_DIR / "data" / "ledger.db"
ENV_FILE  = BASE_DIR / ".env"
TARGET    = 50

CATEGORIES = ["computer", "display", "mobile", "audio", "gadget", "play", "frame"]


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def get_api_key():
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        sys.exit("GEMINI_API_KEY 없음")
    return key


def pending_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM queue WHERE status='pending'").fetchone()[0]


def already_known(conn, product: str) -> bool:
    return bool(
        conn.execute("SELECT 1 FROM queue WHERE LOWER(product)=LOWER(?)", (product,)).fetchone()
        or conn.execute("SELECT 1 FROM products WHERE LOWER(name)=LOWER(?)", (product,)).fetchone()
    )


MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]


def search_recent_products() -> str:
    """DuckDuckGo로 최근 1달 신제품 실제 검색"""
    from datetime import datetime, timedelta
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        now = datetime.now()
        month_ko = now.strftime("%Y년 %m월")
        prev_ko  = (now.replace(day=1) - timedelta(days=1)).strftime("%Y년 %m월")

        snippets = []
        queries = [
            f"{month_ko} 신제품 출시 모니터 TV 노트북 스마트폰",
            f"{prev_ko} 신제품 출시 카메라 이어폰 게임기",
            f"site:naver.com OR site:danawa.com {month_ko} 신제품",
        ]
        with DDGS() as ddgs:
            for q in queries:
                results = list(ddgs.text(q, max_results=4, region="kr-kr"))
                for r in results:
                    snippets.append(f"[{r.get('title','')}] {r.get('body','')[:200]}")

        return "\n".join(snippets[:10])
    except Exception as e:
        print(f"  [검색 실패] {e}")
        return ""


def discover_products(need: int) -> list:
    try:
        from google import genai
    except ImportError:
        sys.exit("google-genai 패키지 없음")

    client = genai.Client(api_key=get_api_key())
    per_cat = max(3, need // len(CATEGORIES) + 3)

    # 실제 최신 제품 웹 검색
    print("  [웹검색] 최근 1달 신제품 탐색 중...")
    recent_web = search_recent_products()
    web_section = f"\n\n[최근 실제 출시 제품 검색 결과 — 이 제품들을 최우선으로 포함]\n{recent_web}" if recent_web else ""

    from datetime import datetime
    now_ym = datetime.now().strftime("%Y-%m")

    prompt = f"""당신은 IT 제품 전문가입니다. 각 카테고리별로 최신 출시 제품을 {per_cat}개씩 추천하세요.

카테고리: {', '.join(CATEGORIES)}
현재 날짜: {now_ym}
{web_section}

[우선순위 규칙 — 반드시 이 순서로]
1순위: 위 검색 결과에 나온 제품 (가장 최신, 이달/지난달 출시)
2순위: 2026년 출시 제품
3순위: 2025년 하반기(7~12월) 출시 제품
4순위: 2025년 상반기 출시 제품
— 2024년 이전 제품은 절대 포함하지 말 것

[기타 조건]
- 실제로 존재하는 정확한 모델명만 (추측·조합 금지)
- 한국 출시 또는 한국 시장 관심도 높은 제품
- 비교하기 좋은 경쟁/이전세대 제품 포함
- 같은 브랜드가 한 카테고리에 3개 이상 몰리지 않게

반드시 아래 JSON 배열 형식으로만 응답 (다른 텍스트 없이):
[
  {{"product": "정확한 제품명", "category": "카테고리영문소문자", "compare_with": "비교제품명", "release_date": "YYYY-MM"}},
  ...
]"""

    for model in MODELS:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            text = response.text.strip()
            start = text.find("[")
            end   = text.rfind("]") + 1
            if start == -1 or end == 0:
                print(f"[{model}] JSON 없음, 다음 모델 시도")
                continue
            print(f"[모델] {model} 사용")
            return json.loads(text[start:end])
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                print(f"[{model}] 할당량 초과, 다음 모델 시도")
                continue
            print(f"[{model}] 오류: {e}")
            continue

    print("[오류] 사용 가능한 Gemini 모델이 없습니다. 내일 다시 시도합니다.")
    return []


def refill(notify_fn=None):
    """
    큐를 TARGET개로 보충.
    notify_fn: 결과 메시지를 외부로 보낼 콜백 (봇 알림용), optional.
    """
    conn = sqlite3.connect(LEDGER_DB)
    try:
        current = pending_count(conn)
        print(f"[큐] 현재 대기: {current}개 / 목표: {TARGET}개")

        if current >= TARGET:
            print("[큐] 충분합니다.")
            return 0

        need = TARGET - current
        print(f"[큐] {need}개 보충 — Gemini 탐색 중...")

        candidates = discover_products(need)
        added = 0
        skipped = 0

        for item in candidates:
            if added >= need:
                break
            product  = str(item.get("product", "")).strip()
            category = str(item.get("category", "")).strip().lower()
            compare  = str(item.get("compare_with", "")).strip()
            release  = str(item.get("release_date", "")).strip()

            if not product or category not in CATEGORIES:
                continue
            if already_known(conn, product):
                skipped += 1
                continue

            # 출시 날짜 기반 priority: 최신일수록 낮은 값(높은 우선순위)
            from datetime import datetime
            try:
                age_months = (datetime.now().year * 12 + datetime.now().month) - \
                             (int(release[:4]) * 12 + int(release[5:7])) if release and len(release) >= 7 else 24
            except Exception:
                age_months = 24
            # 1달 이내=10, 3달=30, 6달=60, 1년=100, 그 이상=100
            auto_priority = min(100, max(10, age_months * 5))

            conn.execute(
                "INSERT INTO queue (product,category,compare_with,source,priority,release_date) "
                "VALUES (?,?,?,'auto',?,?)",
                (product, category, compare, auto_priority, release),
            )
            print(f"  + [{release}] {product} ({category})")
            added += 1

        conn.commit()
        total = pending_count(conn)
        msg = f"큐 보충 완료: {added}개 추가 / 건너뜀 {skipped}개 / 총 대기 {total}개"
        print(f"[큐] {msg}")
        if notify_fn:
            notify_fn(msg)
        return added
    finally:
        conn.close()


if __name__ == "__main__":
    refill()
