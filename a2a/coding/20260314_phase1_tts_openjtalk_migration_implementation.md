# 実装指示書：TTS移行 — Piper → Open JTalk（meiモデル）

発行日: 2026-03-14
担当: Antigravity
フェーズ: Phase 1

---

## 背景・変更理由

Piper TTS の日本語モデルは「落ち着いた女性声」が中心であり、がくこまのコンセプト（タチコマ風・子供らしい機敏な声）を実現できる声質モデルが存在しない。またONNX推論のレイテンシ（約1秒）がクラウドLLMの待ち時間に累積し、対話体験として許容範囲を超えると判断。

**Geminiリサーチ結果に基づき、TTSエンジンを Open JTalk（meiモデル）に変更する。**

- 推定レイテンシ: 50〜100ms未満（Pi5環境）
- 声質: HMM合成のロボット感がタチコマの世界観に合致
- パラメータチューニングにより「子供らしい・元気な声」を実現可能

---

## タスク一覧

### タスク1: Open JTalk のインストール

```bash
sudo apt update
sudo apt install -y open-jtalk open-jtalk-mecab-naist-jdic
```

インストール後、以下で動作確認：

```bash
open_jtalk --version
```

---

### タスク2: meiモデルのダウンロード

モデルを `~/voice_app/tts/models/` に配置する。

```bash
mkdir -p ~/voice_app/tts/models/
cd ~/voice_app/tts/models/

# MMDAgent-EX リポジトリからmeiモデルを取得
wget -O mei_happy.htsvoice "https://raw.githubusercontent.com/mmdagent-ex/MEI/main/mei_happy.htsvoice"
wget -O mei_normal.htsvoice "https://raw.githubusercontent.com/mmdagent-ex/MEI/main/mei_normal.htsvoice"
```

**注意**: 上記URLは一例。ダウンロードに失敗する場合は以下を試す：
- `apt search htsvoice` で apt経由のパッケージを確認
- `apt install mmdagent` または `hts-voice-nitech-jp-atr503-m001` パッケージの存在を確認
- 取得できた場合は `/usr/share/hts-voice/` 以下からコピー

**最低限 `mei_happy.htsvoice` が1つあれば動作可能。** 配置後に以下でテスト：

```bash
echo "こんにちは、学長！がくこま、準備完了です！" | open_jtalk \
  -m ~/voice_app/tts/models/mei_happy.htsvoice \
  -x /var/lib/mecab/dic/open-jtalk/naist-jdic \
  -ow /tmp/test_tts.wav \
  -fm 2.0 -jf 1.3 -r 1.1 && aplay /tmp/test_tts.wav
```

音が出れば成功。

---

### タスク3: config.yaml の更新

`~/voice_app/config.yaml` の `tts` セクションを以下のように書き換える。

**変更前（Piper設定）:**
```yaml
tts:
  engine: piper
  model: tts/models/en_US-lessac-medium.onnx
  # （その他Piper設定）
```

**変更後（Open JTalk設定）:**
```yaml
tts:
  engine: openjtalk
  model: tts/models/mei_happy.htsvoice
  dic: /var/lib/mecab/dic/open-jtalk/naist-jdic
  # タチコマ声質チューニングパラメータ
  speed: 1.1        # 話速（1.0が標準）
  pitch: 2.0        # 声の高さ（fm: 2.0〜2.5で子供らしい声）
  intonation: 1.3   # 抑揚の幅（jf: 1.3〜1.5で感情豊かに）
  output_wav: /tmp/gakukoma_tts_output.wav
```

---

### タスク4: speak_text.py の書き直し

`~/voice_app/tts/speak_text.py` を Open JTalk を subprocess で呼び出す実装に完全書き換えする。

**実装仕様:**
- クラス名: `OpenJTalkTTS`（既存の Piper クラスは削除）
- `speak(text: str)` メソッド: テキストを受け取り、open_jtalk コマンドで WAV生成 → aplay で再生
- config.yaml から `tts.model`, `tts.dic`, `tts.speed`, `tts.pitch`, `tts.intonation`, `tts.output_wav` を読み込む
- テキストが空文字の場合はスキップ
- subprocess の終了コードを確認し、失敗時はエラーログを出力（例外で落とさない）

**逐次再生対応（重要）:**
- `voice_loop.py` からは「文単位」でこのモジュールが呼ばれる想定
- 1回の `speak()` 呼び出しが完了してから次が来る設計のため、同期実行で問題なし

**Piperの依存関係の削除:**
- `speak_text.py` 内の `import piper`, `from piper import ...` 等の参照を全て削除

---

### タスク5: voice_loop.py の確認・修正

`~/voice_app/voice_loop.py` が `speak_text.py` の新クラス `OpenJTalkTTS` を正しくインポートして動作するか確認する。

- クラス名やメソッド名のインターフェースが変わった場合は `voice_loop.py` 側を合わせて修正する
- **LLM応答の逐次発話（文単位での `speak()` 呼び出し）** が実装されていない場合は追加する
  - LLMの応答テキストを句読点（`。！？`）で分割し、各文を順次 `speak()` に渡すことでレスポンス体感を改善できる

---

### タスク6: Piper関連パッケージのアンインストール（任意）

以下は任意対応。容量節約のため推奨：

```bash
pip3 uninstall piper-tts piper-phonemize --break-system-packages
# onnxモデルファイルも不要なら削除
rm -f ~/voice_app/tts/models/en_US-lessac-medium.onnx
rm -f ~/voice_app/tts/models/en_US-lessac-medium.onnx.json
```

---

## 統合テスト

| # | テストシナリオ | 合格基準 |
|---|---|---|
| T-1 | `speak_text.py` 単体実行（日本語テキスト） | meiの声でスピーカーから音が出る |
| T-2 | `voice_loop.py` 起動時の挨拶発話 | 日本語で「がくこま、起動しました」等が聞こえる |
| T-3 | Push-to-Talkで日本語発話→LLM→TTS | 日本語で返答が読み上げられる |
| T-4 | 長文応答の逐次発話（実施した場合） | 文ごとに区切られて自然に読み上げられる |

---

## 完了報告書の作成

全テスト合格後、以下の情報を含む完了報告書を `coding/20260314_phase1_tts_openjtalk_migration_completed.md` に作成してください：

- インストールしたパッケージ・バージョン
- 使用したhtsvoiceモデルのパスと入手先
- config.yaml の最終的なttsセクション内容
- 各テスト結果
- 実測レイテンシ（T-1でのopen_jtalk実行時間）
- 気づいた問題・次のアクションへの申し送り
