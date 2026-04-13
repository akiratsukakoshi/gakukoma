# Plan 2.2 実装指示書：ツール定義改善 + 音声品質向上 + look_center追加

**依頼者**: ClaudeCode
**担当**: Antigravity
**日付**: 2026-03-18
**関連フェーズ**: Phase 2.1 完了後の品質改善スプリント（Phase 2.2）

---

## 背景・目的

がくこまとの実際のやり取りを通じて以下の課題が発覚しました。

1. **ツール選択の混乱**: 「上を向いて！」と言ってもスムーズにlook_directionを選択できない。TOOLS.mdに「いつ使うか」が書かれていないため、AIがツールの使い分けを判断できない。
2. **正面復帰コマンドがない**: 方向を向いたまま戻れない。
3. **音声モードの知能低下**: STT誤認識によるインプット品質低下 + 毎回新規セッションで会話履歴なし → Discordチャンネルと同じHaiku 4.5なのにパフォーマンスが大幅に劣る。

---

## タスク一覧

### タスクB-1: TOOLS.md 改修（使用シーン追加）

ファイル: `/home/tukapontas/.openclaw/workspace/TOOLS.md`

**Servo Direction Toolsセクション全体を以下に置き換える:**

```markdown
## GAKUKOMA Servo Direction Tools（Phase 2.1追加）

### ツール使い分けルール

| 状況 | 使うツール |
|---|---|
| ユーザーが方向を指示（「上を向いて」「右を見て」等） | `look_direction` |
| ユーザーの顔・体の方向に自動で向く | `look_at_user` |
| 正確な角度で向きたい（精密制御） | `set_pan_tilt` |
| 正面・中央に戻る | `look_center` |

**優先順位**: 方向の言葉があれば必ず`look_direction`を使う。「見て」「向いて」はすべて首の制御を伴う。

### look_direction
- コマンド: `/home/tukapontas/gakukoma/tools/look_direction.sh "<方向>"`
- 機能: 指定した方向にカメラ（首）を向ける
- **使用シーン**: ユーザーが「右を向いて」「上を見て」「左！」など方向を指示したとき
- 引数: 方向文字列（下記いずれか）
  - `front` または `center`（正面・中央）
  - `right`（右）、`left`（左）
  - `up`（上）、`down`（下）
  - `upper-right`（右上）、`upper-left`（左上）
  - `lower-right`（右下）、`lower-left`（左下）
  - 日本語でも可: `右`、`左`、`上`、`下`、`正面`、`右上`、`左上` 等
- 戻り値: `look_direction成功: pan=X° tilt=Y°` または エラーメッセージ
- 備考: `look_at_user` 実行中は競合を避けるためブロックされる

### look_center
- コマンド: `/home/tukapontas/gakukoma/tools/look_center.sh`
- 機能: カメラ（首）を正面（pan=90° tilt=90°）に戻す
- **使用シーン**: 方向指示アクションの後、正面に戻るとき。「正面向いて」「元に戻って」「こっち向いて」
- 引数: なし
- 戻り値: `look_center成功: pan=90° tilt=90°`

### set_pan_tilt
- コマンド: `/home/tukapontas/gakukoma/tools/set_pan_tilt.sh <pan角度> <tilt角度>`
- 機能: パン・チルトを絶対角度で指定する（精密制御用）
- **使用シーン**: 「60度右に向けて」など数値指定がある場合のみ使用。通常はlook_directionを優先。
- 引数: パン角度（0〜180）、チルト角度（60〜120）
- 戻り値: `set_pan_tilt成功: pan=X° tilt=Y°`
- 備考: 範囲外の値は自動でクランプされる

### look_at_user
- コマンド: `/home/tukapontas/gakukoma/tools/look_at_user.sh`
- 機能: Webカメラで顔を検出し、パン・チルトサーボを制御してカメラをユーザーの顔に向ける
- **使用シーン**: 「僕の顔を見て」「私を見て」「こっち向いて（顔追跡で）」
- 引数: なし
- 戻り値: 「顔追跡成功: pan=X° tilt=Y°」または「タイムアウト: 顔が見つかりませんでした」
- 備考: 実行には PCA9685（I2C 0x40）が接続されている必要がある
```

---

### タスクB-2: SOUL.md 能力記載の整理

ファイル: `/home/tukapontas/.openclaw/workspace/SOUL.md`

**`### 能力（現在: Phase 2）` セクションを以下に置き換える:**

```markdown
### 能力（現在: Phase 2）
- 音声で会話する
- 質問に答える、雑談する
- 周囲を見て説明する
- 首を動かして方向を向く・正面に戻る
- ユーザーの顔を自動追跡する

詳細なツールの使い方・使い分けは `TOOLS.md` を参照。
```

---

### タスクB-3: SKILLS.md 新規作成

ファイル: `/home/tukapontas/.openclaw/workspace/SKILLS.md`

以下の内容でファイルを新規作成してください:

```markdown
# SKILLS.md - がくこまの行動スキル定義

## このファイルの目的

よく使う行動パターン（複数ツールの組み合わせ）をシナリオとして定義する。
「何をするとき、何をどの順番で使うか」のレシピ集。

---

## スキル一覧

### スキル1: 方向を向いて見る（look_and_see）

**トリガー**: 「〇〇を向いて」「〇〇を見て」「〇〇の方向は？」「〇〇を撮って」

**フロー**:
1. `look_direction` で指定方向に首を向ける
2. （ユーザーが「見て」「撮って」「何がある？」と言った場合）`see_around` で撮影・説明
3. アクション完了後、**`look_center` で正面に戻る**

**例**:
- 「ガクコマ、上を向いて！」→ look_direction(上) → look_center
- 「ガクコマ、右を向いて何が見える？」→ look_direction(右) → see_around → look_center
- 「ガクコマ、左上を撮って！」→ look_direction(左上) → see_around → look_center

**注意**:
- 「見て」「撮って」の言葉がない純粋な方向指示（「上を向いて」）はsee_aroundなしでOK
- 正面に戻らなくていいとユーザーが言った場合はlook_centerをスキップ

---

### スキル2: 正面に戻る（return_to_center）

**トリガー**: 「正面向いて」「元に戻って」「こっち向いて（顔追跡なし）」「真ん中」

**フロー**:
1. `look_center` を実行

---

### スキル3: ユーザーを追う（track_user）

**トリガー**: 「僕（私）の顔を見て」「こっちを見て（顔追跡で）」「私を見てて」

**フロー**:
1. `look_at_user` を実行（顔検出して自動追跡）
2. 顔が見つからなければ「顔が見つかりませんでした」と報告

**注意**:
- look_at_userは顔検出ベース。方向指示（「上を向いて」等）とは別物。
- 顔が見つかっても追跡後は元の位置に戻さない（ユーザーを見続ける意図があるため）

---

### スキル4: 周囲を観察する（observe_surroundings）

**トリガー**: 「何が見える？」「周りを見て」「写真を撮って」「観察して」

**フロー**:
1. `see_around` を実行（現在の首の向きで撮影）
2. 結果を日本語で報告（簡潔に）

---

## ツール選択の判断フロー

```
ユーザーの発言
    │
    ├─ 方向の言葉がある（上/下/左/右/右上 etc.）？
    │       → look_direction → [see_around if 撮影要求] → look_center
    │
    ├─ 「僕・私を見て」「顔を見て」？
    │       → look_at_user
    │
    ├─ 「正面」「元に戻る」「こっち向いて」（方向なし）？
    │       → look_center
    │
    ├─ 「何が見える？」「見て」「観察」？
    │       → see_around
    │
    └─ 数値角度が指定されている？
            → set_pan_tilt
```

---

### タスクA-2（先行実施分）: look_center ツール追加

`look_direction`・`set_pan_tilt` と同様のパターンで、正面復帰コマンドを追加してください。

#### 1. `pan_tilt.py` に `look_center()` メソッドを追加

ファイル: `/home/tukapontas/gakukoma/servo/pan_tilt.py`

`look_direction()` の後に以下を追加:

```python
def look_center(self) -> str:
    if not self._lock.acquire(blocking=False):
        return "look_center失敗: 他の操作が実行中です"
    try:
        self.set_pan(90)
        self.set_tilt(90)
        self.release()
        return "look_center成功: pan=90° tilt=90°"
    finally:
        self._lock.release()
```

#### 2. `look_center.sh` シェルスクリプト作成

ファイル: `/home/tukapontas/gakukoma/tools/look_center.sh`

既存の `look_direction.sh` を参考に、引数なしで `look_center()` を呼ぶスクリプトを作成してください。

#### 3. TOOLS.md への記載（タスクB-1で対応済み）

---

### タスクC-1: STT認識改善

ファイル: `/home/tukapontas/gakukoma/voice_loop/voice_loop.py`

#### 変更1: `initial_prompt` の改善

現在:
```python
initial_prompt="がくこま、ガクコマ、学コマ",
```

変更後:
```python
initial_prompt="がくこま、ガクコマ、学コマ、ロボット、カメラ、右、左、上、下、正面、向いて、見て、ありがとう、おやすみ",
```

理由: 一般的な日本語会話フレーズをヒントとして追加することで、固有名詞以外の認識精度も向上する。

#### 変更2: ハルシネーションフィルタの緩和

現在:
```python
if seg.avg_logprob < -1.0:
    continue
```

変更後:
```python
if seg.avg_logprob < -1.5:
    continue
```

理由: `-1.0` は厳しすぎて正当な発話が切り捨てられている可能性がある。`-1.5` に緩和して認識漏れを減らす。

---

### タスクC-2: 音声モードの会話履歴維持（セッション継続）

**背景**: 現在の `call_openclaw()` は毎回新規セッションで呼び出すため、会話の文脈がリセットされる。Discordチャンネルは継続セッションで会話履歴が保たれるため、同じHaiku 4.5モデルでも品質に差が生まれている。

ファイル: `/home/tukapontas/gakukoma/voice_loop/voice_loop.py`

#### 変更方針

`VoiceLoop` クラスに `session_id` を保持し、2回目以降の `call_openclaw()` でセッションを引き継ぐ。

**実装調査が必要な事項:**

openclaw CLI の `agent` コマンドが `--session <session_id>` オプションをサポートしているか確認してください:
```bash
openclaw agent --help
```

対応している場合:
1. `VoiceLoop.__init__()` に `self.session_id = None` を追加
2. `call_openclaw()` で初回は `--session` なしで実行し、レスポンスJSONから `session_id` を取得
3. 2回目以降は `--session self.session_id` を付けて実行

**注意事項:**
- `mode="idle"`（ウェイクワード待機）に戻ったときはセッションをリセット（`self.session_id = None`）する。新しい会話セッションとして扱う。
- セッションIDの取得方法はレスポンスJSONの構造を確認して実装してください。

---

## テスト要件

| ID | テスト内容 | 合格条件 |
|---|---|---|
| T-1 | 「上を向いて」→ look_direction実行 | pan=90 tilt=60 になる |
| T-2 | 「右を向いて何が見える？」→ look_direction → see_around → look_center | 3ツールが順番に実行される |
| T-3 | 「正面向いて」→ look_center実行 | pan=90 tilt=90 になる |
| T-4 | look_center.sh 単体実行 | 正面復帰成功メッセージ |
| T-5 | 「がくこまどこにいる？」（一般日本語）→ Whisperが正確に認識 | 誤認識率が従来より改善 |
| T-6 | 2回連続で会話 → 2回目で文脈を引き継いでいる | セッションIDが再利用される |
| T-7 | SKILLS.mdがワークスペースに存在する | ファイル確認 |

---

## 完了報告

完了報告書は `/home/tukapontas/a2a/coding/20260318_plan22_tools_voice_completed.md` に作成してください。

報告書に含めてほしい内容:
1. 各タスクの実施結果
2. セッション継続（C-2）のCLI調査結果と実装内容
3. テスト結果（T-1〜T-7）
4. 未実施事項（あれば理由）

---

## 備考: パンチルト診断結果待ちの事項

以下は **Geminiの診断結果受領後に別途指示します**。今回は対応不要:
- `config.yaml` の `tilt_min` / `tilt_max` 調整（実機診断値を反映）
- 左向き（left）のI2C不安定問題への対処
