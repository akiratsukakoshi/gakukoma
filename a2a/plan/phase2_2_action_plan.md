# Phase 2.2 アクションプラン：フィジカル制御精度向上 + UX品質改善

作成日: 2026-03-18
作成者: ClaudeCode（司令塔）
対象フェーズ: Phase 2.2（Phase 3着手前のUX改善スプリント・第2弾）

---

## 1. フェーズ目標

Phase 2.1（Wakeword / VAD / 首振り方向指示）の完成後、実際のがくこまとのやり取りで
3つのカテゴリの課題が発覚した。Phase 3（走行系）着手前に解消する。

| カテゴリ | 課題の概要 | 優先度 |
|---|---|---|
| A. パンチルト制御精度 | 左向き失敗・上下幅不足・正面復帰コマンドなし | 高 |
| B. ツール定義・AI認知 | AIがツールの使い分けを理解できていない | 高 |
| C. 音声品質 | STT誤認識・会話履歴なしで知能が低く見える | 中 |

---

## 2. 課題詳細と根本原因分析

### A. パンチルト制御

#### A-1. 左向き（left）でI2C初期化失敗が発生

**症状**: `look_direction left` 実行時にPCA9685（I2C 0x40）が見つからないエラー。右向き（right）では比較的安定。

**仮説**:
- pan=135°（left）はpan=45°（right）より大きな角度移動 → 瞬間電流消費が大きく電圧降下の可能性
- 物理配線の接触不良（左向き時の台座物理的な引っ張りによる）
- I2C初期化タイミングの問題（deinit後の再起動耐性）

**方針**: まずGeminiに実機診断を依頼し、原因を特定してから対処を決定する。

#### A-2. 上下の動き幅が少ない

**症状**: `up`・`down` の実際の移動幅がユーザーの期待より小さい。

**根本原因**: `config.yaml` の `tilt_min: 60` / `tilt_max: 120`（60度幅）が実際の機構的限界値より保守的に設定されている可能性。

**方針**: Geminiに実機で段階的に角度を変えてもらい、安全な最大範囲を確認・config更新。

#### A-3. 正面復帰コマンドがない

**症状**: `look_direction right` 等の実行後、首がその方向を向いたまま固定。

**方針**: `look_center` ツールを新設。SKILLS.md のフロー定義で「アクション後に正面復帰」を標準化。

---

### B. ツール定義・AI認知の問題

#### B-1. ツールの使い分けが不明確

**症状**: 「ガクコマ、上を向いて！」に対してスムーズにlook_directionが選択されない。look_at_user / look_direction / set_pan_tilt の使い分けが混乱する。

**根本原因**:
- `TOOLS.md` に「いつ使うか（使用シーン）」が書かれていない。ツールの仕様説明のみ。
- `SOUL.md` の `### 能力` にツール一覧が重複記載されており、どちらを参照すべきか曖昧。
- 複合シナリオ（「上を向いて何が見える？」= look_direction → see_around → look_center）を定義したファイルがない。

**方針**: TOOLS.mdに使用シーン追加 + SOUL.md能力欄の重複削除 + SKILLS.md新設。

---

### C. 音声品質の問題

#### C-1. STT認識精度が低い

**症状**: 一般的な日本語会話でWhisperが誤認識・無認識を起こす。

**根本原因**:
- `initial_prompt` が固有名詞のみ（`"がくこま、ガクコマ、学コマ"`）で一般日本語認識を補助していない
- ハルシネーションフィルタ `avg_logprob < -1.0` が正当な発話を切り捨てている可能性

#### C-2. 音声モードの知能レベルがDiscordより低く見える

**症状**: 同じがくこま（Claude Haiku 4.5）なのに、音声モードの返答品質がDiscordより劣る。

**根本原因（調査確定）**:
- LLMは**同一**（どちらもClaude Haiku 4.5）
- 実際の原因は以下の2つ:
  1. **STT誤認識** → 壊れたテキストがLLMに入力される（C-1と連動）
  2. **毎回新規セッション** → `call_openclaw()` がセッションIDなしで呼ばれるため会話履歴がゼロ。Discordは継続セッションを維持しており、文脈を保持している。

**方針**: initial_prompt改善 + フィルタ閾値緩和 + セッションID保持による会話継続。

---

## 3. タスク構成と依存関係

```
[先行: 並行実施]
Gemini   → Task A-診断: パンチルト実機診断（i2cdetect・tilt限界値確認）
Antigravity → Task B + C + A-先行: ツール定義改善 + 音声改善 + look_center追加

[後続: Gemini診断結果受領後]
Antigravity → Task A-後続: config.yaml調整 + 左向き対処
```

**依存関係**:
- Task B / C / A-先行（look_center）はGemini診断を待たずに実施可能
- Task A-後続（tilt範囲調整・左向き対処）はGemini診断結果が必要

---

## 4. 各タスクの詳細要件

### Task A-診断: パンチルト実機診断（Gemini担当）

**目的**: A-後続の実装方針を決定するための実機データ収集。

| 診断項目 | 手順 | 収集する情報 |
|---|---|---|
| 左向きI2Cエラー再現 | `look_direction left` を5回繰り返す | 成功率・エラーメッセージ・失敗直後のi2cdetect結果 |
| チルト上限確認 | `set_pan_tilt 90 55` → `50` → `45` と段階的に試す | 異音・機構干渉が出ない安全な最小角度 |
| チルト下限確認 | `set_pan_tilt 90 125` → `130` → `135` と段階的に試す | 異音・機構干渉が出ない安全な最大角度 |
| パン限界確認（任意） | pan=0° / pan=180° で干渉確認 | 安全範囲 |

**指示書**: `research/20260318_pantilt_diagnosis_request.md`

---

### Task B-1: TOOLS.md 改修（Antigravity担当）

**変更内容**: Servo Direction Toolsセクション全体を改修。

追加要素:
- **ツール使い分けルール表**（どの状況でどのツールを使うか）
- 各ツールに **「使用シーン」** セクション追加
- `look_center` の定義追加
- `look_at_user` もServo Toolsセクションに統合（現在は別セクション）

---

### Task B-2: SOUL.md 能力記載の整理（Antigravity担当）

**変更内容**: `### 能力（現在: Phase 2）` セクションのツール一覧を削除・圧縮。

変更前:
```markdown
### 能力（現在: Phase 2）
- 音声で会話する（listen_voice / speak_text ツール）
- 質問に答える、雑談する
- 周囲を見て説明する（see_around ツール）
- ユーザーの顔にカメラを向ける（look_at_user ツール）
- 自発的な視線移動が可能（look_direction で右・左・上・下・正面等を向ける）
- 精密な首の向き制御が可能（set_pan_tilt で角度直接指定）
```

変更後:
```markdown
### 能力（現在: Phase 2）
- 音声で会話する
- 質問に答える、雑談する
- 周囲を見て説明する
- 首を動かして方向を向く・正面に戻る
- ユーザーの顔を自動追跡する

詳細なツールの使い方・使い分けは `TOOLS.md` を参照。
```

**理由**: ツール名をSOUL.mdに書くと記載が古くなったとき矛盾が生じる。詳細はTOOLS.mdに一元化。

---

### Task B-3: SKILLS.md 新規作成（Antigravity担当）

ファイル: `/home/tukapontas/.openclaw/workspace/SKILLS.md`

**定義するスキル（複合シナリオ）**:

| スキル名 | トリガー例 | フロー |
|---|---|---|
| look_and_see（方向を向いて見る） | 「上を向いて」「右を見て何がある？」 | look_direction → [see_around] → look_center |
| return_to_center（正面復帰） | 「正面向いて」「元に戻って」 | look_center |
| track_user（顔追跡） | 「僕の顔を見て」「私を見てて」 | look_at_user |
| observe_surroundings（周囲観察） | 「何が見える？」「観察して」 | see_around |

**ツール選択判断フロー**（テキスト形式）:
```
方向の言葉あり（上/下/左/右 etc.）→ look_direction → [see_around] → look_center
「僕・私を見て」「顔を見て」        → look_at_user
「正面」「元に戻る」               → look_center
「何が見える？」「観察」           → see_around
数値角度が指定されている           → set_pan_tilt
```

---

### Task A-先行: look_center ツール追加（Antigravity担当）

Gemini診断を待たず実施可能なパンチルト改修。

**追加ファイル・変更**:

1. `pan_tilt.py` に `look_center()` メソッド追加（pan=90, tilt=90に移動してreleaseする）
2. `tools/look_center.sh` シェルスクリプト新規作成（既存 look_direction.sh と同パターン）
3. TOOLS.md へ look_center の記載追加（Task B-1 に含む）

---

### Task C-1: STT認識改善（Antigravity担当）

ファイル: `voice_loop/voice_loop.py`

| 変更箇所 | 変更前 | 変更後 | 理由 |
|---|---|---|---|
| `initial_prompt` | `"がくこま、ガクコマ、学コマ"` | 一般的な日本語会話フレーズを追加 | Whisperの日本語認識全体を底上げ |
| `avg_logprob` フィルタ | `< -1.0` | `< -1.5` | フィルタが厳しすぎて正当な発話が切れていた |

---

### Task C-2: 音声モードの会話履歴維持（Antigravity担当）

ファイル: `voice_loop/voice_loop.py`

**目的**: 毎回新規セッションを廃止し、音声会話中の文脈を保持する。

**実装方針**:
1. openclaw CLIの `agent` コマンドの `--session` オプション有無を調査（`openclaw agent --help`）
2. 対応している場合、`VoiceLoop` クラスに `self.session_id = None` を追加
3. 初回 `call_openclaw()` でセッションを開始しレスポンスJSONからsession_idを取得
4. 2回目以降は `--session <session_id>` を付けて継続
5. `mode = "idle"` に戻ったタイミングでセッションをリセット（会話の区切り）

---

### Task A-後続: パンチルト設定最適化（Antigravity担当・Gemini診断後）

Gemini診断結果を受けて実施。ClaudeCodeから別途指示書を作成。

**想定内容**:
- `config.yaml` の `tilt_min` / `tilt_max` を診断値に更新
- 左向き（left）I2C失敗への対処（原因次第で対応方針が変わる）
  - 物理接触不良 → Geminiが配線修正
  - 電圧降下 → ソフトウェア的なリトライ実装またはPCA9685への直接電源供給
  - ロック問題 → ロック取得タイムアウト変更

---

## 5. 指示書ファイル計画

| ファイル名 | 格納先 | 担当 | 状態 |
|---|---|---|---|
| `20260318_pantilt_diagnosis_request.md` | `research/` | Gemini | ✅ 作成済み |
| `20260318_plan22_tools_voice_implementation.md` | `coding/` | Antigravity | ✅ 作成済み |
| `20260318_plan22_pantilt_config_implementation.md` | `coding/` | Antigravity | ⬜ Gemini診断後に作成 |

---

## 6. テスト計画

| # | テスト | 担当 | 合格条件 |
|---|---|---|---|
| T-1 | look_center.sh 単体 | Antigravity | pan=90° tilt=90° になる |
| T-2 | 「上を向いて」→ look_direction | Antigravity | pan=90 tilt=（調整後のmin）になる |
| T-3 | 「右を向いて何が見える？」→ 3ツール連携 | Antigravity | look_direction → see_around → look_center が順番に実行される |
| T-4 | 「正面向いて」→ look_center | Antigravity | look_centerが選択される |
| T-5 | STT一般日本語認識 | Antigravity | 誤認識率が変更前より改善 |
| T-6 | 会話継続（2ターン） | Antigravity | 2回目の発話で文脈を引き継いでいる |
| T-7 | SKILLS.mdがワークスペースに存在 | Antigravity | ファイル確認 |
| T-8 | 左向き（left）安定動作 | Gemini診断後 | 5回中5回成功 |
| T-9 | tilt範囲の上下幅確認 | Gemini診断後 | ユーザーが「幅が広がった」と体感できる |

---

## 7. リスクと対策

| リスク | 対策 |
|---|---|
| openclaw CLIに `--session` オプションがない | セッションJSONファイルを直接操作する代替実装を検討。または会話履歴をシステムプロンプトとして毎回付与する方式 |
| Gemini診断でtilt限界が現設定と変わらない | config変更なし・現状維持。別の上下改善策（台座取り付け角度調整）を検討 |
| 左向きI2C失敗がハードウェア起因 | 電源強化（5V外部供給）またはPCA9685を別電源ラインに接続。Phase 3のモーター電源設計と合わせて検討 |
| SKILLS.md追加でトークン消費増加 | SKILLS.mdは簡潔に保つ（1000トークン以内）。性能問題が出たらSOUL.mdに統合して整理 |
| STTフィルタ緩和でハルシネーション増加 | `no_speech_prob > 0.6` のフィルタは維持。`avg_logprob` のみ緩和。悪化した場合は元に戻す |

---

## 8. Phase 2.2 完了条件

**Antigravity担当分**:
- [ ] look_center.sh が動作する
- [ ] SKILLS.md が `/home/tukapontas/.openclaw/workspace/SKILLS.md` に存在する
- [ ] TOOLS.md に使用シーン・使い分けルールが記載されている
- [ ] SOUL.md の能力欄がTOOLS.mdへ誘導する形に更新されている
- [ ] 音声モードで2ターン以上の会話文脈が保持される（またはCLI制約の詳細報告）
- [ ] T-1〜T-7 の全テストに合格する
- [ ] 完了報告書が提出済み

**Gemini担当分**:
- [ ] 診断結果報告書が提出済み（左向き再現率・tilt安全範囲）

**Antigravity担当分（Gemini診断後）**:
- [ ] config.yaml の tilt_min / tilt_max が診断値に更新されている
- [ ] 左向き問題への対処が実施済み（またはハードウェア対処の場合は内容を報告）
- [ ] T-8・T-9 のテストに合格する

---

## 9. 申し送り事項（Phase 2.1からの引き継ぎ）

- `pan_tilt.py`: `~/gakukoma/servo/pan_tilt.py`（既存のlook_direction/set_pan_tiltを拡張）
- `voice_loop.py`: `~/gakukoma/voice_loop/voice_loop.py`
- `config.yaml`: `~/gakukoma/voice_loop/config.yaml`
- OpenClaw workspace: `~/.openclaw/workspace/`
- シェルスクリプト格納先: `~/gakukoma/tools/`
- サーボ排他ロック: `/tmp/gakukoma_servo.lock`（fcntl方式、プロセス終了時に自動解放）
- 現在のtilt設定: `tilt_min: 60`（上）/ `tilt_max: 120`（下）← Gemini診断後に更新予定
- 現在のpan設定: `pan_min: 0` / `pan_max: 180`（right=45°, left=135°, center=90°）
- サーボ回転方向補正: `pan_gain=-0.1`・`tilt_gain=0.1`（look_at_userで確認済み）
- LLMモデル: `anthropic/claude-haiku-4-5-20251001`（変更なし）
