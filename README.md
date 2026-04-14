# GAKUKOMA — フィジカルAIロボット

Raspberry Pi 5上で動作する自律会話・自律移動ロボット。
音声対話・視覚認識・パンチルト追跡・タンク走行を統合した「身体を持つAI」。

---

## ハードウェア構成

| パーツ | 詳細 |
|---|---|
| コンピュータ | Raspberry Pi 5（8GB） |
| 電源（脳系統A） | UPS HAT(B) + NCR18650 × 2（5V/5A） |
| 電源（動力系統B） | XL4015 DCDC降圧（11.1V → 6V）+ 1000μFコンデンサ |
| バッテリー | 11.1V Li-ion 3セル |
| マイク | USB単一指向性マイク |
| スピーカー | MAX98357A I2S DAC + 4Ω8Wスピーカー |
| カメラ | EMEET SmartCam C960（USB） |
| サーボドライバ | PCA9685（I2C 0x40） |
| パンチルト | アルミ合金製台座 + DS3218（20kg-cm）× 2 |
| 走行 | YP100タンクシャーシ + TB6612FNG モータードライバ |

---

## ソフトウェアアーキテクチャ

```
voice_loop.py          ← メインループ（音声入出力・ステートマシン）
    │
    ├─ STT: faster-whisper（small / tiny）
    ├─ TTS: Open JTalk（meiモデル・タチコマ声質）
    ├─ Wakeword: 「おはよう」で起動 / 「おやすみ」でスリープ
    ├─ VAD: webrtcvad による自動発話検出
    ├─ LED: RGB LED（idle=青 / listening=緑 / thinking=黄 / speaking=赤）
    ├─ GestureController: パンチルトジェスチャー（thinking/speaking/center）
    │
    └─ GAKUKOMABrain（brain/gakukoma_brain.py）
           │
           └─ Anthropic API（claude-haiku-4-5）直接呼び出し
                  ├─ Tool Use: look_direction / see_around / look_at_user / ...
                  ├─ few-shot priming（セッション初回のみ）
                  ├─ ローカル会話履歴（直近3ターン）
                  └─ 日次メモ読み書き（~/.openclaw/workspace/memory/）
```

---

## GAKUKOMA Brain — 軽量ブレインシステム

### 背景と狙い

初期実装では `voice_loop.py` → `openclaw CLI（subprocess）` → `Claude Haiku` という構成を採っていた。OpenClaw はエージェントフレームワークとして多機能だが、GAKUKOMA の用途では**不要なオーバーヘッドが大きな問題**になっていた。

| 問題 | 旧構成での状況 |
|---|---|
| subprocess起動コスト | 毎ターン300〜500msのオーバーヘッド |
| 入力トークン数 | Turn 1で約30,105トークン（OpenClawのワークスペース全体をLLMに送信） |
| キャラクター制御 | OpenClawの汎用プロンプト構造に乗っているため調整が困難 |
| ツール実行 | システムプロンプト内のテキスト指示に依存（実行されないリスク） |

これを解決するために **`GAKUKOMABrain`** として軽量フレームワークを自作した。

### 設計方針

**1. Anthropic API 直接呼び出し**

OpenClaw を経由せず `anthropic` Python ライブラリを直接使用する。subprocess起動コストをゼロにし、レイテンシを大幅削減。

**2. 必要最小限のシステムプロンプト**

OpenClawのワークスペース全体（AGENTS.md・TOOLS.md・SOUL.md等）をLLMに渡す旧方式から、約200トークンの固定文字列 `SYSTEM_PROMPT` に切り替え。入力トークン数を **30,105 → 約2,300（92%削減）** に圧縮。

**3. Anthropic 公式 Tool Use 形式**

旧方式ではシェルコマンド名をシステムプロンプトに文字列で書いており、LLMがコマンドを「書くだけ」で実際には実行されないリスクがあった。`TOOLS` 定数で公式の `tool_use` 形式を定義することで、LLMが `stop_reason: "tool_use"` を返したときに**確実にシェルスクリプトが実行される**。

```python
# tool_useループ: end_turnが返るまでツール実行を続ける
while True:
    response = client.messages.create(...)
    if response.stop_reason == "tool_use":
        # ツールを実行してmessagesに追記し再呼び出し
        ...
    else:  # end_turn
        return response_text
```

**4. 4層メッセージ構造**

各ターンのユーザーメッセージは以下の4層を重ねて組み立てる:

```
Layer 4: 【最近の記憶】日次メモ（過去3日分）  ← 全ターン付加
Layer 2: few-shot priming会話例             ← 初回ターンのみ
Layer 3: （直前の会話）ローカル履歴 最新3ターン ← 2ターン目以降
Layer 1: ユーザーの発言本文
```

日次メモには前回セッションの会話サマリーが入っており、セッションをまたいだ記憶の継続性を実現している。

**5. セッション管理**

- `new_session()`: ウェイクワード検出時に呼ばれ、会話履歴・フラグをリセット
- `invoke()`: 1ターンの会話を処理し応答を返す
- `end_session()`: 「おやすみ」時に呼ばれ、セッション内容を日次メモに追記

### 実測パフォーマンス（2026-04-14 実機テスト）

| 指標 | 旧構成 | 新構成 | 改善率 |
|---|---|---|---|
| Turn 1 input tokens | 30,105 | ~2,300 | **-92%** |
| subprocess起動コスト | 300〜500ms | 0ms | **-100%** |
| LLMレイテンシ体感 | 1〜2秒 | 大幅改善（体感で明確） | ✅ |
| ユーザー体験 | - | 「かなりよかった」 | ✅ |

---

## ディレクトリ構成

```
gakukoma/
├── brain/
│   └── gakukoma_brain.py      # GAKUKOMABrainクラス（LLMエージェントコア）
├── voice_loop/
│   ├── voice_loop.py          # メインループ（4ステートマシン）
│   └── config.yaml            # 音声・サーボ・VAD設定
├── tools/                     # シェルスクリプト（ツール実行インターフェース）
│   ├── speak_text.sh          # TTS発話
│   ├── see_around.sh          # カメラ撮影 + Vision API
│   ├── survey_room.sh         # 3方向撮影 + Vision API一括送信
│   ├── look_direction.sh      # 首振り（right/left/up/down/front）
│   ├── look_center.sh         # 正面向き
│   ├── look_at_user.sh        # 顔追跡
│   └── set_pan_tilt.sh        # パン・チルト角度直接指定
├── tts/
│   └── speak_text.py          # Open JTalk TTS（meiモデル）
├── stt/
│   └── listen_voice.py        # faster-whisper STT
├── servo/
│   ├── pan_tilt.py            # PCA9685 サーボ制御
│   └── gesture_controller.py  # ジェスチャー（thinking/speaking/center）
├── camera/
│   └── ...                    # OpenCV + Vision API
└── led_controller.py          # RGB LED ステート可視化
```

---

## 起動方法

```bash
cd /home/tukapontas/gakukoma/voice_loop
python3 voice_loop.py
```

- 「おはよう」: アクティブモードに移行
- 「おやすみ」: スリープ復帰

---

## 開発フェーズ

| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase 1 | 音声対話（STT/TTS/Voice Loop） | ✅ 完了 |
| Phase 2 | カメラ・パンチルト追跡 | ✅ 完了 |
| Phase 2.1 | Wakeword / VAD / 首振り方向指示 | ✅ 完了 |
| Phase 2.2 | パンチルト精度向上 | ✅ 完了 |
| Phase 2.3 | レスポンス速度・ビジュアル認識・UX改善 | ✅ 完了 |
| Phase 2.5 | GAKUKOMABrain（軽量フレームワーク刷新） | ✅ 完了 |
| Phase 3 | タンク走行（TB6612FNG配線・move_robot実装） | 🔧 進行中 |
| Phase 4 | グリッパー把持 | ⬜ 未着手 |

---

## ロールバック手順

新フレームワーク（Brain）が動作しない場合:

```bash
# voice_loop.py を旧バージョンに戻す
git checkout <旧コミットハッシュ> -- gakukoma/voice_loop/voice_loop.py

# workspace内部 .git を復元（OpenClaw compaction用）
cd /home/tukapontas/.openclaw/workspace
tar xzf /home/tukapontas/backups/openclaw_workspace_git_20260413.tar.gz

# gakukoma_brain.py は削除するだけでよい
rm -rf /home/tukapontas/gakukoma/brain/
```
