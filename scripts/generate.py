#!/usr/bin/env python3
"""
Dahlia 자동 글 생성기
사용법:
  python3 generate.py --product "LG 32GX870B" --category display
  python3 generate.py --product "LG 32GX870B" --category display --compare "삼성 G80SH"
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
from pathlib import Path

BASE_DIR  = Path.home() / "dahlia"
SITE_DIR  = BASE_DIR / "site"
LEDGER_DB = BASE_DIR / "data" / "ledger.db"
ENV_FILE  = BASE_DIR / ".env"

MODELS = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]

CAT_ITEMS = {
    "computer": "CPU, GPU, 노트북",
    "display":  "모니터, TV, 빔프로젝터",
    "mobile":   "스마트폰, 태블릿, 이어폰, 워치",
    "audio":    "스피커, 헤드셋, 마이크, DAC",
    "gadget":   "마우스, 키보드, 데스크테리어",
    "play":     "게임기, 게이밍기어",
    "frame":    "카메라, 렌즈",
}


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
        sys.exit("GEMINI_API_KEY가 없습니다. ~/dahlia/.env 에 추가하세요.")
    return key


# ── 공식 이미지 수집 ──────────────────────────────────────────────────────────

# 브랜드 → 공식 도메인 매핑
BRAND_SITES = {
    "삼성": "samsung.com", "samsung": "samsung.com",
    "lg": "lg.com",
    "apple": "apple.com",
    "sony": "sony.com",
    "asus": "asus.com",
    "dell": "dell.com",
    "hp": "hp.com",
    "lenovo": "lenovo.com",
    "microsoft": "microsoft.com",
    "google": "store.google.com",
    "motorola": "motorola.com",
    "bose": "bose.com",
    "sennheiser": "sennheiser.com",
    "canon": "canon.com", "캐논": "canon.com",
    "nikon": "nikon.com", "니콘": "nikon.com",
    "fujifilm": "fujifilm.com", "후지": "fujifilm.com",
    "acer": "acer.com",
    "razer": "razer.com",
    "msi": "msi.com",
    "meta": "meta.com",
    "nintendo": "nintendo.com", "닌텐도": "nintendo.com",
    "playstation": "playstation.com", "소니": "sony.com",
    "xbox": "xbox.com",
    "shure": "shure.com",
    "jabra": "jabra.com",
    "logitech": "logitech.com", "로지텍": "logitech.com",
    "corsair": "corsair.com",
    "beyerdynamic": "beyerdynamic.com",
    "audio-technica": "audio-technica.com",
    "jbl": "jbl.com",
    "marshall": "marshallheadphones.com",
}


def get_brand_site(product: str) -> str:
    p = product.lower()
    for brand, site in BRAND_SITES.items():
        if brand in p:
            return site
    return ""


def fetch_official_images(product: str, slug: str, max_images: int = 3) -> list:
    """
    공식 제품 페이지의 og:image만 수집.
    공식 도메인 확인 안 되면 이미지 없이 진행.
    """
    import httpx
    import re as _re

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        return []

    brand_site = get_brand_site(product)
    img_dir = SITE_DIR / "static" / "images" / slug
    img_dir.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    # 1. 공식 페이지 URL 검색
    page_urls = []
    try:
        with DDGS() as ddgs:
            q = f'"{product}"' + (f" site:{brand_site}" if brand_site else " official site")
            results = list(ddgs.text(q, max_results=5, region="kr-kr"))
            if not results and brand_site:
                results = list(ddgs.text(f'"{product}" site:{brand_site}', max_results=5))
            for r in results:
                url = r.get("href", "")
                # 공식 도메인만 허용
                if brand_site and brand_site in url:
                    page_urls.append(url)
                elif not brand_site and any(s in url for s in BRAND_SITES.values()):
                    page_urls.append(url)
    except Exception as e:
        print(f"  [이미지] 검색 실패: {e}")
        return []

    if not page_urls:
        print(f"  [이미지] 공식 페이지 없음 — 이미지 생략")
        return []

    # 2. 각 페이지에서 og:image 추출 후 다운로드
    saved = []
    for page_url in page_urls:
        if len(saved) >= max_images:
            break
        try:
            resp = httpx.get(page_url, timeout=10, follow_redirects=True, headers=headers)
            if resp.status_code != 200:
                continue

            # og:image / twitter:image 추출
            og_imgs = _re.findall(
                r'<meta[^>]+(?:property=["\']og:image["\']|name=["\']twitter:image["\'])[^>]+content=["\']([^"\']+)["\']',
                resp.text
            )
            og_imgs += _re.findall(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property=["\']og:image["\']|name=["\']twitter:image["\'])',
                resp.text
            )

            for img_url in og_imgs:
                if not img_url.startswith("http"):
                    img_url = f"https://{brand_site}{img_url}" if img_url.startswith("/") else None
                if not img_url:
                    continue
                try:
                    ir = httpx.get(img_url, timeout=8, follow_redirects=True, headers=headers)
                    ct = ir.headers.get("content-type", "")
                    if ir.status_code != 200 or "image" not in ct:
                        continue
                    ext = "jpg" if "jpeg" in ct or "jpg" in ct else "png"
                    fname = f"img{len(saved)+1}.{ext}"
                    (img_dir / fname).write_bytes(ir.content)
                    saved.append({
                        "path": f"/images/{slug}/{fname}",
                        "source_url": page_url,
                        "alt": product,
                    })
                    print(f"  [이미지] {fname} ← {page_url[:60]}")
                    break
                except Exception:
                    continue
        except Exception:
            continue

    if not saved:
        print("  [이미지] 공식 이미지 없음 — 이미지 생략")
    return saved


# ── 실제 스펙 검색 ────────────────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5) -> str:
    """DuckDuckGo로 검색, 스니펫 반환. 실패 시 빈 문자열."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region="kr-kr"))
            if not results:
                results = list(ddgs.text(query, max_results=max_results))
            snippets = [f"[{r.get('title','')}] {r.get('body','')}" for r in results]
            return "\n".join(snippets)
    except Exception as e:
        print(f"[검색 실패] {e}")
        return ""


def fetch_specs(product: str) -> str:
    """제품 공식 스펙 검색. 여러 쿼리 시도."""
    print(f"  [검색] {product}")
    # 영문 모델명이 포함된 제품이면 영문 검색도 시도
    info = web_search(f'"{product}" 스펙 사양 공식')
    if not info:
        info = web_search(f'"{product}" specifications review')
    return info


# ── 모델명 검증 ───────────────────────────────────────────────────────────────

def extract_key_tokens(name: str) -> list[str]:
    """모델명에서 핵심 토큰(숫자+알파벳 조합) 추출. 예: '32GX870B' → ['32GX870B']"""
    return re.findall(r"[A-Z0-9]{4,}", name.upper())


def validate_model_names(body: str, product: str, compare: str) -> list[str]:
    """
    생성된 글에 요청한 모델명의 핵심 토큰이 있는지 확인.
    없으면 오류 목록 반환.
    """
    issues = []
    body_upper = body.upper()

    for name in [product] + ([compare] if compare else []):
        tokens = extract_key_tokens(name)
        for tok in tokens:
            if tok not in body_upper:
                issues.append(f"모델명 누락/변조: '{tok}' (원본: {name})")

    return issues


# ── Gemini 호출 ───────────────────────────────────────────────────────────────

def call_gemini(client, prompt: str) -> str:
    """모델 폴백 순서로 Gemini 호출. 반환값: 생성된 텍스트."""
    for model in MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"temperature": 0.2},   # 낮을수록 사실에 충실
            )
            print(f"  [모델] {model}")
            return resp.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                print(f"  [{model}] 할당량 초과 → 다음 모델")
                continue
            if "500" in err or "503" in err:
                print(f"  [{model}] 서버 오류 → 잠시 후 재시도")
                time.sleep(5)
                continue
            sys.exit(f"Gemini 오류 ({model}): {e}")
    sys.exit("모든 Gemini 모델 할당량 초과. 내일 다시 시도하세요.")


# ── 메인 생성 함수 ────────────────────────────────────────────────────────────

def generate_article(product: str, category: str, compare: str = "") -> tuple:
    """(title, body_markdown) 반환. 모델명 검증 실패 시 재시도."""
    try:
        from google import genai
    except ImportError:
        sys.exit("python3 -m pip install google-genai --break-system-packages")

    client = genai.Client(api_key=get_api_key())
    cat_hint = CAT_ITEMS.get(category, "")

    # 1. 실제 스펙 검색
    print("[단계 1] 실제 스펙 검색 중...")
    product_info = fetch_specs(product)
    compare_info = fetch_specs(compare) if compare else ""

    spec_block = ""
    if product_info:
        spec_block += f"\n\n=== {product} 실제 검색 결과 (이 정보를 우선 사용) ===\n{product_info[:2000]}"
    if compare_info:
        spec_block += f"\n\n=== {compare} 실제 검색 결과 (이 정보를 우선 사용) ===\n{compare_info[:2000]}"

    compare_line = f"비교 대상: **{compare}**" if compare else "동급 경쟁 제품 또는 이전 세대와 비교"

    # 2. 글 생성 (최대 2회 시도)
    print("[단계 2] 글 생성 중...")
    for attempt in range(2):
        retry_note = "" if attempt == 0 else (
            "\n\n⚠️ 이전 시도에서 모델명이 잘못됐습니다. 반드시 아래 정확한 모델명만 사용하세요."
        )
        prompt = f"""당신은 한국어 IT 전문 블로그 에디터입니다.

━━━ 절대 규칙 ━━━
주 제품명: "{product}"
비교 제품명: "{compare if compare else '없음'}"

위 모델명을 글 전체에서 단 한 글자도 바꾸지 마세요.
비슷한 모델명(예: 숫자·알파벳 하나만 다른 이름)을 쓰는 것은 심각한 오류입니다.
확실하지 않은 스펙은 지어내지 말고 "공식 사이트 참고" 로 표기하세요.
{retry_note}
━━━━━━━━━━━━━
{spec_block}
━━━━━━━━━━━━━

카테고리: {category} ({cat_hint})
{compare_line}

[글 작성 규칙]
- 한국어, 자연스럽고 읽기 쉽게
- 전문 용어는 쉽게 풀어서 설명
- 단순 스펙 나열 금지 — 실사용 의미와 분석 필수
- 비교표는 마크다운 표(| 형식)로 작성
- 추천 대상 명확히 제시
- 광고성 과장 표현, AI·인공지능 문구 절대 금지

[글 구조]
## 핵심 요약
## 주요 스펙
## 비교 분석
## 실사용 분석
## 추천 대상
## 결론

첫 줄에 "TITLE: 한국어제목" 형식으로 제목을 쓰고 그 다음 줄부터 본문을 시작하세요.
frontmatter 없이 본문만 작성하세요."""

        text = call_gemini(client, prompt)

        # 3. 모델명 검증
        issues = validate_model_names(text, product, compare)
        if not issues:
            break

        print(f"  [경고] 모델명 검증 실패 (시도 {attempt+1}/2): {issues}")
        if attempt == 1:
            # 2회 시도 후에도 실패하면 경고와 함께 진행
            print("  [경고] 모델명 검증 2회 실패. 내용을 확인하고 필요시 수동 수정하세요.")

    # 제목 파싱
    lines = text.split("\n")
    title = product
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("TITLE:"):
            title = line.replace("TITLE:", "").strip()
            body_start = i + 1
            break

    body = "\n".join(lines[body_start:]).strip()
    return title, body


# ── 저장 / 기록 ───────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text).strip("-")
    return text or "article"


def already_covered(product: str) -> bool:
    conn = sqlite3.connect(LEDGER_DB)
    try:
        return bool(conn.execute(
            "SELECT id FROM products WHERE LOWER(name)=LOWER(?)", (product,)
        ).fetchone())
    finally:
        conn.close()


def save_and_record(product: str, category: str, title: str, body: str, images: list = None) -> Path:
    now = datetime.now(KST)
    date_str    = now.strftime("%Y-%m-%d")
    datetime_str = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    slug = slugify(product)
    filename = f"{date_str}-{slug}.md"

    content_dir = SITE_DIR / "content" / category.lower()
    content_dir.mkdir(parents=True, exist_ok=True)
    filepath = content_dir / filename

    description = ""
    for line in body.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("|") and len(line) > 40:
            description = line[:150].rstrip(".,") + "."
            break

    images = images or []
    cover = images[0] if images else None

    cover_block = ""
    if cover:
        cover_block = f"""cover:
  image: "{cover['path']}"
  alt: "{product}"
  caption: "출처: {cover['source_url']}"
  relative: false
"""

    frontmatter = f"""---
title: "{title}"
date: {datetime_str}
categories: ["{category.title()}"]
description: "{description}"
draft: false
{cover_block}---

"""

    # 추가 이미지(2~3번째)를 본문 중간에 삽입 — 핵심 요약 바로 뒤
    extra_imgs = images[1:]
    if extra_imgs:
        img_md = "\n".join(
            f'![{product}]({img["path"]})\n*출처: {img["source_url"]}*'
            for img in extra_imgs
        )
        # "## 실사용 분석" 앞에 삽입
        body = body.replace("## 실사용 분석", img_md + "\n\n## 실사용 분석", 1)

    filepath.write_text(frontmatter + body, encoding="utf-8")

    conn = sqlite3.connect(LEDGER_DB)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO articles (slug,title,category,status,published_at) "
            "VALUES (?,?,?,'published',datetime('now','localtime'))",
            (slug, title, category),
        )
        conn.execute(
            "INSERT OR IGNORE INTO products (name,brand,category,covered_at) "
            "VALUES (?,?,?,date('now','localtime'))",
            (product, product.split()[0], category),
        )
        conn.execute(
            "UPDATE queue SET status='done',done_at=datetime('now','localtime') "
            "WHERE LOWER(product)=LOWER(?)",
            (product,),
        )
        conn.commit()
    finally:
        conn.close()

    return filepath


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product",  required=True)
    parser.add_argument("--category", required=True, choices=list(CAT_ITEMS.keys()))
    parser.add_argument("--compare",  default="")
    parser.add_argument("--force",    action="store_true", help="중복 무시")
    args = parser.parse_args()

    if not args.force and already_covered(args.product):
        print(f"[건너뜀] 이미 다룬 제품: {args.product}")
        sys.exit(0)

    print(f"[생성 시작] {args.product} ({args.category})")
    title, body = generate_article(args.product, args.category, args.compare)
    print(f"[완료] {title}")

    slug = slugify(args.product)
    print(f"[단계 3] 공식 이미지 수집 중...")
    images = fetch_official_images(args.product, slug)

    filepath = save_and_record(args.product, args.category, title, body, images)
    print(f"[저장] {filepath} (이미지 {len(images)}개)")


if __name__ == "__main__":
    main()
