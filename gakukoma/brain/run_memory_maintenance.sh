#!/bin/bash
# がくこま記憶メンテナンス統合スクリプト
# systemd (gakukoma-memory.service) から呼ばれる。
#   1. memory_processor.py を実行
#   2. 成功した場合のみ backup_memory.sh を実行
# どちらかが失敗したら非0で終了し、systemd に failed を可視化させる。
# ログは従来どおり memory/processor.log に追記する。

set -u

BRAIN_DIR="/home/tukapontas/gakukoma/brain"
BACKUP_SH="/home/tukapontas/gakukoma/backup_memory.sh"
PROC_LOG="/home/tukapontas/gakukoma/memory/processor.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === メンテナンス開始 ===" >> "$PROC_LOG"

# 1. memory_processor.py 実行（stdout/stderr を processor.log に追記）
python3 "$BRAIN_DIR/memory_processor.py" >> "$PROC_LOG" 2>&1
proc_status=$?
if [ "$proc_status" -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] memory_processor.py 失敗 (exit=$proc_status)。backupは実行しない。" >> "$PROC_LOG"
    exit "$proc_status"
fi
echo "[$(date '+%Y-%m-%d %H:%M:%S')] memory_processor.py 成功" >> "$PROC_LOG"

# 2. 成功時のみ backup_memory.sh 実行
"$BACKUP_SH"
backup_status=$?
if [ "$backup_status" -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] backup_memory.sh 失敗 (exit=$backup_status)" >> "$PROC_LOG"
    exit "$backup_status"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === メンテナンス完了 ===" >> "$PROC_LOG"
exit 0
