#!/usr/bin/env python3
"""
Dahlia Lab 텔레그램 봇

명령어:
  /gen 제품명 카테고리 [비교제품]   — 즉시 생성 + 배포
  /add 제품명 카테고리 [비교제품]   — 큐에 추가 (새벽 3시 자동 발행)
  /queue                           — 큐 현황
  /recent                          — 최근 발행 글
  /help                            — 도움말

카테고리: computer display mobile audio gadget play frame
예시: /gen LG C4 OLED 65인치 display 삼성 QD-OLED S95D
"""
import asyncio
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DAHLIA     = Path.home() / "dahlia"
LEDGER_DB  = DAHLIA / "data" / "ledger.db"
CATEGORIES = ["computer", "display", "mobile", "audio", "gadget", "play", "frame"]


def load_env():
    env = DAHLIA / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))


load_env()
TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))

if not TOKEN or not CHAT_ID:
    sys.exit("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 가 .env에 없습니다.")


def authorized(update: Update) -> bool:
    return update.effective_chat.id == CHAT_ID


def parse_args(args: list[str]) -> tuple[str, str, str] | None:
    """args → (product, category, compare). category 키워드 기준으로 분리."""
    cat_idx = next((i for i, a in enumerate(args) if a.lower() in CATEGORIES), None)
    if cat_idx is None or cat_idx == 0:
        return None
    product  = " ".join(args[:cat_idx])
    category = args[cat_idx].lower()
    compare  = " ".join(args[cat_idx + 1:])
    return product, category, compare


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    text = (
        "*Dahlia Lab 봇*\n\n"
        "*즉시 생성+배포*\n"
        "`/gen 제품명 카테고리 [비교제품]`\n\n"
        "*큐에 추가 (새벽 3시 자동)*\n"
        "`/add 제품명 카테고리 [비교제품]`\n\n"
        "*현황*\n"
        "`/queue` — 대기 중인 큐\n"
        "`/recent` — 최근 발행 글\n\n"
        "*카테고리*\n"
        "computer display mobile audio gadget play frame\n\n"
        "*예시*\n"
        "`/gen LG C4 OLED 65인치 display 삼성 QD-OLED S95D`\n"
        "`/add 애플 맥북프로 M4 computer 델 XPS 15`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_gen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    parsed = parse_args(ctx.args or [])
    if not parsed:
        await update.message.reply_text(
            "사용법: `/gen 제품명 카테고리 [비교제품]`\n"
            "예: `/gen LG C4 OLED 65인치 display 삼성 QD-OLED S95D`",
            parse_mode="Markdown",
        )
        return

    product, category, compare = parsed
    lines = [f"⏳ 생성 중...", f"제품: {product}", f"카테고리: {category}"]
    if compare:
        lines.append(f"비교: {compare}")
    msg = await update.message.reply_text("\n".join(lines))

    cmd = [sys.executable, str(DAHLIA / "scripts/generate.py"),
           "--product", product, "--category", category]
    if compare:
        cmd += ["--compare", compare]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

        if proc.returncode != 0:
            err = (stderr or stdout).decode()[:400]
            await msg.edit_text(f"❌ 생성 실패\n`{err}`", parse_mode="Markdown")
            return

        out = stdout.decode()
        title_line = next((l for l in out.splitlines() if l.startswith("[완료]")), "")

        # 배포
        await msg.edit_text(f"✅ 글 완성! 배포 중...\n{title_line}")
        deploy = await asyncio.create_subprocess_exec(
            str(DAHLIA / "scripts/deploy.sh"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(deploy.communicate(), timeout=60)

        if deploy.returncode == 0:
            await msg.edit_text(
                f"✅ 발행 완료!\n{title_line}\nhttps://dahlialab.duckdns.org"
            )
        else:
            await msg.edit_text(f"⚠️ 글 생성됐지만 배포 실패. 수동으로 deploy.sh 실행하세요.")

    except asyncio.TimeoutError:
        await msg.edit_text("❌ 시간 초과 (3분). 나중에 다시 시도하세요.")
    except Exception as e:
        await msg.edit_text(f"❌ 오류: {e}")


async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    parsed = parse_args(ctx.args or [])
    if not parsed:
        await update.message.reply_text(
            "사용법: `/add 제품명 카테고리 [비교제품]`",
            parse_mode="Markdown",
        )
        return

    product, category, compare = parsed
    conn = sqlite3.connect(LEDGER_DB)
    try:
        conn.execute(
            "INSERT INTO queue (product,category,compare_with,source,priority) VALUES (?,?,?,'user',0)",
            (product, category, compare),
        )
        conn.commit()
        user_cnt = conn.execute("SELECT COUNT(*) FROM queue WHERE status='pending' AND source='user'").fetchone()[0]
        auto_cnt = conn.execute("SELECT COUNT(*) FROM queue WHERE status='pending' AND source='auto'").fetchone()[0]
    finally:
        conn.close()

    await update.message.reply_text(
        f"✅ 큐에 추가됨 (최우선)\n제품: {product}\n카테고리: {category}"
        + (f"\n비교: {compare}" if compare else "")
        + f"\n\n대기: 직접추가 {user_cnt}개 · 자동 {auto_cnt}개"
    )


async def cmd_queue(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    conn = sqlite3.connect(LEDGER_DB)
    try:
        user_rows = conn.execute(
            "SELECT id,product,category,compare_with FROM queue WHERE status='pending' AND source='user' ORDER BY id LIMIT 10"
        ).fetchall()
        auto_rows = conn.execute(
            "SELECT id,product,category,release_date FROM queue WHERE status='pending' AND source='auto' ORDER BY release_date DESC, id LIMIT 10"
        ).fetchall()
        user_cnt = conn.execute("SELECT COUNT(*) FROM queue WHERE status='pending' AND source='user'").fetchone()[0]
        auto_cnt = conn.execute("SELECT COUNT(*) FROM queue WHERE status='pending' AND source='auto'").fetchone()[0]
    finally:
        conn.close()

    lines = [f"*큐 현황* — 총 {user_cnt+auto_cnt}개\n"]

    if user_rows:
        lines.append(f"*직접 추가 ({user_cnt}개)*")
        for qid, prod, cat, cmp in user_rows:
            line = f"⭐ {prod} ({cat})"
            if cmp:
                line += f" vs {cmp}"
            lines.append(line)

    if auto_rows:
        lines.append(f"\n*자동 추가 ({auto_cnt}개)*")
        for qid, prod, cat, rel in auto_rows[:5]:
            lines.append(f"• {prod} ({cat})" + (f" [{rel}]" if rel else ""))
        if auto_cnt > 5:
            lines.append(f"  … 외 {auto_cnt-5}개")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_recent(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    conn = sqlite3.connect(LEDGER_DB)
    try:
        rows = conn.execute(
            "SELECT title,category,published_at FROM articles ORDER BY published_at DESC LIMIT 10"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        await update.message.reply_text("아직 발행된 글이 없습니다.")
        return

    lines = ["*최근 발행 글*\n"]
    for title, cat, pub in rows:
        lines.append(f"• [{cat}] {title} ({pub[:10]})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("start",  cmd_help))
    app.add_handler(CommandHandler("gen",    cmd_gen))
    app.add_handler(CommandHandler("add",    cmd_add))
    app.add_handler(CommandHandler("queue",  cmd_queue))
    app.add_handler(CommandHandler("recent", cmd_recent))

    log.info("Dahlia Lab 봇 시작")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
