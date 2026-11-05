#!/usr/bin/env bash
# Dahlia Lab 새벽 자동 발행 (cron: 0 18 * * * = 새벽 3시 KST)
# 하루 2개 생성
set -euo pipefail

DAHLIA="$HOME/dahlia"
DAILY_LIMIT=2
mkdir -p "$DAHLIA/logs"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# 큐 보충 (항상 50개 유지)
log "큐 보충 확인 중..."
python3 "$DAHLIA/scripts/queue_refill.py"

# DAILY_LIMIT개 순서대로 생성
for i in $(seq 1 $DAILY_LIMIT); do
  NEXT=$(sqlite3 "$DAHLIA/data/ledger.db" \
    "SELECT id,product,category,compare_with FROM queue
     WHERE status='pending'
     ORDER BY priority ASC, release_date DESC, id ASC
     LIMIT 1;" 2>/dev/null || true)

  if [ -z "$NEXT" ]; then
    log "큐가 비어있습니다. 종료."
    break
  fi

  IFS='|' read -r QID PRODUCT CATEGORY COMPARE <<< "$NEXT"
  log "[$i/$DAILY_LIMIT] 생성 시작: $PRODUCT ($CATEGORY)"

  if python3 "$DAHLIA/scripts/generate.py" \
      --product "$PRODUCT" \
      --category "$CATEGORY" \
      ${COMPARE:+--compare "$COMPARE"}; then
    log "[$i/$DAILY_LIMIT] 완료: $PRODUCT"
  else
    log "[$i/$DAILY_LIMIT] 실패: $PRODUCT"
    sqlite3 "$DAHLIA/data/ledger.db" \
      "UPDATE queue SET status='failed' WHERE id=$QID;"
  fi

  # 모델 레이트 리밋 방지
  [ "$i" -lt "$DAILY_LIMIT" ] && sleep 10
done

# 전체 빌드·배포 (1번에 몰아서)
log "빌드·배포 시작..."
"$DAHLIA/scripts/deploy.sh"
log "완료"
