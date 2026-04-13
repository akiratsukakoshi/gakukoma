# TTSエンジン選定の変更および日本語モデル調査報告書

## 調査結果の要約
当初検討していた Piper TTS についても調査を行いましたが、日本語モデルのバリエーション（特に子供らしい声）が不足していること、およびクラウドLLMとの組み合わせにおけるトータルレイテンシを考慮し、**「Open JTalk」へのエンジン切り替えを決定**しました。

「がくこま」のコンセプトである「タチコマ風のキャラクター性」を実現するため、Open JTalk の `mei` モデルを採用し、パラメータチューニングによって最適化します。

---

## 1. Piper 日本語モデルの調査（参考）
- **入手先:** Hugging Face `rhasspy/piper-voices` 内の `ja_JP` ディレクトリ。
- **モデル種類:** `kanae (medium)`, `misaki (medium)`, `nanami (medium)` 等が存在。
- **断念理由:** - 落ち着いた女性の声が中心であり、タチコマのような「子供らしい/元気な」声のモデルが標準で存在しない。
    - ONNX推論のラグ（約1秒）が、クラウドLLMの待ち時間と累積すると、ロボットの反応として許容範囲を超える懸念がある。

## 2. 推奨モデル（決定）
- **エンジン:** Open JTalk
- **音声モデル:** `MMDAgent htsvoice "mei"` (特に `mei_happy` または `mei_normal`)
- **品質ランク:** HMM方式（軽量・高速）
- **推定レイテンシ（Pi5）:** 50ms 〜 100ms 未満（ほぼ即時）

## 3. セットアップ・ダウンロード手順

### 実行エンジンのインストール
```bash
sudo apt update
sudo apt install -y open-jtalk open-jtalk-mecab-naist-jdic

### モデルファイルの取得
`~/voice_app/tts/models/` に配置します。

```bash
# ディレクトリ作成
mkdir -p ~/voice_app/tts/models/
cd ~/voice_app/tts/models/

# meiモデルのダウンロード（MMDAgentリポジトリより）
wget [https://github.com/mmdagent/MMDAgent/raw/master/Release/AppData/Voice/mei/mei_happy.htsvoice](https://github.com/mmdagent/MMDAgent/raw/master/Release/AppData/Voice/mei/mei_happy.htsvoice)
wget [https://github.com/mmdagent/MMDAgent/raw/master/Release/AppData/Voice/mei/mei_normal.htsvoice](https://github.com/mmdagent/MMDAgent/raw/master/Release/AppData/Voice/mei/mei_normal.htsvoice)

## 4. チューニング設定（タチコマ化）
以下のパラメータを open_jtalk コマンド実行時に付与することで、キャラクター性を演出します。

* **声の高さ (-fm):** 2.0 〜 2.5（標準より高く、子供らしい声へ）
* **抑揚の幅 (-jf):** 1.3 〜 1.5（感情表現を豊かに）
* **話速 (-r):** 1.1 （少し早口にすることで、AIの機敏さを演出）

**テスト用実行コマンド:**
echo "こんにちは、学長！がくこま、準備完了です！" | open_jtalk \
-m ~/voice_app/tts/models/mei_happy.htsvoice \
-x /var/lib/mecab/dic/open-jtalk/naist-jdic \
-ow output.wav \
-fm 2.0 -jf 1.3 -r 1.1 && aplay output.wav

---

## 5. 注意事項・既知の問題
* **音質:** Piper（ニューラル系）に比べると、やや機械的な質感になります。しかし、「ロボットであるタチコマ」のモチーフとしては、この質感が逆にポジティブな要素として機能すると判断しました。
* **逐次再生:** LLMのストリーミング出力を文単位で区切り、順次 open_jtalk に渡して再生することで、対話のレスポンス速度を最大化してください。

---

## 6. ClaudeCode・Antigravity への申し送り事項
* **ライブラリの変更:** Piper 関連の依存関係を削除し、subprocess 等を利用して open_jtalk コマンドを呼び出すクラスを実装してください。
* **Config:** config.yaml の tts.engine を openjtalk に変更し、fm, jf, r などのパラメータを外部から調整可能にしてください。
* **ディレクトリ構成:** モデルファイルは ~/voice_app/tts/models/ 以下を参照するようにパスを固定してください。