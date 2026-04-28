#!/bin/bash
# がくこま記憶バックアップスクリプト
# memory_processor.py の直後にcronで実行される

MEMORY_DIR="/home/tukapontas/gakukoma/memory"
FACE_DIR="/home/tukapontas/gakukoma/camera/face_data"
REMOTE="gdrive:gakukoma_backup"
LOG="/home/tukapontas/gakukoma/memory/backup.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] バックアップ開始" >> "$LOG"

# wiki（長期記憶）をバックアップ
rclone sync "$MEMORY_DIR/wiki" "$REMOTE/wiki" --log-file="$LOG" --log-level INFO
if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wiki バックアップ完了" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wiki バックアップ失敗" >> "$LOG"
fi

# 顔認識モデルをバックアップ
rclone sync "$FACE_DIR" "$REMOTE/face_data" --log-file="$LOG" --log-level INFO
if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] face_data バックアップ完了" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] face_data バックアップ失敗" >> "$LOG"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] バックアップ終了" >> "$LOG"
