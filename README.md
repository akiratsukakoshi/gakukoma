# GAKUKOMA — フィジカルAIロボット

Raspberry Pi 5上で動作する自律会話・自律移動ロボット。
音声対話・視覚認識・パンチルト追跡・タンク走行・**記憶の蓄積と学習**を統合した「身体を持ち、経験を重ねるAI」。

---

## コアコンセプト

がくこまは「話す・見る・動く」身体機能（Phase 1〜3）に加え、**経験を記憶し、自ら世界に働きかける知性**（Phase 5〜）を持つことを目指している。

設計上のこだわりは**非宣言的記憶**。人間が何度も通る場所を無意識に覚えるように、がくこまも日々の行動・会話・場所を蓄積していく。記憶は無限に積み上げるのではなく、脳科学のCLS理論（Complementary Learning Systems）に倣い「忘却と保存の設計」を持つ。

| 目標とする知性レベル | 実現したいこと |
|---|---|
| 小学5年生程度の知性 | 高度な知識問答ではなく、周囲に興味を持ち、働きかけ、経験を蓄積する |
| 身体性の重視 | 宣言的記憶よりも非宣言的記憶（空間・手続き・情動） |
| 制約の現実 | Raspberry Pi 5 + Claude API のコスト・レイテンシーの中で最大化（会話: Haiku / 記憶処理: Sonnet） |

---

## ハードウェア構成

| パーツ | 詳細 |
|---|---|
| コンピュータ | Raspberry Pi 5（16GB） |
| 電源（脳・系統A） | UPS HAT(B) + NCR18650 × 2（5V/5A・自律起動対応） |
| 電源（動力・系統B） | XL4015 DCDC降圧（11.1V → 6V）+ 1000μFコンデンサ |
| バッテリー | 11.1V Li-ion 3セル（3S） |
| マイク | USB単一指向性マイク（hw:3,0） |
| スピーカー | MAX98357A I2S DAC + 4Ω8Wスピーカー |
| カメラ | EMEET SmartCam C960（USB, /dev/video0） |
| サーボドライバ | PCA9685（I2C 0x40） |
| パンチルト | アルミ合金製台座 + DS3218（20kg-cm）× 2 |
| 走行 | YP100タンクシャーシ + TB6612FNG モータードライバ |
| LED | RGB LED（GPIO17/27/22） |

---

## ソフトウェアアーキテクチャ

```
voice_loop.py  ── メインループ（4ステートマシン: idle/listening/thinking/speaking）
    │
    ├─ STT: faster-whisper（small / tiny）
    ├─ TTS: Open JTalk（meiモデル・タチコマ声質）
    ├─ Wakeword: 「おはよう」で起動 / 「おやすみ」でスリープ
    ├─ VAD: webrtcvad による自動発話検出
    ├─ LED: RGB LED ステート可視化
    ├─ GestureController: パンチルトジェスチャー
    ├─ sing_song: LLMが音符列を生成して演奏・首振りリズム連動
    ├─ 退屈行動: アイドル一定時間後に自発的な視線移動・移動・呟き
    │
    └─ GAKUKOMABrain（brain/gakukoma_brain.py）
           │
           ├─ Anthropic API（claude-haiku-4-5）直接呼び出し
           ├─ Tool Use: look_direction / see_around / move_robot / ...
           ├─ few-shot priming（セッション初回のみ）
           ├─ ローカル会話履歴（直近3ターン）
           └─ 記憶システム（3層wiki構造）
                  ├─ ONLINE: wiki/index.md + core_memories.md を参照（Haiku）
                  └─ OFFLINE: memory_processor.py がセッション後に分析・更新（Sonnet）
```

---

## 記憶システム（Phase 5.1〜）

### 設計思想

人間の記憶統合（海馬 → 大脳皮質への転送・睡眠中の記憶固化）を参考に、**ONLINE処理とOFFLINE処理を分離**した設計。

```
ONLINE（会話中・Haiku）     OFFLINE（深夜3時 cron・Sonnet）
─────────────────           ─────────────────────────────────────────
wiki を参照するだけ    →    Step 1: 会話分析（emotion_score + surprise_score）
レイテンシー最優先          Step 2: core_memories.md 更新（感情スコア7以上）
                            Step 2b: surprises.md 更新（驚きスコア6以上）
                            Step 3: people/ ページ更新
                            Step 3b: places/ ページ更新
                            Step 4: index.md 再構築
                            Step 5: Cross-reference 更新（## 関連セクション）
                            log.md: 更新ログ追記
                            ─────────────────────────────────────────
                            毎日: generate_daily_dream（過去記憶ランダム連想 → dreams.md）
                            週次（月曜）: Lint（矛盾検出・孤立ページ・改善提案）
```

### 3層記憶構造

```
memory/
├── raw/              RAWセッションログ（7日で自動削除）
│   └── 2026-04-18_143052.md
└── wiki/             長期記憶（恒久保存）
    ├── index.md            カタログ + 出来事時系列（登場人物・場所リンク付き）
    ├── core_memories.md    感情スコア7以上の核記憶
    ├── surprises.md        驚きスコア6以上の予測誤差記録
    ├── dreams.md           REM連想（Lint時に生成・翌朝の自発発話の源泉）
    ├── log.md              wiki更新の時系列ログ（append-only）
    ├── lint_report.md      週次健全性レポート（矛盾・孤立・改善提案）
    ├── known_names.json    人名エイリアステーブル（名寄せ・重複ページ防止）
    ├── people/             人物ページ（自動更新・cross-reference付き）
    │   └── <人物名>.md
    └── places/             場所ページ（自動更新・トポロジ情報付き）
        └── <場所名>.md
```

人間の脳に倣い、**「何を忘れるか」の設計が記憶の質を決める**。日常的な会話は7日で消え、感情的に重要な体験だけが核記憶として長期保存される。

### 退屈行動（Intrinsic Motivation）

アイドル状態（wakewordリッスン中）が一定時間（デフォルト5分）継続すると、確率的に自発行動を起こす。

| 確率 | 行動 |
|---|---|
| 50% | ランダムな方向を見てカメラで画像取得 → Haiku で感想を生成して呟く |
| 10% | 少し前進してすぐ止まる |
| 15% | `dreams.md` の最新エントリを「昨日ふと思ったんだけど」として呟く |
| 15% | `wiki/index.md` や `core_memories.md` をもとに Haiku で独り言を生成して呟く |
| 10% | 何もしない |

深夜22時〜朝7時はOFF。`config.yaml` の `idle_behavior.interval_sec` で間隔を調整可能。

---

## ディレクトリ構成

```
gakukoma/
├── brain/
│   ├── gakukoma_brain.py      # GAKUKOMABrainクラス（LLMエージェントコア）
│   └── memory_processor.py    # OFFLINE記憶処理（cron実行・wiki更新）
├── memory/                    # 記憶ストレージ
│   ├── raw/                   # セッション生ログ（7日保持）
│   └── wiki/                  # 長期記憶（恒久保存）
│       ├── index.md           # カタログ + 時系列
│       ├── core_memories.md   # 感情スコア7以上の核記憶
│       ├── surprises.md       # 驚きスコア6以上の予測誤差記録
│       ├── dreams.md          # REM連想（毎日生成・翌日の退屈行動・会話で引用）
│       ├── log.md             # 更新ログ（append-only）
│       ├── lint_report.md     # 週次健全性レポート
│       ├── known_names.json   # 人名エイリアステーブル（名寄せ）
│       ├── people/
│       └── places/
├── voice_loop/
│   ├── voice_loop.py          # メインループ（4ステートマシン）
│   ├── led_controller.py      # RGB LED ステート可視化
│   └── config.yaml            # 全設定（音声・サーボ・VAD・idle_behavior等）
├── tools/                     # シェルスクリプト（ツール実行インターフェース）
│   ├── speak_text.sh
│   ├── see_around.sh
│   ├── survey_room.sh         # 3方向撮影 + Vision API一括
│   ├── look_direction.sh
│   ├── look_center.sh
│   ├── look_at_user.sh
│   ├── set_pan_tilt.sh
│   ├── move_robot.sh
│   ├── sing_song.sh           # 音符列演奏 + 首振りリズム連動
│   └── sing_song.py
├── tts/
│   └── speak_text.py          # Open JTalk TTS（meiモデル）
├── stt/
│   └── listen_voice.py        # faster-whisper STT
├── servo/
│   ├── pan_tilt.py            # PCA9685 サーボ制御
│   └── gesture_controller.py  # ジェスチャー制御
├── motor/
│   ├── tb6612_ctrl.py         # TB6612FNG 低レベル制御
│   ├── motor_driver.py        # モータードライバ抽象層
│   └── move_robot_cmd.py      # move_robot コマンド実装
└── camera/
    ├── see_around.py          # OpenCV + Claude Vision API
    ├── face_detect.py         # 顔検出（YuNet DNN / Haar Cascadeフォールバック）
    ├── face_recognizer.py     # 顔認識（LBPH・多フレーム登録・YuNet共有）
    ├── capture.py             # カメラキャプチャ
    └── models/
        └── face_detection_yunet_2023mar.onnx  # YuNet顔検出モデル（OpenCV Zoo）
```

---

## 起動方法

```bash
cd /home/tukapontas/gakukoma/voice_loop
python3 voice_loop.py
```

| 発話 | 動作 |
|---|---|
| 「おはよう」 | アクティブモード移行 |
| 「おやすみ」 | スリープ復帰・セッションログ保存 |

---

## 開発フェーズ

| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase 1 | 音声対話（STT / TTS / Voice Loop） | ✅ 完了 |
| Phase 2 | カメラ・パンチルト追跡（look_at_user） | ✅ 完了 |
| Phase 2.1 | Wakeword / VAD / 首振り方向指示 | ✅ 完了 |
| Phase 2.2 | パンチルト精度向上・I2C安定化 | ✅ 完了 |
| Phase 2.3 | レスポンス速度・ビジュアル認識・UX改善 | ✅ 完了 |
| Phase 2.5 | GAKUKOMABrain（軽量フレームワーク刷新） | ✅ 完了 |
| Phase 3 | タンク走行（TB6612FNG / move_robot / 電源独立） | ✅ 完了 |
| Phase 4 | グリッパー把持 | ⏸ 保留 |
| **Phase 5.1** | **LLM Wiki型記憶システム + 退屈行動** | ✅ **完了** |
| Phase 5.x | sing_song ツール（音符列演奏・首振りリズム連動） | ✅ 完了 |
| Phase 5.2 | 顔認識 + person-wiki（face_recognition） | ✅ 完了 |
| Phase 5.3 | 場所記憶 + エンコーダー活用（トポロジカルマップ） | 📋 指示中 |
| Phase 5.4〜 | Navigation Q-learning / PRIMING動的更新 / YOLO物体検出 | ⬜ 将来 |

---

## 今後の開発ロードマップ（Phase 5.2以降）

### Phase 5.2：顔認識 + person-wiki ✅ 実装済み
- **顔検出**: YuNet（DNN/ONNX）— Haar Cascadeより横顔・距離変化に強い
- **顔認識**: OpenCV LBPH — 登録時15フレーム収集 × 9バリエ拡張（最大135サンプル）
- `look_at_user()` 実行時に「誰か」を識別して名前で呼びかける
- `register_face` ツール: 「がくこま、これが〇〇だよ」で顔登録
- person-wiki（`memory/wiki/people/`）をOFFLINE処理で自動更新

### Phase 5.3：場所記憶 + エンコーダー活用
- `move_robot()` 後に `see_around()` で場所を自動記述・保存
- モーターエンコーダー線（現在未使用）を接続してオドメトリ記録
- SQLiteでトポロジカルマップ（場所ノード・遷移エッジ）を管理
- 「ここ来たことある」と言えるようになる

### Phase 5.4以降（将来ビジョン）
- **Navigation Q-learning**: 部屋のマップ上で経路を自律学習
- **動的PRIMING更新**: 週次でユーザー反応の良い応答パターンを自動学習
- **YOLOv8 nano物体検出**: `see_around()` に物体認識を追加
- **REM睡眠模倣**: ✅ 実装済み（毎日dreams.md生成 + gakukoma_brain.py への注入 + 退屈行動での引用）

### 将来的なハードウェア追加候補
- IMU（MPU-6050, ~$2）: 傾き・加速度・転倒検知
- 距離センサー（HC-SR04, ~$1）: 壁・障害物検知（Q-learning衝突回避に必須）
- 深度カメラ（将来）: 本格SLAM（Pi5との相性要確認）

---

## GAKUKOMABrain — 技術詳細

### 設計方針

| 設計 | 内容 |
|---|---|
| Anthropic API 直接呼び出し | subprocess廃止・起動コストゼロ |
| 最小システムプロンプト | 約200トークン固定（旧比 -92%） |
| 公式 Tool Use 形式 | ツール実行漏れを構造的に防止 |
| ONLINE/OFFLINE分離 | 会話中は軽量・セッション後に重い分析処理 |

### 実測パフォーマンス

| 指標 | 旧構成（OpenClaw） | 現構成 |
|---|---|---|
| Turn 1 input tokens | ~30,105 | ~2,600（-91%） |
| subprocess起動コスト | 300〜500ms | 0ms |
| LLMレイテンシ | 10秒超 | 1〜2秒 |

### ロールバック手順

新フレームワークが動作しない場合:

```bash
# voice_loop.py を旧バージョンに戻す
git checkout <旧コミットハッシュ> -- gakukoma/voice_loop/voice_loop.py

# workspace内部 .git を復元（OpenClaw compaction用）
cd /home/tukapontas/.openclaw/workspace
tar xzf /home/tukapontas/backups/openclaw_workspace_git_20260413.tar.gz

# brain/ を削除
rm -rf /home/tukapontas/gakukoma/brain/
```

---

## cron設定（自動実行）

```
0  3 * * *  python3 /home/tukapontas/gakukoma/brain/memory_processor.py >> /home/tukapontas/gakukoma/memory/processor.log 2>&1
30 3 * * *  /home/tukapontas/gakukoma/backup_memory.sh
```

毎朝3時にOFFLINE処理を実行。RAWログを分析してwikiを更新し、7日超の古いログを削除する。
3時30分に `backup_memory.sh` が実行され、`memory/wiki/` と `camera/face_data/` をGoogle Driveに自動バックアップする（rclone sync）。

## プライバシーとgit管理

`gakukoma/memory/` と `camera/face_data/` はgit管理対象外（`.gitignore`）。個人の会話ログ・人物wiki・顔認識モデルはリポジトリに含まれない。
これらのバックアップはGoogle Drive（`gakukoma_backup/`）で管理する。

---

*最終更新: 2026-05-03（夢・ひらめき機能追加・退屈行動強化：see_around感想/夢引用/記憶呟き・YuNet顔認識換装・起動ボタン実装中）*
