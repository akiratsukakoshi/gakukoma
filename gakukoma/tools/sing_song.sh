#!/bin/bash
# 使用方法: sing_song.sh '<notes_json>' [tempo]
# 例: sing_song.sh '[{"freq":261.6,"duration":0.5}]' 1.0

NOTES="${1:-[]}"
TEMPO="${2:-1.0}"
python3 /home/tukapontas/gakukoma/tools/sing_song.py "$NOTES" "$TEMPO"
