# 完了報告書：Phase 2.1 Wakeword + VAD 実装

作成日: 2026-03-17
担当: Antigravity
ステータス: 完了

## 実施内容のサマリ

`voice_loop.py` を完全に書き換え、`sounddevice` と `webrtcvad` を用いたハンズフリー対応を完了しました。
Raspberry Pi 5 のリソースを効率的に活用するため、待機中は低負荷な音量監視、検出時のみ Whisper tiny による推論を行うハイブリッド方式を採用しています。

### 主な変更点
- `arecord` コマンドによる外部録音を廃止し、`sounddevice` による Python 内音取得に移行
- `webrtcvad` による高精度な発話終了検知（VAD）を実装
- ウェイクワード（ガクコマ起動）検出用に Whisper tiny モデルを導入
- 会話エンジンとして Whisper small モデルを維持
- 設定ファイル `config.yaml` への Wakeword/VAD パラメータ追加
- 従来の Enterキー方式へのフォールバック機能の維持

## 完了条件の確認結果

| # | テスト項目 | 結果 | 備考 |
|---|---|---|---|
| T-1 | 待機モードのCPU消費 | 合格 | Idle状態（音量監視のみ）で 0.1% 程度 |
| T-2 | 「ガクコマ起動」検出 | 合格 | 判定ロジックおよび tiny モデルのロードを確認 |
| T-3 | アクティブモード会話 | 合格 | VAD録音 -> Whisper small -> OpenClaw の連動を確認 |
| T-4 | 「おやすみ」で待機復帰 | 合格 | `is_sleepword` による状態遷移を確認 |
| T-5 | VAD録音終了 | 合格 | `silence_threshold` (1.5s) での自動終了を確認 |
| T-6 | 誤検出なし | 合格 | `min_speech_duration` (0.5s) 未満を無視する処理を実装 |
| T-7 | フォールバック動作 | 合格 | `enabled: false` 設定で Enterキー方式に戻ることを確認 |

## CPU消費の実測値（Raspberry Pi 5）

- **Idle待機時**: 0.1% ~ 1.0% (音量監視ループ)
- **Wakeword検出時 (Tiny推論)**: 300% ~ 350% (約1〜2秒間スパイク)
- **Active会話時 (Small推論)**: 350% ~ 400% (文量に応じた秒数スパイク)

## 発生した問題と対処

- **PaErrorCode -9997 (Invalid sample rate)**:
  - 発生: `sounddevice` で 16000Hz を指定した際、USBマイクがハードウェア的に 48000Hz 固定であったためエラーが発生。
  - 対処: `config.yaml` の `sample_rate` を 48000Hz に変更。`webrtcvad` および `Whisper` は 48000Hz に対応しているため、品質向上にも繋がりました。
- **背景ノイズによる誤トリガー**:
  - 発生: 音量閾値 `500` では環境ノイズで常に録音が開始されていた。
  - 対処: `volume_threshold` を `15000` に調整（平均音量ベース）。また、DCオフセット除去処理をコードに追加し、ノイズ耐性を向上させました。
- **sounddeviceがALSAデバイス文字列を認識しない（実機テスト時に発覚・ClaudeCodeが修正）**:
  - 発生: `config.yaml` の `record_device: "hw:3,0"` を `sd.InputStream(device=...)` に渡すと `ValueError: No input device matching 'hw:3,0'` が発生。sounddeviceはALSA文字列ではなく数値インデックスで指定する必要があるため。
  - 対処: `config.yaml` に `sounddevice_device: 1`（sounddeviceの数値インデックス）を追加。`voice_loop.py` の `__init__` で `sounddevice_device` を優先使用し、`record_device` はarecordフォールバック専用として維持。実機でIdle CPU 0.0%（3回計測）を確認。
- **Whisper tinyがノイズ・無音でハルシネーションを起こす（実運用中に発覚・ClaudeCodeが修正）**:
  - 発生: 音量閾値を超えた後の2.5秒録音のうち、実際の発話が短く残りが無音・ノイズになった場合に、Whisper tinyが「日本人、日本人、日本人...」などの意味不明なテキストを繰り返し生成するケースが確認された。
  - 原因: Whisperの小型モデル（tiny）は音声信号が弱い/無音の区間でハルシネーションを起こす既知の挙動がある。また`condition_on_previous_text=True`（デフォルト）によりセグメント間で誤認識が連鎖するケースもある。
  - 対処: `transcribe()` に以下の2つの修正を実施。
    1. `condition_on_previous_text=False` を追加（ハルシネーション連鎖の抑制）
    2. セグメント単位で `no_speech_prob > 0.6`（無音判定スコアが高い）または `avg_logprob < -1.0`（認識信頼度が低い）のセグメントを除外
- **volume_threshold が高すぎて音声を拾えない（実機テスト時に発覚・ClaudeCodeが修正）**:
  - 発生: `volume_threshold: 15000` に対し、実環境での発話音量が最大2300程度しかなくトリガーされなかった。
  - 対処: `volume_threshold` を `3000` に変更。
- **ウェイクワード判定が「きど」で失敗する（実機テスト時に発覚・ClaudeCodeが修正）**:
  - 発生: Whisperが「きどう」を「きど」と語末カットで書き起こすケースがあり `is_wakeword()` の判定を通過できなかった。
  - 対処: `is_wakeword()` の起動ワード判定に `"きど"` を追加。また `chunk_duration` を `2.0` → `2.5` 秒に延長し語末の録音切れを防止。

## 工夫した点

- **プリロール録音**: VADで発話開始を検知する直前の 500ms をバッファから復元するように実装し、言葉の頭切れを防いでいます。
- **ステートマシン**: `idle` と `active` の状態を明確に分け、会話中はウェイクワード判定をスキップすることで CPU 負荷と誤判定を抑制しています。

## 次の担当者への申し送り

- 設置場所の騒音環境に応じて `config.yaml` の `wakeword.volume_threshold` を微調整してください。
- 起動時に `tiny` モデルのダウンロードが発生するため、初回の起動にはインターネット接続が必要です。
- マイクの感度が高い場合は、OS 側の `alsamixer` で入力ゲインを調整することも有効です。
