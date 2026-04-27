#!/usr/bin/env python3
"""
sing_song.py: 音符列を受け取ってsin波で演奏する。演奏中は首を左右に振る。

使用方法:
  python3 sing_song.py '<notes_json>' [tempo]
  例: python3 sing_song.py '[{"freq":261.6,"duration":0.5}]' 1.0
"""

import sys
import json

# 必須ライブラリのインポートチェック
try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    print("sounddeviceまたはnumpyが利用できない")
    sys.exit(1)

SAMPLE_RATE = 44100
FADE_SAMPLES = int(SAMPLE_RATE * 0.005)  # 5ms フェードイン/アウト

# 首振りパターン: left → right → left → right ...
PAN_SEQUENCE = [130, 50, 130, 50]
# 累積時間がこの閾値を超えたら首を動かす（ビート感を出す）
BEAT_THRESHOLD = 0.3  # 秒


def make_wave(freq: float, duration: float) -> "np.ndarray":
    """指定周波数・長さのsin波を生成する（エンベロープつき）"""
    n = int(SAMPLE_RATE * duration)
    if n == 0:
        return np.zeros(1, dtype=np.float32)

    if freq <= 0:
        return np.zeros(n, dtype=np.float32)

    t = np.linspace(0, duration, n, endpoint=False)
    wave = 0.5 * np.sin(2 * np.pi * freq * t).astype(np.float32)

    # エンベロープ（クリックノイズ防止）: 先頭・末尾5msをフェードイン/アウト
    fade = min(FADE_SAMPLES, n // 2)
    if fade > 0:
        ramp = np.linspace(0, 1, fade, dtype=np.float32)
        wave[:fade] *= ramp
        wave[-fade:] *= ramp[::-1]

    return wave


def init_head():
    """PanTiltControllerを初期化して返す。失敗時はNone。"""
    try:
        sys.path.insert(0, '/home/tukapontas/gakukoma')
        from servo.pan_tilt import PanTiltController
        return PanTiltController()
    except Exception as e:
        print(f"[sing_song] 首振り初期化失敗（音だけ再生）: {e}", file=sys.stderr)
        return None


def move_head(ctrl, beat_idx: int):
    """ビートインデックスに応じて首を動かす。"""
    if ctrl is None:
        return
    pan = PAN_SEQUENCE[beat_idx % len(PAN_SEQUENCE)]
    try:
        ctrl.set_pan(pan)
    except Exception:
        pass


def play_notes(notes: list, tempo: float, ctrl):
    """音符リストをリズムに合わせて再生し、首を連動して動かす。"""
    total_notes = len(notes)
    total_duration = 0.0
    beat_idx = 0
    accumulated = 0.0

    for note in notes:
        freq = float(note.get("freq", 0))
        duration = float(note.get("duration", 0.25)) / tempo
        total_duration += duration

        # BEAT_THRESHOLD を超えたら首を動かす
        accumulated += duration
        if accumulated >= BEAT_THRESHOLD:
            move_head(ctrl, beat_idx)
            beat_idx += 1
            accumulated = 0.0

        wave = make_wave(freq, duration)
        sd.play(wave, samplerate=SAMPLE_RATE)
        sd.wait()

    return total_notes, total_duration


def main():
    # 引数パース
    notes_json = sys.argv[1] if len(sys.argv) > 1 else "[]"
    tempo_str = sys.argv[2] if len(sys.argv) > 2 else "1.0"

    try:
        notes = json.loads(notes_json)
    except json.JSONDecodeError:
        print("notes JSONが不正")
        sys.exit(1)

    try:
        tempo = float(tempo_str)
        if tempo <= 0:
            tempo = 1.0
    except ValueError:
        tempo = 1.0

    if not notes:
        print("演奏完了（0音符, 0.0秒）")
        return

    # 演奏前にサーボを初期化（スレッドを使わず直接制御）
    ctrl = init_head()

    try:
        total_notes, total_duration = play_notes(notes, tempo, ctrl)
    finally:
        # 演奏終了後に正面へ戻す
        if ctrl is not None:
            try:
                ctrl.look_center()
            except Exception:
                pass

    print(f"演奏完了（{total_notes}音符, {total_duration:.1f}秒）")


if __name__ == "__main__":
    main()
