#!/bin/bash
# がくこま記憶バックアップスクリプト
# memory_processor.py の直後に実行される（run_memory_maintenance.sh 経由）。
# rcloneの失敗を集約し、1つでも失敗なら exit 1（systemdでfailed可視化）。

MEMORY_DIR="/home/tukapontas/gakukoma/memory"
FACE_DIR="/home/tukapontas/gakukoma/camera/face_data"
REMOTE="gdrive:gakukoma_backup"
LOG="/home/tukapontas/gakukoma/memory/backup.log"
# 削除・上書き分の世代退避先（リモート側trash）。日付ごとに分ける。
TRASH="$REMOTE/trash/$(date +%Y%m%d)"

# --- ログローテーション: 512KB超なら最新200行に切り詰め ---
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 524288 ]; then
    tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup.log をローテーション（最新200行に切り詰め）" >> "$LOG"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] バックアップ開始" >> "$LOG"

failed=0

# wiki（長期記憶）をバックアップ（削除・上書き分は trash へ世代退避＝非破壊化）
rclone sync "$MEMORY_DIR/wiki" "$REMOTE/wiki" --backup-dir "$TRASH/wiki" --log-file="$LOG" --log-level INFO
if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wiki バックアップ完了" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wiki バックアップ失敗" >> "$LOG"
    failed=1
fi

# 顔認識モデルをバックアップ（同様に trash へ世代退避）
rclone sync "$FACE_DIR" "$REMOTE/face_data" --backup-dir "$TRASH/face_data" --log-file="$LOG" --log-level INFO
if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] face_data バックアップ完了" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] face_data バックアップ失敗" >> "$LOG"
    failed=1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] バックアップ終了" >> "$LOG"

if [ "$failed" -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 1つ以上のバックアップが失敗しました（exit 1）" >> "$LOG"
    exit 1
fi
exit 0
