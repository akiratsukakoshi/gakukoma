#!/bin/bash
# 引数なしで呼ばれた場合: 5秒録音してSTT結果を返す
TMPFILE=/tmp/gakukoma_tool_input.wav
DEVICE=$(grep 'device:' /home/tukapontas/gakukoma/voice_loop/config.yaml | awk '{print $2}' | tr -d '"')
arecord -D "$DEVICE" -f S16_LE -r 16000 -c 1 "$TMPFILE" -d 5
python3 /home/tukapontas/gakukoma/stt/listen_voice.py "$TMPFILE"
rm -f "$TMPFILE"
