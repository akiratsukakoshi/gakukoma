  # GAKUKOMA プロジェクト 運用ルール

  ## 対象エージェント
  - **ClaudeCode**（司令塔・本ドキュメントの管理者）
  - **コーディング担当AI**（コーディング実装担当：Antigravity / Cline+GLM / Codex / Claudeサブエージェント(gakukoma-coder)等。つどユーザーが担当AIを選択）
  - **Gemini**（ハードウェア組み立てサポート担当）

  ---

  ## 1. ディレクトリ構成

  ```
  /home/tukapontas/a2a/
  ├── operation_rules.md      # 本ファイル（運用ルール）
  ├── specification.md        # プロジェクト仕様書
  ├── progress.md             # 全体進捗管理（ClaudeCodeがセッション開始時に必ず確認）
  ├── hardware_lists.md       # ハードウェア買い出しリスト・手配状況（随時更新）
  ├── current_phase.md        # 現在の開発フェーズ
  ├── coding/                 # コーディング担当AI向け指示書・報告書
  ├── hardware/               # Gemini向け指示書・報告書
  └── research/               # Gemini向けリサーチ依頼・完了報告
  ```

  **ディレクトリ割り当て基準：**
  - `coding/`: コーディング担当AIへの実装指示・完了報告（Python/シェルスクリプト等）
  - `hardware/`: Geminiへの組み立て指示・完了報告（配線・部品・物理構成）
  - `research/`: Geminiへの調査・リサーチ依頼・完了報告（モデル選定・部品調査・技術検証等）
  - **コードと配線の両方にまたがる作業は両ディレクトリに指示書を設置する。**
    - 相手の指示書を参照したほうが伝わりやすい場合は、指示書内で相手ファイルのパスを明示して参照させること
    - 例: `hardware/`の指示書に「対応するコード実装については `/home/tukapontas/a2a/coding/YYYYMMDD_xxx_implementation.md` を参照」と記載

  ---

  ## 2. ドキュメント命名規則

  ```
  YYYYMMDD_<内容>_<役割>.md
  ```

  **役割の種類：**
  | 役割サフィックス | 説明 | 作成者 | 格納先 |
  |---|---|---|---|
  | `implementation` | 実装担当への指示書 | ClaudeCode | `coding/` or `hardware/` |
  | `request` | Geminiへのリサーチ依頼書 | ClaudeCode | `research/` |
  | `report` | 調査・検討結果の報告書 | ClaudeCode | 任意 |
  | `completed` | 作業・調査完了報告書 | **担当エージェント自身** | 依頼書と同ディレクトリ |

  **例：**
  - `20260311_voice-stt-setup_implementation.md`（ClaudeCodeが作成・コーディング担当AIへの指示）
  - `20260311_voice-stt-setup_completed.md`（**コーディング担当AIが作成**）
  - `20260311_motor-driver-wiring_implementation.md`（ClaudeCodeが作成・Geminiへの指示）
  - `20260311_motor-driver-wiring_completed.md`（**Geminiが作成**）
  - `20260313_piper-tts-japanese-model_request.md`（ClaudeCodeが作成・Geminiへのリサーチ依頼）
  - `20260313_piper-tts-japanese-model_completed.md`（**Geminiが作成**）

  **同一作業の指示書と完了報告書は、末尾のサフィックス以外は同名にすること。**

  ---

  ## 3. ワークフロー

  ### 3.1 タスク開始時（ClaudeCode）
  1. 仕様書・`current_phase.md`・直近の`_completed.md`を確認して現状把握
  2. 指示書（`_implementation.md`）を作成して該当ディレクトリに設置
    - コード+ハードウェア両方にまたがる場合は両ディレクトリに設置（§1参照）
  3. ユーザーに「指示書を設置しました。コーディング担当AI / Geminiに渡してください」と伝える（どのAIに渡すかはユーザーが決定）

  ### 3.2 実装中（コーディング担当AI / Gemini）
  - 指示書の内容に従い作業を実施
  - 不明点はユーザー経由でClaudeCodeに質問（指示書に記載されていない判断事項は自己判断不可）

  ### 3.3 実装完了時（コーディング担当AI / Gemini）
  - **実装担当エージェント自身が完了報告書（`_completed.md`）を作成する**
    - コーディング担当AIはコーディング完了後に `coding/_completed.md` を作成
    - Geminiはハードウェア作業完了後に `hardware/_completed.md` を作成
  - 完了報告書の内容：実施内容・結果・確認したこと・次の担当者への申し送り事項
  - 完了報告書作成後、ユーザー経由でClaudeCodeに「完了報告書を設置した」と伝える
  - ClaudeCodeが完了報告書の内容を確認し、`progress.md` を更新する
  - ClaudeCodeが次のタスクを検討・提案する

  ### 3.4 リサーチタスク（Gemini）

  モデル選定・部品調査・技術検証など、実装前に調査が必要な場合は以下のフローで行う。

  1. **ClaudeCode** がリサーチ依頼書（`research/YYYYMMDD_<内容>_request.md`）を作成
  2. **ユーザー** がGeminiにファイルを共有
  3. **Gemini** が調査を実施し、完了報告書（`research/YYYYMMDD_<内容>_completed.md`）を作成
  4. **ユーザー** がClaudeCodeに「完了報告書を設置した」と伝える
  5. **ClaudeCode** が完了報告書を確認し、`progress.md` を更新して次のアクションを提案する

  > リサーチ結果は通常、後続の `_implementation.md`（実装指示書）に反映される。

  ---

  ## 4. 指示書の書き方（ClaudeCode）

  指示書は**エージェントが迷わず実装できる**レベルの詳細さを必須とする。

  ### 必須記載事項
  ```markdown
  # [日付] [タスク名] 指示書

  ## 対象エージェント
  コーディング担当AI（担当AIはユーザーが指定） または Gemini

  ## 目的
  このタスクで達成すること（1〜3文）

  ## 前提条件
  - 完了済みの依存タスク
  - 使用するハードウェア/ソフトウェア

  ## 関連指示書（コード+ハードウェア両方にまたがる場合）
  - 対応するXX指示書: `/home/tukapontas/a2a/coding（またはhardware）/YYYYMMDD_xxx_implementation.md`

  ## 実装手順
  1. 具体的なステップ（コマンド・設定値・ピン番号等を明記）
  2. ...

  ## 完了条件
  - 何ができれば完了か（テスト方法を含む）

  ## 完了報告書の記載事項
  - 実施内容のサマリ
  - 完了条件の確認結果
  - 発生した問題と対処
  - 次の担当者への申し送り

  ## 注意事項
  - Raspberry Pi 5 (aarch64) 固有の注意点
  - リソース制約（CPU/メモリ）
  - その他の注意点
  ```

  ---

  ## 5. エージェント別の役割と制約

  ### ClaudeCode（司令塔）
  - **担当**: 調査・計画・指示書作成・全体進捗管理・フェーズ管理
  - **実装**: 原則担わない（ユーザーから個別に依頼された場合のみ）
  - **トークン節約**: 実装コードは指示書に詳細を記述し、コーディング担当AIに委ねる
  - **セッション開始時**: `progress.md` を最初に確認し、現在の開発状況を把握してから動く
  - **進捗更新**: 完了報告書（`_completed.md`）を受領したら `progress.md` を更新する

  ### コーディング担当AI（コーディング実装）
  ※ 担当AIはAntigravity / Cline+GLM / Codex / Claudeサブエージェント等から、つどユーザーが選択する
  - **担当**: `/home/tukapontas/a2a/coding/` の `_implementation.md` を参照して実装
  - **完了報告**: 作業完了後、自身で `coding/_completed.md` を作成する（ClaudeCodeが書くのではなく担当AIが書く）
  - **通信**: ユーザー経由でClaudeCodeに質問・報告
  - **制約**: 指示書に記載のないアーキテクチャ変更は自己判断不可。判断が必要な場合はユーザー経由で確認

  ### Gemini（ハードウェアサポート・リサーチ）
  - **担当①（ハードウェア）**: `/home/tukapontas/a2a/hardware/` の `_implementation.md` を参照してユーザーの組み立てをサポート
  - **担当②（リサーチ）**: `/home/tukapontas/a2a/research/` の `_request.md` を参照して調査を実施
  - **完了報告**: 作業・調査完了後、自身で `_completed.md` を作成する（ハードウェア→`hardware/`、リサーチ→`research/`）
  - **通信**: ユーザー経由でClaudeCodeが依頼書を作成→ユーザーがGeminiに共有
  - **制約**: 電源系統の変更（GND共通接地ルール等）は指示書に明示されたもの以外は変更不可

  ---

  ## 6. フェーズ管理

  現在のフェーズを `/home/tukapontas/a2a/current_phase.md` に記録する。
  フェーズ変更はClaudeCodeが判断し、ユーザーの承認を得て更新する。

  | フェーズ | 内容 | 主担当 |
  |---|---|---|
  | Phase 1 | 脳の覚醒と対話（Brain & Voice） | コーディング担当AI |
  | Phase 2 | 視覚と表情（Eyes & Neck） | コーディング担当AI + Gemini |
  | Phase 3 | 大地への進出（Body & Power） | コーディング担当AI + Gemini |
  | Phase 4 | 物理干渉（Hand） | コーディング担当AI + Gemini |
