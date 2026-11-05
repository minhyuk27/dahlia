#!/usr/bin/env bash
set -euo pipefail

SITE_DIR="$HOME/dahlia/site"
DEPLOY_KEY="$HOME/.ssh/dahlia_deploy"
MICRO_USER="ubuntu"
MICRO_HOST="134.185.115.158"
REMOTE_PATH="/var/www/dahlia/public"

cd "$SITE_DIR"
hugo --minify --cleanDestinationDir

rsync -avz --delete \
  -e "ssh -i $DEPLOY_KEY -o StrictHostKeyChecking=accept-new" \
  public/ \
  "$MICRO_USER@$MICRO_HOST:$REMOTE_PATH/"

echo "[deploy] 완료: $(date '+%Y-%m-%d %H:%M:%S')"
