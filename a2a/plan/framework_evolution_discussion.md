# GAKUKOMAフレームワーク進化検討 — チーム議論ドキュメント

> **作成日**: 2026-04-10
> **ファシリテーター**: ClaudeCode（司令塔）
> **目的**: フィジカルAI特化フレームワークへの進化方針を議論・合意し、Phase 2.5（フレームワーク刷新スプリント）のキックオフに向けた設計基盤を作る

---

## 1. 議論参加者・役割

| エージェント | 役割 | 主な視点 |
|---|---|---|
| **ClaudeCode（ファシリテーター）** | 司令塔・進行・合意形成 | 全体最適・プロジェクト進行 |
| **エージェントB** | レイテンシー・トークンコスト専門 | コンパクト化・高速化 |
| **エージェントC** | 身体機能専門 | 身体性の保持・拡大 |
| **エージェントD** | 記憶・対話専門 | キャラクターの安定化 |
| **エージェントE** | 既存フレームワーク保持派 | リスク回避・段階的改善 |

---

## 2. 現状整理（ファシリテーターによる事前確認）

議論開始前に、ファシリテーターが以下のファイルを実際に確認した：

- `/home/tukapontas/a2a/progress.md` — 開発進捗
- `/home/tukapontas/.openclaw/openclaw.json` — OpenClaw設定
- `/home/tukapontas/.openclaw/workspace/AGENTS.md`, `SOUL.md`, `TOOLS.md` — エージェント設定
- `/home/tukapontas/gakukoma/voice_loop/voice_loop.py` — メインループ実装

### 現在のアーキテクチャ（図解）

```
ユーザー発話
    │
    ▼ webrtcvad + Whisper tiny（ウェイクワード「おはよう」）
    │
    ▼ Whisper small（STT: 1〜2秒）
    │
    ▼ voice_loop.py（4ステートマシン: idle/listening/thinking/speaking）
    │
    ▼ subprocess呼び出し: "openclaw agent --json" （300〜500msオーバーヘッド）
    │
    ▼ OpenClaw（セッション管理・プロンプトキャッシュ・ツール呼び出し）
    │   ├─ system: AGENTS.md + SOUL.md + TOOLS.md + memory/YYYY-MM-DD.md
    │   └─ user: few-shot priming（初回）+ ローカル履歴（最大5ターン）+ 発話テキスト
    │
    ▼ Claude Haiku (claude-haiku-4-5-20251001) 1〜2秒
    │
    ▼ ツール実行（シェルスクリプト経由）
    │   ├─ speak_text.sh / see_around.sh
    │   └─ look_direction.sh / look_at_user.sh / set_pan_tilt.sh
    │
    ▼ Open JTalk TTS（76ms）
    │
    ▼ スピーカー再生
```

### 現状の主要指標

| 指標 | 現在値 | 備考 |
|---|---|---|
| Turn 1 input tokens | 30,105 | 初期88,000から66%削減済み |
| LLMレイテンシ | 1〜2秒 | キャッシュヒット時 |
| 全体レイテンシ | 5〜7秒 | see_aroundなし |
| see_around実行 | 4〜6秒 | Vision API |
| TTS | 76ms | Open JTalk |
| STT（Whisper small） | 1〜2秒 | CPU推論 |

---

## 3. 各エージェントの分析と主張

### 3-B. エージェントB（レイテンシー・コスト専門）

#### 現状の問題点

**トークンコスト**
- Turn 1 input: 30,105トークンは依然として多い
- 内訳: SOUL.md 約210トークン、TOOLS.md 約180トークン、AGENTS.md 約200トークン、memory 1,000〜2,000トークン、few-shot priming 約300トークン、ローカル履歴 1,000〜2,000トークン
- ただしこれらは現在プロンプトキャッシュが効いており、2ターン目以降はcache_readで1/10コスト

**構造的な非効率性**

1. **OpenClawの「汎用性の重み」**: `openclaw agent --json` をsubprocessで起動するたびにバイナリのスピンアップが発生。推定300〜500msのオーバーヘッド
2. **セッション間キャッシュの非効率**: ウェイクワード検出のたびに新UUID生成 → TTL 5分のキャッシュが有効期限内でも活かされないケースがある
3. **ツール呼び出しの「重さ」**: `look_at_user()` は顔検出+Vision API+サーボ追跡で4〜6秒。このツールが使われると全体が大幅悪化

#### 推薦アーキテクチャ：「軽量ハイブリッド案」

**OpenClaw廃止。Anthropic API直接呼び出し。**

```python
# 新規実装: llm_agent.py（概念）

class GAKUKOMAAgent:
    def __init__(self, config):
        self.client = anthropic.Anthropic(api_key=config['anthropic_key'])
        self.model = "claude-haiku-4-5-20251001"
        self.system_prompt = self._build_system_prompt(config)  # 固定・キャッシュ対象
        self.session_id = None
        self.local_history = []

    def invoke(self, user_text, memory_context=""):
        # cache_control付きでシステムプロンプトをキャッシュ
        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,  # 短い応答を強制
            system=[{
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"}
            }],
            messages=self._build_messages(user_text, memory_context)
        )
        return response.content[0].text
```

**削減目標**:

| 項目 | 現在 | 目標 | 削減率 |
|---|---|---|---|
| System Prompt（キャッシュ後） | 1,200 | 100-200（cache read） | 90% |
| Memory context | 2,000 | 500（当日分のみ） | 75% |
| **合計Input Tokens/ターン** | **30,105** | **〜12,000** | **60%** |

**レイテンシー目標**:

| 段階 | 現在 | 目標 |
|---|---|---|
| LLM（キャッシュヒット時） | 1〜2秒 | 0.5〜1.0秒 |
| subprocess起動 | 300〜500ms | 0ms（廃止） |
| 全体（ツールなし） | 5〜7秒 | 2.0〜3.5秒 |

#### 具体的アクション提案
- `coding/20260410_phase2_3_lightweight_llm_framework_implementation.md` 作成
- Phase 2.3残タスク（ビジュアル認識改善）と並行実装可能
- Phase 3 Task D開始前に完了を目指す

---

### 3-C. エージェントC（身体機能専門）

#### 守るべき身体機能の本質

がくこまの身体機能の本質は **「LLMが自発的に判断して物理世界に働きかけること」** の3核：

**1. 自律的視覚同期（Agency in Perception）**
- `see_around()` は単なる「画像入力」ではなく、LLMが能動的に「確認したいから見よう」と判断して実行するツール
- SOUL.mdの「君が見たものはすべて君自身の視界だ」という原則 — 一人称的・自発的な知覚
- **失ってはいけない**: LLMが「見た視界」として受け取る仕組み。「与えられた画像解析テキスト」への退化は許されない

**2. 身体位置制御の階層化（Embodied Orientation）**
- 4段階の抽象化レイヤーが現在実装されている:
  - 高レベル: `look_at_user()`（社会的インタラクション）
  - 中レベル: `look_direction(right/left/up/down)`（自然言語理解）
  - 低レベル: `set_pan_tilt(60, 90)`（精密制御）
  - リセット: `look_center()`（正面への復帰）
- **失ってはいけない**: この階層化。全てを低レベルAPIに統一したら会話の自然性が失われる

**3. 身体と音声の協調動作（Multimodal Embodiment）**
- 首振り（パンチルト）と発話がシーケンシャルに組み合わさる
- 「体を動かしてから話す」という順序性
- **失ってはいけない**: LLMが時系列で物理動作を計画できる設計

#### フォーク・新規開発時の身体機能リスク

1. **ツール呼び出しレイテンシの増加リスク**: Phase 3での「走りながら見る・会話する」というリアルタイム協調動作が破綻する可能性
2. **一人称性の喪失リスク**: フレームワーク側が自動翻訳を強制した場合、LLMが「見た」ではなく「説明を受け取った」状態に退化
3. **階層化の喪失リスク**: 全ツールが統一化された場合、社会的インタラクションと機械的制御の区別が消滅

#### Phase 3・4を見据えたツール設計提案

**Phase 3（走行系）**:
```
move_robot(
    direction: "forward" | "backward" | "left" | "right",
    duration: float,
    speed: int,           # 0-255
    concurrent_sensing: bool  # 走行中カメラ有効/無効
) -> {"distance_traveled": m, "obstacles_detected": [...], "heading": deg}
```

戻り値に「実際に走った距離」「検出した障害物」「最終方位」を含めることで、LLMが次の動作を判断できる情報を返す。

**新ツール: `look_around_while_moving()`の新設**
- 走行中の視覚同期用
- バックグラウンドで周囲スキャン・障害物検出を実行
- 走行スレッド + カメラ処理スレッドの分離

**ツール入出力のメタデータ付与提案**:
- `timestamp`: ツール実行時刻
- `latency`: 実行時間
- `confidence`: 認識信頼度
- `embodied_state`: 実行時のサーボ角度（「見た時点での自分の姿勢」）

LLMが「見た時点で自分がどこを向いていたか」を理解可能に。身体位置と視界が切り離されないアーキテクチャ。

#### 「小学校高学年男子の身体性」実装への3提案

1. **「やってみる」という能動性**: ツール定義に`experimental=true`フラグを追加し、自発的な探索行動を可能に
2. **「繰り返し試行」の設計**: move_robot()の戻り値で「障害物あり」なら別方向を試す。試行回数・成功率をLLMが学習
3. **「身体の限界を知る」学習**: エラー情報（衝突検知、モーター過負荷）をツールが詳細に返すことで距離感を習得

#### 新フレームワーク採用時の3点チェック
- Tool Callのレイテンシが現在比で2倍以上でないか？
- ツール結果にメタデータ（タイムスタンプ、実行位置、信頼度）を含められるか？
- 複数ツールの並列実行をサポートしているか？

---

### 3-D. エージェントD（記憶・対話専門）

#### 失ってはいけない記憶・対話の核心

**1. セッション自律リセット機構**
- ウェイクワードで`session_id`を新規生成、ローカル履歴・`is_first_turn`を初期化
- 「おはよう〜おやすみ」の1セッション内は連続的な文脈を持ちながら、セッション跨ぎでは自然にリセット
- **新フレームワーク移行時もこの自動リセット機構は必ず保持**

**2. Few-shot Priming の「会話同意形式」の効果**
- progress.md（2026-03-25）より実証済み: systemプロンプトより「会話中の直接指示（ガクチョがルール提示→がくこまが同意）」の方が効く
- **会話形式primingは守り抜く**

**3. SOUL.mdの「応答の大原則」**
- 「2〜3文以内」「ユーザー発言繰り返し禁止」「定型フレーズ連呼禁止」
- 実装側（voice_loop.py）と理念側が同期していることが重要

**4. ローカル履歴「最新3ターン」方式**
- メモリ効率と文脈連続性のバランス
- 「タチコマ的な短期焦点」を実現

#### 長期記憶設計の改善案

**現在の日次ノート方式の問題点**:
1. 「その場で学んだこと」が自動キャプチャされない
2. セッション終了時の自動サマリー生成機構がない
3. 「2日前のノート」参照指示がない

**改善案**:
1. **セッション終了時に自動サマリー生成**: voice_loop.py終了時に`local_history`から「学んだこと」を自動抽出して`memory/YYYY-MM-DD.md`に追記
2. **「最近3日分」メモの優先読み込み**: AGENTS.mdの指示を「今日・昨日・一昨日」の3ファイルに変更
3. **セマンティック検索はPhase 4以降で検討**: 現フェーズでは不要

#### 「4層防御」によるキャラクター安定化

systemプロンプトが短縮化される場合への対処として、4層構造を明確化：

```
Layer 1: systemプロンプト（最小化・30トークン程度）
  └─ 「一人称は僕・2〜3文・繰り返し禁止・タチコマ的好奇心」

Layer 2: few-shot priming（初回ターンのみ・会話同意形式を死守）
  └─ ガクチョ→ルール確認 / がくこま→同意 の4ターン例

Layer 3: ローカル履歴注入（毎ターン・最新3ターン）
  └─ 「直前の会話」として前後文脈を提供

Layer 4: 日次メモ（セッション跨ぎ記憶）
  └─ memory/YYYY-MM-DD.md（最近3日分）
```

各層は相互補完的。どの層も削除・大幅短縮はできない。

#### マルチモーダル統合への準備

1. **ビジュアル認識結果を文脈型記憶に**: see_around()実行時、その結果をローカル履歴に記録（`(user_request, "★ビジュアル: [説明]", response)` の3要素組）
2. **gesture実行もlocal_historyに記録**: 「右を向いて見てみた」という動作ログがセッション文脈に入ることで後続発話が自然になる
3. **LED self-stateとの連動**: 音声遅延が長くても「考え中」がLEDで可視化されることで不安減少

---

### 3-E. エージェントE（既存フレームワーク保持・改善派）

#### OpenClawの現在の価値と資産

**失いたくないもの**:

1. **プロンプトキャッシュの実績**: `cacheRetention: "short"` + TTL 5分でLLMレイテンシが10秒超→1〜2秒。このキャッシュ機構は実装コストゼロで実現した成果
2. **セッション管理・エラーハンドリングの抽象化**: call_openclaw()が単純に書けるのはOpenClawが内部でセッションID管理・レスポンスパース・エラーリトライを処理しているから
3. **workspace統合（memory管理）**: compaction（safeguard）とcontextPruning（cache-ttl: 5m）によるセッション間メモリ漏れの自動防止
4. **Discord統合**: ロボットの音声出力・ツール実行結果をDiscordにリアルタイム配信。移動中もクラウド経由でユーザーが状態を把握可能

#### フォーク・新規開発のリスク

1. **ローカルLLMのツール呼び出し精度低下リスク**: 現在のHaikuでツール呼び出し精度は90%以上。3Bローカルモデルに置き換えると50%程度に低下するリスク。走行制御・把持動作という重要タスクで不確実性を増やすべきではない
2. **Phase 3・4の統合テスト破壊リスク**: Task E完了した状態で大幅フレームワーク変更を行うと、Task D→F→G→Hの各タスクで動作保証が失われる
3. **リアルタイム走行制御への非対応**: ローカルLLM推論の遅延（8〜17秒/50トークン）では走行中の即座判断ができない
4. **API費用削減の錯覚**: フルローカル化でAPI費用はゼロになるが、Pi5の電力消費大幅増加（UPS HAT電池交換頻度増加）

#### OpenClaw継続前提での最適化ロードマップ

**現在30,000トークンからさらに削減できる箇所**:

| 箇所 | 現在 | 改善案 | 期待削減 |
|---|---|---|---|
| SOUL.md | 3,903B | character vibe説明を1行に統約 | -2,000トークン |
| TOOLS.md | 2,594B | JSON最小化形式に変更 | -1,500トークン |
| AGENTS.md | 1,045B | Red Lines のみに絞る | -500トークン |
| few-shot priming | 固定 | 2ターン目以降の動的化 | -500トークン |
| memory auto-compaction | 手動 | 5KBで自動要約 | -2,000トークン |
| **合計** | **30,000** | → | **19,000（-37%）** |

**subprocessオーバーヘッド削減**:
- OpenClawのdaemon modeを活用（バイナリ常駐）しUnix socket通信
- 期待効果: 300〜500ms → 50〜100ms（-75%）

#### 折衷案：「並行PoC」方式

```
本体: voice_loop.py（OpenClawで運用継続）
並行: 環境変数フラグ USE_LOCAL_LLM=0|1 でA/Bテスト
```

- 本体はOpenClawで安定稼働しつつ、オフピークで並行検証
- 検証結果が良好なら`USE_LOCAL_LLM=1`へ切り替え

#### 推薦ロードマップ

| フェーズ | 期間 | 主な作業 |
|---|---|---|
| Short（今〜2週間） | OpenClaw継続最適化（-3,500トークン） | Antigravity |
| Medium（2〜6週間） | Phase 3完了（Task D〜H） + ログ蓄積 | Antigravity + Gemini |
| Medium（6〜10週間） | Phase 4完了（グリッパー） | Antigravity + Gemini |
| Long（10週間〜） | ローカルLLM並行検証 + ファインチューニング | ClaudeCode + Gemini |

---

## 4. ファシリテーターによるクロス議論

### 論点1: 「今すぐOpenClaw廃止」vs「Phase 4後に検討」（B vs E）

**Bの主張**: subprocessオーバーヘッド300〜500msの廃止で全体レイテンシーを5〜7秒→2〜3.5秒に改善できる。実装規模は500〜800行程度で、Phase 2.3の延長で対応可能。

**Eの反論**: 現在Phase 3のTask D〜Hが残存しており、このタイミングでの大幅変更は走行制御・把持動作という重要タスクの動作保証を失う。ツール呼び出し精度が90%→50%に低下するリスクは許容できない。

**ファシリテーターの所見**:
EがローカルLLM移行を前提としているのに対し、BはAnthropicAPI直接呼び出し（Haikuを継続使用）を提案している。**ツール呼び出し精度の低下リスクはBの提案には存在しない**。Eの主張するリスクの多くはローカルLLM移行に対するものであり、「OpenClaw廃止＋Anthropic API直接呼び出し」という折衷案では解消される。

→ **論点1の暫定整理**: ローカルLLM移行は長期課題。「OpenClaw廃止＋Anthropic API直接呼び出し」は実現可能性が高い。ただしタイミングはPhase 3 Task D開始前（短期）とするか、Phase 3完了後（中期）とするかで依然対立。

### 論点2: 身体機能への影響（C vs B/E）

**Cの主張**: フレームワーク変更時に最も危険なのは、ツール呼び出しがブラックボックス化してLLMが「自分の経験」ではなく「与えられた説明」を受け取る状態になること。透明性・一人称性・階層化を守ること。

**Bの提案との整合性**: Bの「軽量ハイブリッド案」ではツールは現行のシェルスクリプトをそのまま継続使用し、LLMからの呼び出し結果もそのまま返す設計。**Cの要件と矛盾しない**。

**追加提案（C→B）**: ツール戻り値にメタデータ（タイムスタンプ・サーボ角度・信頼度）を付加することで、Phase 3・4の複合動作に備える。これはBの設計に組み込み可能。

→ **論点2の整理**: B・C間に根本的対立なし。設計要件として「ツール透明性・一人称性・階層化維持」をBの実装に組み込む。

### 論点3: 記憶・対話の安定性（D vs B）

**Dの主張**: 4層防御（system/priming/ローカル履歴/日次メモ）が有機的に機能している。特に「会話同意形式のfew-shot priming」と「セッション自律リセット」は死守すべき。

**Bとの整合性**: Bの設計でも`is_first_turn`フラグ・セッションUUID・few-shot primingは維持される設計。DはBの実装に対して「4層構造を明示的に設計書に落とせ」という要件提示として機能する。

**追加提案（D）**: セッション終了時の自動サマリー生成・最近3日分メモ読み込みは現フレームワーク（OpenClaw継続でも新規でも）に実装すべき改善点。

→ **論点3の整理**: D・B間に根本的対立なし。4層防御の明示化をBの設計要件に組み込む。

### 論点4: タイミング問題（E vs B）

**Eの主張**: Phase 3（Task D〜H）が残存している今、フレームワーク変更は危険。

**ファシリテーターの所見**:
- Phase 3 Task D（TB6612FNG配線）は**Gemini担当のハードウェア作業**。この期間、Antigravityはソフトウェア側の実装が可能
- Phase 3 Task G（`move_robot()`ツール実装）はAntigravity担当だが、フレームワーク刷新後の方が実装しやすいとも言える
- **提案**: Task Dと並行して新フレームワークのPoC実装（Antigravity）を行い、Task G実装前に移行を完了する

---

## 5. 最終合意事項（ファシリテーター）

### 5-1. 基本方針の決定

**「OpenClaw廃止＋Anthropic API直接呼び出し」による軽量フレームワーク化を採用する。**

理由：
1. Bのsubprocessオーバーヘッド廃止（300〜500ms削減）効果が明確
2. EのリスクはローカルLLM移行に対するもの。Haiku継続使用ならツール精度低下なし
3. C・Dの要件はいずれも新設計と矛盾しない
4. タイミングはPhase 3 Task D（Gemini担当・ハードウェア作業）と並行での実装が最適

### 5-2. 新フレームワーク「GAKUKOMA Brain」設計要件

4名のエージェントの提言を統合した設計要件：

#### 【必須要件】

**R1 - コンパクト性（B提言）**
- Anthropic API直接呼び出し（subprocessゼロ）
- システムプロンプトキャッシュ（cache_control: ephemeral）活用
- max_tokens=200を上限とし、短い応答を強制
- 目標：Turn 1 input 30,105トークン → 12,000トークン以下

**R2 - 身体機能の完全保持（C提言）**
- 既存ツール（シェルスクリプト）の完全継続
- ツール呼び出し結果はLLMに透明かつ一人称的に提供
- 4段階の抽象化レイヤー（look_at_user / look_direction / set_pan_tilt / look_center）の維持
- ツール戻り値にメタデータ（timestamp, latency, embodied_state）付与（Phase 3対応）

**R3 - 4層記憶・対話構造（D提言）**
- Layer 1: systemプロンプト（最小化・30トークン程度）
- Layer 2: few-shot priming（初回ターンのみ・会話同意形式を死守）
- Layer 3: ローカル履歴（最新3ターン・毎ターン更新）
- Layer 4: 日次メモ（最近3日分・セッション起動時に読み込み）

**R4 - セッション管理（D提言）**
- ウェイクワードで新session_id生成・ローカル履歴リセット
- セッション終了時（「おやすみ」）に自動サマリー生成→memory/YYYY-MM-DD.mdに追記

**R5 - マルチモーダル統合準備（C・D提言）**
- see_around()の実行結果をローカル履歴に記録（ビジュアル文脈の保持）
- gesture実行（look_direction等）もローカル履歴に記録

#### 【Phase 3対応要件】

**R6 - 非同期・並列ツール実行対応（C提言）**
- move_robot()実装時、走行中の並列カメラ処理に対応できる設計
- バックグラウンドスレッドでの走行中視覚同期（look_around_while_moving）

**R7 - ツール戻り値の拡充（C提言）**
```python
# move_robot()の戻り値設計
{
    "distance_traveled": float,     # 実際に走った距離
    "obstacles_detected": [...],    # 検出障害物
    "heading": int,                 # 最終方位
    "embodied_state": {...}         # 実行時の全センサー状態
}
```

#### 【長期課題（Phase 4以降）】

**R8 - ローカルLLM移行の並行検証（E提言）**
- `USE_LOCAL_LLM=0|1` フラグによるA/Bテスト環境
- Phase 4完了時点でセッションログからファインチューニングデータ作成検討

### 5-3. 新フレームワーク「GAKUKOMA Brain」アーキテクチャ図

```
voice_loop.py（変更最小限）
    │
    ├─── STT: Faster-Whisper（現状維持）
    ├─── VAD/Wakeword: webrtcvad + Whisper tiny（現状維持）
    ├─── LED: led_controller.py（現状維持）
    │
    └─── [NEW] gakukoma_brain.py（OpenClaw廃止・新規）
              │
              ├─ session: UUID管理・自動リセット
              ├─ memory: load_daily_notes（最近3日）
              │           auto_summarize_on_sleep（セッション終了時）
              ├─ context: build_message（4層構造）
              │            Layer1: system_prompt（fixed・cacheable）
              │            Layer2: priming（初回のみ・会話同意形式）
              │            Layer3: local_history（最新3ターン）
              │            Layer4: daily_notes（最近3日）
              ├─ llm: anthropic.messages.create（direct API）
              │        cache_control: ephemeral
              │        max_tokens: 200
              └─ tools: ToolsHandler
                         │
                         ├─ speak_text.sh（現状維持）
                         ├─ see_around.sh（現状維持・戻り値をlocal_historyに記録）
                         ├─ look_direction.sh（現状維持）
                         ├─ look_center.sh（現状維持）
                         ├─ look_at_user.sh（現状維持）
                         ├─ set_pan_tilt.sh（現状維持）
                         └─ [Phase 3] move_robot.sh（新規）
```

### 5-4. アクションプラン

#### 短期（Phase 3 Task D並行・〜2週間）

| # | タスク | 担当 | 成果物 |
|---|---|---|---|
| 1 | 新フレームワーク指示書作成 | ClaudeCode | `coding/20260410_gakukoma_brain_implementation.md` |
| 2 | `gakukoma_brain.py` 実装 | Antigravity | - |
| 3 | voice_loop.py の `call_openclaw()` 置き換え | Antigravity | - |
| 4 | 4層記憶構造の実装 | Antigravity | - |
| 5 | セッション自動サマリー実装 | Antigravity | - |
| 6 | 基本動作テスト（T-1〜T-8） | Antigravity | - |

#### 中期（Phase 3 Task G実装時）

| # | タスク | 担当 | 成果物 |
|---|---|---|---|
| 7 | move_robot()ツール実装 | Antigravity | 新フレームワーク前提で設計 |
| 8 | ツール戻り値のメタデータ拡充 | Antigravity | - |
| 9 | 並列ツール実行の検証 | Antigravity | - |

#### 長期（Phase 4完了後）

| # | タスク | 担当 | 成果物 |
|---|---|---|---|
| 10 | ローカルLLM（Ollama/Qwen）PoC | Gemini（リサーチ） | `research/YYYYMMDD_local_llm_evaluation_request.md` |
| 11 | セッションログからファインチューニングデータ作成 | ClaudeCode | - |
| 12 | A/Bテスト環境構築 | Antigravity | `USE_LOCAL_LLM=0|1`フラグ |

---

## 6. 未解決の論点・継続観測事項

1. **OpenClaw廃止後のDiscord統合**: EはDiscord統合の価値を主張。新フレームワークでDiscord統合をどう維持するかは未設計。優先度は低いが別途検討が必要。
2. **see_around()のレイテンシー（4〜6秒）**: フレームワーク刷新では根本解決にならない。Vision API呼び出しの最適化（キャッシュ・条件付き実行）は別タスクで検討。
3. **Whisper small（STT）のレイテンシー（1〜2秒）**: ストリーミングSTTへの移行検討（長期）。
4. **ストリーミング発話**: Bが提案。LLM出力をリアルタイムTTSに渡すことで「最初の音が出るまで」の体感レイテンシーを大幅改善できる可能性。Phase 2.5の追加タスクとして検討。

---

## 7. このドキュメントについて

このドキュメントは2026-04-10のチーム議論の成果物です。
エージェントB・C・D・Eはそれぞれ異なる専門視点から独立した分析を行い、ファシリテーターが統合・合意形成を行いました。

**次のアクション**: ファシリテーターがこの合意内容をもとに
`coding/20260410_gakukoma_brain_implementation.md`（Antigravity向け指示書）を作成します。

> *エージェントチーム実験注記*: 本ドキュメントはClaudeCodeが複数のサブエージェントを並列起動し、各視点の分析を収集・ファシリテーターとして統合した成果物です。各エージェントはコードベースを独立して調査した上で意見を形成しました。
