# Phase 5 アクションプラン：記憶と知性の進化

作成日: 2026-04-18
作成者: ClaudeCode（司令塔）
参照: `research/20260417_brain_evolution_discussion.md`

---

## 1. フェーズ目標

「経験を蓄積し、自ら世界に働きかけるがくこま」の実現。

Phase 1〜3で「話す・見る・動く」身体が完成した。Phase 5では**記憶と知性**を育てる。
具体的には：

- 会話・行動の記憶を3層構造（RAW→エピソード→長期）で管理し、意味ある記憶を蓄積する
- 感情的に重要な体験を「核記憶」として長期保存する（忘却と保存の設計）
- アイドル時に自発的に周囲へ働きかける（Intrinsic Motivation）
- 人の顔を識別し、関係性を記憶する
- 移動した場所を記述・記録し、「来たことがある」と言えるようにする

**制約前提**: Raspberry Pi 5 + Claude Haiku API。レイテンシーとトークンコストを常に意識する。
**設計原則**: ONLINEは軽量（wiki参照のみ）、OFFLINEで重い処理（wiki更新・分析・圧縮）。

---

## 2. サブフェーズ構成

### Phase 5.1：LLM Wiki型記憶システム（最小実装・最優先）

**コンセプト**: 「眠って記憶を整理する脳」を実装する。

現在のフラットな日次ログを3層構造に進化させ、重要な記憶だけが長期残るようにする。
退屈行動も同時に実装し、受動的なシステムから能動的なシステムへ第一歩を踏み出す。

**実装内容**:

| タスク | 内容 | 担当 |
|---|---|---|
| Task A: 3層記憶ディレクトリ設計 | `memory/raw/`・`memory/episodes/`・`memory/wiki/` の構造作成 | Antigravity |
| Task B: セッション後OFFLINE処理 | セッション終了後にHaikuが会話を分析→wikiページ更新するスクリプト実装 | Antigravity |
| Task C: 感情タグ + 核記憶 | 分析時に感情スコア（0-10）付与、スコア8以上を `wiki/core_memories.md` に格納 | Antigravity |
| Task D: 忘却スケジュール | cronでRAWログ7日削除・エピソード30日圧縮を自動実行 | Antigravity |
| Task E: 退屈行動（Intrinsic Motivation基礎版） | アイドル60秒後にランダム視線移動・稀に軽い走行・稀に呟き | Antigravity |
| Task F: 統合テスト | 記憶蓄積・wiki更新・退屈行動の動作確認（実機T-1〜T-8） | Antigravity + ユーザー |

**ディレクトリ設計（参考）**:
```
/home/tukapontas/gakukoma/memory/
├── raw/              # セッションごとの生ログ（7日で削除）
│   └── 2026-04-18_session1.md
├── episodes/         # 週次要約（30日で圧縮→wiki統合）
│   └── 2026-W16.md
└── wiki/             # 長期記憶（恒久保存）
    ├── core_memories.md    # 感情スコア8以上の核記憶
    ├── people/             # 人物ページ
    ├── places/             # 場所ページ
    └── index.md            # wikiインデックス（Haiku参照用）
```

**ONLINE/OFFLINE設計**:
```
ONLINE（会話中）:
  wiki/index.md + 関連ページ数件をコンテキスト注入（read only）
  ← 既存のRAWログ注入から切り替え

OFFLINE（セッション終了後・cron 03:00）:
  raw/本日ログ → Haikuで分析 → wiki/各ページ更新
  古いrawログ削除・episodesの圧縮処理
```

**追加トークンコスト試算**: ONLINE +500〜1,000 tokens/turn（wiki参照分）、OFFLINE 2,000〜5,000 tokens/セッション（分析処理）

---

### Phase 5.2：顔認識 + person-wiki

**コンセプト**: 「誰が来たかを知っている」がくこまにする。

現在の顔「検出」（位置だけ）を顔「識別」（誰か）に昇格させ、人物ページを自動更新する。

**実装内容**:

| タスク | 内容 | 担当 |
|---|---|---|
| Task A: face_recognitionライブラリ導入 | dlib/face_recognition のaarch64インストール確認 | Antigravity |
| Task B: 顔登録フロー実装 | 初回「がくこま、これが〇〇だよ」→顔ベクトル保存の対話フロー | Antigravity |
| Task C: look_at_user()統合 | 顔検出時に識別処理を追加、識別できた場合は名前で呼びかける | Antigravity |
| Task D: person-wiki自動更新 | OFFLINE処理でperson-wikiの「最後に会った日」「最近の話題」等を更新 | Antigravity |
| Task E: 統合テスト | 登録・識別・呼びかけ・wiki更新の動作確認 | Antigravity + ユーザー |

**person-wikiスキーマ（参考）**:
```markdown
# people/ガクチョ.md
- 名前: ガクチョ
- 初めて会った日: 2026-03-11
- 最後に会った日: （自動更新）
- 関係性: 製作者・養親
- 最近の話題: （自動更新）
- 行動パターン: （週次でHaikuが推論・更新）
- 感情記憶: （核記憶から抽出）
```

**注意**: face_recognition（dlib）はaarch64のビルドに時間がかかる場合がある（Pi5で~30分）。事前にインストール確認をTask Aで実施すること。

---

### Phase 5.3：場所記憶 + エンコーダー活用

**コンセプト**: 「ここ来たことある」と言えるがくこまにする。

走行時に場所を自動記述・記録し、トポロジカルな場所マップを構築する。
エンコーダー線（現在未使用）を接続し、移動距離・方向の定量記録も加える。

**実装内容**:

| タスク | 内容 | 担当 |
|---|---|---|
| Task A: エンコーダー配線 | モーターエンコーダー線（黄・白・緑・青）をGPIOに接続 | Gemini |
| Task B: オドメトリ実装 | エンコーダーパルスカウント→移動距離・方向の推定スクリプト | Antigravity |
| Task C: 場所記述スクリプト | move_robot()後に自動でsee_around()→Haikuで場所を200文字描写→保存 | Antigravity |
| Task D: トポロジカルマップ管理 | SQLiteで「場所ノード」と「遷移エッジ（オドメトリ値）」を管理 | Antigravity |
| Task E: wiki/places/自動更新 | OFFLINE処理で場所wikiページを更新、再訪時に「前回ここで〇〇だった」を参照 | Antigravity |
| Task F: 統合テスト | 走行→場所記録→wiki更新→再訪での応答確認 | Antigravity + ユーザー |

**エンコーダー接続メモ（Gemini向け）**:
- YP100タンクシャーシのモーターエンコーダー線: 黄・白（左）、緑・青（右）
- 信号線はGPIOの入力ピンへ接続（3.3V系、プルアップ推奨）
- 具体的なGPIOアサインはTask A指示書で確定させること

---

### Phase 5.4以降（将来ビジョン・着手時期未定）

以下はPhase 5.1〜5.3の運用経験を経てから判断する。

| 機能 | 概要 | 前提条件 |
|---|---|---|
| Navigation Q-learning | 場所マップ上で経路を自律学習、ガクチョのいる場所へ自動移動 | Phase 5.3完了・場所マップ蓄積 |
| 動的PRIMING_EXAMPLES更新 | 週次でユーザー反応の良い応答パターンを抽出・プライミング自動更新 | Phase 5.1の感情スコア蓄積 |
| YOLOv8 nano物体検出 | see_around()に物体検出追加・空間記憶に「赤いコップがある部屋」記録 | Pi5 CPU余裕の確認 |
| REM睡眠模倣 | OFFLINE処理で過去記憶のランダム連想生成・翌朝「昨日ふと思ったんだけど」 | Phase 5.1 wiki蓄積後 |
| 退屈行動の拡張（novelty-seeking） | アイドル発動時にsee_around()で撮影→初めて見るものがあればLLMに聞いて呟く | Phase 5.1安定運用後 |

**将来的なハードウェア追加候補**:
- IMU（MPU-6050, ~$2）: 傾き・加速度・転倒検知
- 距離センサー（HC-SR04, ~$1）: 壁・障害物検知（Q-learning衝突回避に必須）
- 深度カメラ（将来）: 本格SLAM（Pi5との相性要確認）

---

## 3. 着手順序と依存関係

```
Phase 5.1（LLM Wiki + 感情核記憶 + 退屈行動）
    ↓ 3〜4週間運用して記憶蓄積を確認してから
Phase 5.2（顔認識 + person-wiki）
    ↓ 並行可能
Phase 5.3（場所記憶）
    ↑ Task Aのエンコーダー配線はGemini（早めに依頼可）
```

Phase 5.2とPhase 5.3は一部並行可能だが、**Phase 5.1を先に3週間運用**してwikiの設計が実際の使用感に合っているかを確認してから着手することを推奨する（Dr. Mehtaの助言に基づく）。

---

## 4. リスクと対策

| リスク | 対策 |
|---|---|
| OFFLINE処理がセッション開始前に終わらない | cron実行時刻を深夜3時に固定。失敗時のログを残す |
| wiki肥大化でトークン超過 | index.mdは常に最新化・コンテキスト注入はindex.md + 関連ページのみ |
| face_recognitionのdlibがビルド失敗 | aarch64向けwheel提供状況を事前確認。失敗時はOpenCV HOG顔識別で代替 |
| エンコーダーのGPIOアサインが既存と競合 | Phase 5.3指示書作成前にGPIO空きピン確認（Gemini） |
| 退屈行動が誤動作（深夜に勝手に動く等） | 時間帯制限（22:00〜7:00はアイドル行動OFF）をconfig.yamlで設定 |

---

*作成: ClaudeCode, 2026-04-18*
*参照議論: `research/20260417_brain_evolution_discussion.md`*
