# Phase 2.1 アクションプラン：UX向上（Voice & Neck）

作成日: 2026-03-17
作成者: ClaudeCode（司令塔）
対象フェーズ: Phase 2.1（Phase 3着手前のUX改善スプリント）

---

## 1. フェーズ目標

Phase 1（音声）・Phase 2（カメラ・首振り）の完成を踏まえ、
**「もっと自然に・もっと自由に」** を実現する3つの改善を行う。

| # | 改善内容 | 動機 |
|---|---|---|
| A | Wakeword対応 | EnterキーなしでGAKUKOMAを呼び起こせるようにする |
| B | VAD自動発話終了検知 | Enterキーなしで発話終了を自動検知する |
| C | 首振り方向指示ツール | がくこまが「右を見る」「上を向く」を自在に行えるようにする |

---

## 2. 各改善の詳細要件

### A. Wakeword（ウェイクワード）

**ユーザー要件**:
- 「がくこま、起きて」でGAKUKOMAが音声モードに入る
- 「がくこま、おやすみ」でGAKUKOMAが音声モードを終了する
- 待機中は静かにしている（音声出力・LLM呼び出しをしない）

**技術選定: Openwakeword**

| 項目 | 内容 |
|---|---|
| ライブラリ | `openwakeword` |
| CPU消費 | 常時約2〜5%（Raspberry Pi 5で実用範囲内） |
| メモリ消費 | 約30〜50MB |
| aarch64対応 | ✅ |
| カスタムwakeword | ✅（学習不要のモデルフリー方式で近似語も検出可） |
| インストール | `pip3 install openwakeword` |

**動作フロー**:
```
[待機モード]
  └─ sounddeviceでマイク常時監視（低CPU）
      └─ "がくこま" 検出 → [アクティブモード]
          ├─ 「はい、なんでしょう」とTTS発話
          ├─ VAD録音 → STT → LLM → TTS（通常会話ループ）
          └─ "おやすみ" 検出 → 「おやすみなさい」と発話 → [待機モード]
```

**状態管理**:
- 状態変数: `mode = "idle" | "active"`
- `idle`中はwakeword検出のみ実行（Whisperは呼び出さない）
- `active`中はwakeword検出を一時停止（誤検出防止）

**カスタムwakeword「がくこま」について**:
- Openwakewordの組み込みモデル（英語）では「がくこま」は検出不可
- **段階実装推奨**:
  1. まず英語のwakeword（"hey jarvis" 等）で動作確認
  2. 問題なければ、日本語wakewordとして近い発音（"hey computer" 等）で代替
  3. 余裕があればカスタムモデル作成（音声サンプル録音→学習→統合）
- 代替案：Wakeword部分のみ`faster-whisper tiny`で「がくこま」を検出する軽量ループ
  - メリット：日本語「がくこま」を正確に認識可能
  - デメリット：`tiny`でもCPU10〜20%程度（`openwakeword`より重い）
  - **実装時にAntigravityが状況に応じて選択すること**

---

### B. VAD自動発話終了検知

**ユーザー要件**:
- 話し終わったら自動でSTTに渡される（Enterキー不要）
- 不自然な沈黙にならない（短い間は録音継続する）

**技術選定: webrtcvad + sounddevice**

| 項目 | 内容 |
|---|---|
| ライブラリ | `webrtcvad`（Google WebRTC由来・軽量VAD） |
| CPU消費 | ほぼ無視できるレベル |
| aarch64対応 | ✅ |
| インストール | `pip3 install webrtcvad` |

**録音フロー**:
```
話し始め検知（音量閾値）
    └─ 録音開始
        └─ 無音1.5秒継続 → 録音終了
            └─ Whisper STTへ渡す
```

**パラメータ（config.yamlに追記）**:
```yaml
vad:
  silence_threshold: 1.5   # 無音継続でSTT渡しとみなす秒数
  aggressiveness: 2         # webrtcvad感度（0〜3、2が標準）
  min_speech_duration: 0.5  # これ以下は無音として無視（誤検出防止）
```

**後方互換性**:
- `voice_loop.py`の`input("Enterキーで録音開始...")`をVAD方式に置き換える
- 実装後もEnterキー方式にフォールバックできるよう`config.yaml`にフラグを設ける

---

### C. 首振り方向指示ツール

**ユーザー要件**:
- 「右を向く」「上を見る」「正面を向く」などの指示でがくこまが首を動かせる
- LLMが状況に応じて自由にカメラの向きを変えられる
- `look_at_user()`（顔追跡）とは独立したツールとして動く

**追加ツール設計**:

#### `look_direction(direction: str)` ツール

| 引数 `direction` | パン角度 | チルト角度 | 意味 |
|---|---|---|---|
| `"front"` / `"center"` | 90° | 90° | 正面・中央 |
| `"right"` | 45° | 90° | 右 |
| `"left"` | 135° | 90° | 左 |
| `"up"` | 90° | 60° | 上（チルト最小） |
| `"down"` | 90° | 120° | 下（チルト最大） |
| `"upper-right"` | 45° | 60° | 右上 |
| `"upper-left"` | 135° | 60° | 左上 |

- 方向名は日本語でも受け付けるよう、LLMに自然言語→direction変換を委ねる
  （TOOLS.mdの説明文で「"right"または"みぎ"」のように記載）

#### `set_pan_tilt(pan: float, tilt: float)` ツール

- 絶対角度でパン・チルトを指定
- パン: 0〜180°、チルト: 60〜120°（範囲外はクランプ）
- がくこまが「細かく首を動かしたい」場合のための精密制御用

**ファイル構成**:
```
~/gakukoma/
  look_direction.py        # look_direction()本体
  tools/
    look_direction.sh       # OpenClaw用ラッパー
    set_pan_tilt.sh         # OpenClaw用ラッパー（set_pan_tilt()を呼ぶ）
```

**pan_tilt.pyへの追記**（既存ファイルを拡張）:
- `look_direction(direction: str)` メソッドを追加（方向文字列→角度変換）
- `set_pan_tilt(pan, tilt)` メソッドを追加（直接角度指定）

**OpenClaw統合**:
- `TOOLS.md` に `look_direction` / `set_pan_tilt` ツール定義を追記
- `SOUL.md` の能力欄に「自発的な視線移動が可能」を追記

---

## 3. タスク分解と依存関係

```
[Antigravity] Task A: Wakeword実装      ─┐
[Antigravity] Task B: VAD実装           ─┤→ voice_loop.py統合テスト
[Antigravity] Task C: 首振り方向指示ツール ─┘
```

3タスクはすべて独立して着手可能。
統合テストはAntigravityが全タスク完了後に実施。

---

## 4. 指示書ファイル計画

| ファイル名 | 格納先 | 担当 |
|---|---|---|
| `20260317_phase2_1_wakeword_vad_implementation.md` | `coding/` | Antigravity |
| `20260317_phase2_1_look_direction_implementation.md` | `coding/` | Antigravity |

WakewordとVADは密接に関連する（どちらも`voice_loop.py`の書き換えを伴う）ため、1つの指示書にまとめる。
首振り方向ツールは独立した指示書とする。

---

## 5. テスト計画

| # | テスト | 合格条件 |
|---|---|---|
| T-1 | Wakeword待機動作 | idle状態でCPU使用率が10%以下であること |
| T-2 | 「起きて」検知 | wakewordに反応し「はい、なんでしょう」と発話すること |
| T-3 | 「おやすみ」検知 | active中に「おやすみ」を発話すると終了メッセージを発し待機に戻ること |
| T-4 | VAD録音開始 | 発話を始めると自動的に録音が始まること |
| T-5 | VAD録音終了 | 1.5秒の無音でSTTに渡されること |
| T-6 | 誤検出なし | 短い咳・雑音で録音が始まらないこと |
| T-7 | look_direction単体 | 各方向（front/right/left/up/down）でサーボが正しく動くこと |
| T-8 | set_pan_tilt単体 | 指定角度にサーボが移動すること |
| T-9 | OpenClaw統合（首振り） | 「右を向いて」の発話でlook_directionが呼ばれサーボが動くこと |
| T-10 | 全体統合 | Wakeword → VAD会話 → 首振り指示が1セッション内で動作すること |

---

## 6. リスクと対策

| リスク | 対策 |
|---|---|
| 「がくこま」wakewordが認識されない | `tiny` Whisperループへフォールバック。または「ねえ、がくこま」など音節数を増やす |
| VAD誤検出（背景ノイズで録音開始） | `aggressiveness=3`（最高感度）に変更。マイクの設置場所見直し |
| Wakeword+VAD常時起動でCPU高騰 | idle中はwakewordのみ（Whisperは停止）。問題あれば`tiny`モデルに変更 |
| 首振りが`look_at_user()`と競合 | `look_at_user()`呼び出し中は`look_direction()`を無視するロック機構を追加 |
| サーボの物理限界角度超え | pan_tilt.pyのクランプ処理を必ず通す（既存実装に追加） |

---

## 7. Phase 2.1 完了条件

- [ ] Wakeword（待機→アクティブ→待機）が動作する
- [ ] VADで発話終了が自動検知されSTTに渡される
- [ ] Enterキー不要でエンドツーエンドの会話ができる
- [ ] `look_direction()` がOpenClaw経由で呼び出せる
- [ ] `set_pan_tilt()` がOpenClaw経由で呼び出せる
- [ ] T-1〜T-10の全テストに合格する
- [ ] TOOLS.md / SOUL.mdが更新されている
- [ ] Antigravityが完了報告書を提出済み

---

## 8. 申し送り事項（Phase 2からの引き継ぎ）

- `voice_loop.py` は `~/gakukoma/voice_loop/voice_loop.py`
- `config.yaml` は `~/gakukoma/voice_loop/config.yaml`（新設定は全てここに追記）
- マイクデバイス: `hw:3,0`（config.yamlの`audio.record_device`）
- `pan_tilt.py` は `~/gakukoma/servo/pan_tilt.py`（既存実装を拡張すること）
- サーボ回転方向補正: `pan_gain=-0.1`・`tilt_gain=0.1`（`look_at_user()`で確認済み）
- OpenClaw TOOLS.md: `~/.openclaw/workspace/TOOLS.md`
- OpenClaw SOUL.md: `~/.openclaw/workspace/SOUL.md`
