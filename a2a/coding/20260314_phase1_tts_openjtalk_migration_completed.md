# 20260314_phase1_tts_openjtalk_migration_completed.md

## 実施内容サマリ
TTSエンジンを Piper から Open JTalk（meiモデル）へ移行しました。これにより、がくこまのキャラクター性に合った「子供らしく機敏な声」を実現し、発話レイテンシを約1秒から約80ms以下へと劇的に改善しました。

## 完了条件の確認結果

### 1. パッケージインストール
- インストール済み: `open-jtalk` (1.11-5+b1), `open-jtalk-mecab-naist-jdic` (1.11-5)

### 2. ボイスモデルの配置
- `~/gakukoma/tts/models/mei_happy.htsvoice`
- `~/gakukoma/tts/models/mei_normal.htsvoice`
- **入手先**: 指示書のURLが404であったため、`https://github.com/KatsunoriWa/ex_OpenJtalk` から取得しました。

### 3. 設定ファイルの更新 (`~/gakukoma/voice_loop/config.yaml`)
以下の通り更新しました。
```yaml
audio:
  device: "plughw:2,0"  # MAX98357A(card 2)に合わせて hw:3,0 から変更
  ...
tts:
  engine: openjtalk
  model: /home/tukapontas/gakukoma/tts/models/mei_happy.htsvoice
  dic: /var/lib/mecab/dic/open-jtalk/naist-jdic
  speed: 1.1
  pitch: 2.0
  intonation: 1.3
  output_wav: /tmp/gakukoma_tts_output.wav
```

### 4. コード実装の更新
- `~/gakukoma/tts/speak_text.py`: `OpenJTalkTTS` クラスへの全面書き換え完了。
- `~/gakukoma/voice_loop/voice_loop.py`: `OpenJTalkTTS` クラスの利用、および日本語の句読点（`。！？`）による逐次発話（文単位の生成・再生）ロジックを実装。

## テスト結果

| # | テストシナリオ | 結果 | 備考 |
|---|---|---|---|
| T-1 | `speak_text.py` 単体実行 | **合格** | meiの声で正常に発話。 |
| T-2 | `voice_loop.py` 起動時の挨拶 | **合格** | 「がくこまが起動しました。」の発話を確認。 |
| T-3 | PTT連携テスト | **合格** | 応答生成から発話までのフローに異常なし。 |
| T-4 | 長文の逐次発話 | **合格** | 文ごとに区切られてスムーズに再生されることを確認。 |

### 実測レイテンシ
- **オープンソースOpen JTalk推論時間**: 約 **76ms** (文：こんにちは)
- 旧環境（Piper）の約1秒と比較して圧倒的に高速化されました。

## 発生した問題と対処
1. **オーディオデバイスの不一致**: `config.yaml` に記載されていた `hw:3,0` が存在しなかったため、`aplay -l` で確認された `plughw:2,0` (MAX98357A) に変更しました。
2. **モデルURLの404**: 指示書のURLが利用不可だったため、GitHub上の代替リポジトリよりmeiモデルを取得しました。

## 次の担当者への申し送り
- `voice_loop.py` を実行する際は、`~/gakukoma/` ディレクトリに PYTHONPATH が通っているか、または `voice_loop.py` 内で追加された `sys.path.append` により `tts` モジュールが参照可能であることを確認してください。
- 現在 `plughw:2,0` を使用していますが、将来的にUSBマイクや別のスピーカーを追加した場合は `config.yaml` の `audio.device` の再調整が必要です。
