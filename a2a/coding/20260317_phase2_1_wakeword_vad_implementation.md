# 指示書：Phase 2.1 Wakeword + VAD 実装

作成日: 2026-03-17
作成者: ClaudeCode（司令塔）
担当: Antigravity
完了報告先: `/home/tukapontas/a2a/coding/20260317_phase2_1_wakeword_vad_completed.md`

---

## 概要

現在の `voice_loop.py` は Enterキー操作が必要なPush-to-Talk方式。
これを **完全ハンズフリー** に改造する。

| 改善 | 内容 |
|---|---|
| Wakeword | 「ガクコマ起動」でアクティブ化、「おやすみ」で待機に戻る |
| VAD | 発話終了を自動検知（無音1.5秒でSTTへ渡す） |

---

## 環境情報

- 作業ファイル: `/home/tukapontas/gakukoma/voice_loop/voice_loop.py`
- 設定ファイル: `/home/tukapontas/gakukoma/voice_loop/config.yaml`
- マイクデバイス: `hw:3,0`（config.yamlの `audio.record_device`）
- Python: `python3`（/usr/bin/python3）
- pip: `pip3`

---

## タスク1：パッケージインストール

```bash
pip3 install webrtcvad sounddevice
```

インストール後、`import webrtcvad`・`import sounddevice` が通ることを確認する。
`faster-whisper` はすでにインストール済みのため追加不要。

---

## タスク2：Wakeword実装方針

**`faster-whisper tiny` ループ方式を採用する（方針決定済み、選択不要）。**

### 仕組み

```
音量監視（ほぼ0% CPU）
    └─ 一定音量以上を検知 → 2秒録音
        └─ Whisper tiny で推論（Pi5で約1〜2秒）
            └─ 結果に「ガクコマ」かつ「起動」が含まれるか判定
```

### CPUの特性

- **無音時**: ほぼ0%（音量監視のみ）
- **推論時**: 一時的にスパイク（1〜2秒で終わる）
- **平均**: 普段使いで5〜10%程度

### Whisperによる「ガクコマ」認識について

既存の `initial_prompt="がくこま、ガクコマ、学コマ"` により、tiny モデルでも「ガクコマ」を正しく認識できる。

wakeword検出用の tiny モデルは起動時に別途ロードする（smallモデルとは独立）:

```python
wakeword_model = WhisperModel("tiny", device="cpu", compute_type="int8")
```

### wakeword判定ロジック

```python
def is_wakeword(text: str) -> bool:
    return ("ガクコマ" in text or "がくこま" in text or "学コマ" in text) and \
           ("起動" in text or "きどう" in text)
```

### スリープワード判定ロジック

```python
def is_sleepword(text: str) -> bool:
    return "おやすみ" in text or "お休み" in text
```

---

## タスク3：`config.yaml` への設定追記

`/home/tukapontas/gakukoma/voice_loop/config.yaml` に以下のセクションを追記する:

```yaml
# ウェイクワード設定（Phase 2.1追加）
wakeword:
  enabled: true              # falseにするとEnterキーモードに戻せる
  chunk_duration: 2.0        # wakeword検出用の録音チャンク長（秒）
  volume_threshold: 500      # この音量以上で録音を開始（無音スキップ用）

# VAD設定（Phase 2.1追加）
vad:
  enabled: true              # falseにするとEnterキーモードに戻せる
  silence_threshold: 1.5     # 無音継続でSTT渡しとみなす秒数
  aggressiveness: 2          # webrtcvad感度（0〜3、2が標準）
  min_speech_duration: 0.5   # これ以下は無音として無視（誤検出防止）
```

---

## タスク4：`voice_loop.py` の書き換え

### 動作フロー（実装仕様）

```
起動
  ├─ Whisper tiny モデルロード（wakeword検出用）
  ├─ Whisper small モデルロード（会話STT用）
  ├─ 「がくこまが起動しました」発話
  └─ [待機モード: idle]
       └─ sounddeviceで音量監視
           └─ 音量閾値超え → 2秒録音 → tiny で推論
               └─ 「ガクコマ起動」検出 → [アクティブモード: active]
                   ├─ 「はい、なんでしょう」発話
                   ├─ VAD録音開始（sounddevice + webrtcvad）
                   │    └─ 発話開始検知 → 録音
                   │    └─ 無音1.5秒 → 録音終了
                   ├─ Whisper small でSTT → OpenClaw LLM → TTS
                   ├─ 応答完了後 → VAD録音待機に戻る（activeのまま）
                   └─ STT結果に「おやすみ」検出
                        └─ 「おやすみなさい」発話 → [待機モード: idle]
```

### 状態管理

```python
mode = "idle"  # または "active"
```

- `idle`中: tiny モデルによるwakeword検出ループのみ実行
- `active`中: wakeword検出ループを停止（誤検出防止）
- `active`中のSTT結果に「おやすみ」が含まれていたら待機に戻る

### sounddevice を使ったVAD録音

`arecord` による録音をやめ、`sounddevice` + `webrtcvad` に統一する。

```python
import sounddevice as sd
import webrtcvad
import numpy as np

# webrtcvadはframe sizeが10/20/30msのどれかである必要がある
# sample_rate=16000, frame_duration=30ms → 480サンプル/フレーム
```

録音フロー:
1. `sd.InputStream` でマイクから16kHz, mono, int16 で読み込む
2. `webrtcvad` でフレームごとに音声/無音を判定
3. 音声が始まったら `recording=True` にして蓄積
4. 無音が `silence_threshold` 秒以上続いたら録音終了
5. 蓄積した音声をWAVファイルに書いてWhisper small に渡す

`min_speech_duration` 秒未満の音声は無視する（誤検出防止）。

---

## タスク5：後方互換フラグの確認

`config.yaml` の `wakeword.enabled = false` かつ `vad.enabled = false` の場合、
従来のEnterキー方式で動作することを確認する（フォールバックテスト）。

---

## テスト項目

完了報告書に全テスト結果を記載すること。

| # | テスト | 合格条件 |
|---|---|---|
| T-1 | 待機モードのCPU消費 | idle状態（無音時）でCPU使用率10%以下 |
| T-2 | 「ガクコマ起動」検出 | wakewordに反応し「はい、なんでしょう」と発話する |
| T-3 | アクティブモード会話 | 発話→VAD終了検知→STT→LLM→TTS が動作する |
| T-4 | 「おやすみ」で待機復帰 | active中に「おやすみ」と言うと待機に戻る |
| T-5 | VAD録音終了 | 無音1.5秒でSTTに渡される |
| T-6 | 誤検出なし | 短い咳・雑音（0.5秒未満）で録音が開始されない |
| T-7 | フォールバック動作 | enabled=falseでEnterキー方式に戻せる |

---

## 完了報告書に含めること

- T-1〜T-7の全テスト結果
- CPU消費の実測値（idle無音時・wakeword検出時・active会話時）
- 問題点・工夫した点

---

## 申し送り

- `voice_loop.py` の `subprocess.Popen(arecord ...)` による録音部分を `sounddevice` に置き換えること
- 既存のOpenClaw呼び出し部分（`openclaw agent --message`）はそのまま維持する
- `WhisperModel("small", ...)` の初期化は起動時1回のみ（変更なし）
- tiny モデルのキャッシュは `~/.cache/huggingface/hub/` にダウンロードされる（初回のみ通信が必要）
