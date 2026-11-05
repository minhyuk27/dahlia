#!/usr/bin/env bash
# 큐에 제품 추가
# 사용법: ./queue_add.sh "제품명" "카테고리" ["비교제품명"]
# 예시:   ./queue_add.sh "LG C4 OLED 65인치" "display" "삼성 QD-OLED S95D"

set -euo pipefail

PRODUCT="${1:-}"
CATEGORY="${2:-}"
COMPARE="${3:-}"

if [ -z "$PRODUCT" ] || [ -z "$CATEGORY" ]; then
  echo "사용법: $0 \"제품명\" \"카테고리\" [\"비교제품\"]"
  echo "카테고리: computer display mobile audio gadget play frame"
  exit 1
fi

DB="$HOME/dahlia/data/ledger.db"

sqlite3 "$DB" "
  INSERT INTO queue (product, category, compare_with)
  VALUES ('$PRODUCT', '$CATEGORY', '$COMPARE');
"

echo "추가됨: $PRODUCT ($CATEGORY)"
sqlite3 "$DB" "SELECT id,product,category,status FROM queue ORDER BY id;"
