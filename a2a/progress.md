# GAKUKOMA 開発進捗管理

> **ClaudeCode管理ファイル。セッション開始時に必ず確認すること。**
> 完了報告書（`_completed.md`）が届いたら本ファイルを更新する。

最終更新: 2026-04-28（memory_processor スケール修正・感情スコア閾値7に変更・重複ページ統合）

---

## 現在のフェーズ

**Phase 1: 脳の覚醒と対話（Brain & Voice）✅ 完了**
**Phase 2: 目の覚醒（Camera & Look-at）✅ 完了**
**Phase 2.1: UX向上（Wakeword / VAD / 首振り方向指示）✅ 完了**
**Phase 2.2: パンチルト精度向上 ✅ 完了**
**Phase 2.3: レスポンス速度・ビジュアル認識・システムプロンプト改善 ✅ 完了**
**Phase 3: 大地への進出（走行系・電源独立） ✅ 完了**
**Phase 4: スキップ（グリッパー・必要時に再開）**
**→ Phase 5: 記憶と知性の進化 📋 計画中**

---

## ハードウェア手配状況サマリ

> 詳細は `/home/tukapontas/a2a/hardware_lists.md` を参照

| フェーズ | ハードウェア手配 |
|---|---|
| Phase 1 | ✅ 全て手配済み（Pi5, クーラー, SD, マイク, スピーカー） |
| Phase 2 | ✅ 全て手配済み（カメラ, パン・チルト台座, PCA9685） |
| Phase 3 | ✅ 全て手配済み・一部変更あり（タンクシャーシ✅組立完了, TB6612FNG, UPS HAT(B), 11.1V Li-ion, LM2596, **DS3218+アルミパンチルト台座+1000μFコンデンサ追加**） |
| Phase 4 | ⬜ 未手配（グリッパーキット） |
| 共通消耗品 | 🔶 一部手配済み（ジャンパーワイヤ済み / スペーサー・両面テープ未手配） |

---

## タスク進捗一覧

### Phase 1（ハードウェア手配済み → 即着手可能）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| 音声HW（マイク・スピーカー）セットアップ | Gemini | ✅ 完了 | `hardware/20260311_phase1_audio_hardware_setup_implementation.md` | `hardware/20260311_phase1_audio_hardware_setup_completed.md` |
| Faster-Whisper (STT) + Piper (TTS) + Voice Loop 実装 | Antigravity | ✅ 完了 | `coding/20260311_phase1_stt_tts_voiceloop_implementation.md` | `coding/20260311_phase1_stt_tts_voiceloop_completed.md` |
| TTS移行：Piper → Open JTalk（meiモデル・タチコマ声質） | Antigravity | ✅ 完了 | `coding/20260314_phase1_tts_openjtalk_migration_implementation.md` | `coding/20260314_phase1_tts_openjtalk_migration_completed.md` |

### Phase 2（ハードウェア手配済み → Phase 1完了後に着手可能）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| Webカメラ・OpenCV環境構築 + `see_around()`実装 | Antigravity | ✅ 完了 | `coding/20260315_phase2_camera_opencv_implementation.md` | `coding/20260315_phase2_camera_opencv_completed.md` |
| パン・チルト台座の組み立て | Gemini | ✅ 完了 | `hardware/20260315_phase2_pantilt_assembly_implementation.md` | `hardware/20260315_phase2_pantilt_assembly_completed.md` |
| PCA9685サーボドライバ配線 | Gemini | ✅ 完了 | `hardware/20260315_phase2_pca9685_wiring_implementation.md` | `hardware/20260315_phase2_pca9685_wiring_completed.md` |
| `look_at_user()` ツール実装・統合テスト | Antigravity | ✅ 完了 | `coding/20260315_phase2_look_at_user_implementation.md` | `coding/20260315_phase2_look_at_user_completed.md` |

### Phase 2.1（Phase 3着手前のUX改善スプリント）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| Wakeword（がくこま起きて/おやすみ） + VAD自動発話終了 | Antigravity | ✅ 完了 | `coding/20260317_phase2_1_wakeword_vad_implementation.md` | `coding/20260317_phase2_1_wakeword_vad_completed.md` |
| 首振り方向指示ツール（look_direction / set_pan_tilt） | Antigravity | ✅ 完了 | `coding/20260317_phase2_1_look_direction_implementation.md` | `coding/20260317_phase2_1_look_direction_completed.md` |

### Phase 2.2（Phase 3着手前のUX改善スプリント・第2弾）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| パンチルト実機診断（左向きI2C / tilt限界値） | Gemini | ✅ 完了 | `research/20260318_pantilt_diagnosis_request.md` | `research/20260318_pantilt_diagnosis_completed.md` |
| I2Cバス復旧 + 配線ゆとり修正 | Gemini | ✅ 完了 | `hardware/20260319_i2c_recovery_wiring_fix_implementation.md` | `hardware/20260319_i2c_recovery_wiring_fix_completed.md` |
| ツール定義改善 + look_center + 音声品質向上 | Antigravity | ✅ 完了 | `coding/20260318_plan22_tools_voice_implementation.md` | `coding/20260318_plan22_tools_voice_completed.md` |
| config.yaml tilt範囲調整 + 左向き対処（pan_max/offset動的設定化） | Antigravity | ✅ 完了 | `coding/20260318_pantilt_config_fix_implementation.md` | `coding/20260318_pantilt_config_fix_completed.md` |
| パンチルト設定動的化 T-1〜T-6 テスト再実施 | Antigravity | ✅ 完了 | `coding/20260319_pantilt_config_retest_implementation.md` | `coding/20260319_pantilt_config_retest_completed.md` |
| release()/deinit() バグ修正 + tilt_max拡張 | ClaudeCode | ✅ 完了 | `coding/20260319_pantilt_deinit_fix_implementation.md` | - |

### Phase 2.3（Phase 3着手前のUX改善スプリント・第3弾）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| workspaceのMDファイル整理・統合（AGENTS.md縮小・IDENTITY.md削除等） | ClaudeCode | ✅ 完了 | - | - |
| レスポンス速度改善（ローリングウィンドウ + プロンプトキャッシュ） | Antigravity | ✅ 完了 | `coding/20260321_phase2_3_response_speed_implementation.md` | `coding/20260321_phase2_3_response_speed_completed.md` |
| ビジュアル認識改善（see_around視点修正 + survey_room実装） | コーディング担当AI | ✅ 完了 | `coding/20260321_phase2_3_visual_recognition_implementation.md` | `coding/20260321_phase2_3_visual_recognition_completed.md` |
| voice_loop 4ステートマシン化（ACTIVEモード常時リスニング + TTS混線防止） | Antigravity | ✅ 完了 | `coding/20260321_voiceloop_4state_implementation.md` | `coding/20260321_voiceloop_4state_completed.md` |
| LEDによるself-state可視化（RGB LED配線） | Gemini | ✅ 完了 | `hardware/20260321_led_selfstate_implementation.md` | `hardware/20260321_led_selfstate_completed.md` |
| LEDによるself-state可視化（コーディング実装） | Antigravity | ✅ 完了 | `coding/20260325_led_selfstate_coding_implementation.md` | `coding/20260325_led_selfstate_coding_completed.md` |
| トークン削減: セッション管理修正 + ツールプロファイル最小化 | Antigravity | ✅ 完了 | `coding/20260322_token_reduction_session_fix_implementation.md` | `coding/20260322_token_reduction_session_fix_completed.md` |
| few-shot priming + ローカル会話履歴注入（定型フレーズ癖の解消） | Antigravity | ✅ 完了 | `coding/20260324_voiceloop_fewshot_history_implementation.md` | `coding/20260324_voiceloop_fewshot_history_completed.md` |
| パンチルト ジェスチャー機能（スリープ復帰・シンキング・スピーキング） | Antigravity | ✅ 完了 | `coding/20260410_pantilt_gesture_implementation.md` | `coding/20260410_pantilt_gesture_completed.md` |
| ジェスチャー修正（Thinking動作スロー化 + Listening移行時停止） | Antigravity | ✅ 完了 | `coding/20260411_gesture_fix_implementation.md` | `coding/20260411_gesture_fix_completed.md` |

**着手順序**: ClaudeCode（MDファイル整理）→ コーディング担当AI（レスポンス速度・ビジュアル認識、並行可能）

### Phase 2.5: GAKUKOMA Brain フレームワーク刷新（Phase 3 Task D並行）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| GAKUKOMA Brain 設計・指示書作成 | ClaudeCode | ✅ 完了 | `coding/20260410_gakukoma_brain_implementation.md` | - |
| `gakukoma_brain.py` 実装 + voice_loop.py置き換え | Claudeサブエージェント | ✅ 完了 | `coding/20260410_gakukoma_brain_implementation.md` | `coding/20260410_gakukoma_brain_completed.md` |

#### ⚠️ ロールバック手順（新フレームワークが動作しない場合）

**旧構成に戻す手順:**

```bash
# 1. voice_loop.py を git で旧バージョンに戻す
git checkout <旧コミットハッシュ> -- gakukoma/voice_loop/voice_loop.py

# 2. workspace の内部 .git を復元（OpenClaw compaction機能の復旧）
cd /home/tukapontas/.openclaw/workspace
tar xzf /home/tukapontas/backups/openclaw_workspace_git_20260413.tar.gz
# → .git/ が復元され、OpenClaw compaction が再び動作する

# 3. gakukoma_brain.py は削除するだけでよい（voice_loop.py が使わない）
rm -rf /home/tukapontas/gakukoma/brain/
```

**バックアップ保存場所:**
- `/home/tukapontas/backups/openclaw_workspace_git_20260413.tar.gz` — workspace内部 `.git` のスナップショット（2026-04-13時点）

---

### Phase 3（ハードウェア手配済み・タンク組立完了 → 即着手可能）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| **ハードウェア手配** | Gemini | ✅ 完了 | - | `hardware/20260320_phase3_hardware_procurement_completed.md` |
| **SG90→DS3218換装・アルミパンチルト台座・コンデンサ追加（アップグレード）** | Gemini | ✅ 完了（手配） | - | `hardware/20260402_hardware-procurement-upgrade_completed.md` |
| **タンクシャーシ組み立て** | Gemini | ✅ 完了 | - | `hardware/20260402_hardware-procurement-upgrade_completed.md` |
| Task A1: Pi5 EEPROM設定（PSU_MAX_CURRENT=5000） | Antigravity | ✅ 完了 | `coding/20260402_phase3_eeprom_setup_implementation.md` | `coding/20260402_phase3_eeprom_setup_completed.md` |
| Task A2: UPS HAT(B) Pi5自律起動テスト | Gemini | ✅ 完了 | `hardware/20260402_phase3_ups_hat_test_implementation.md` | `hardware/20260402_phase3_ups_hat_test_completed.md` |
| Task B: 系統B電源構築（LM2596 6V設定・コンデンサ挿入・GND共通接地） | Gemini | ✅ 完了 | `hardware/20260402_phase3_power_system_b_implementation.md` | `hardware/20260402_phase3_power_system_b_completed.md` |
| Task C: タンクシャーシ確認・モーター配線準備 | Gemini | ✅ 完了 | `hardware/20260402_phase3_chassis_prep_implementation.md` | `hardware/20260402_phase3_chassis_prep_completed.md` |
| Task D: TB6612FNG配線（GPIO接続・電源系統B接続） | Gemini | ✅ 完了 | `hardware/20260402_phase3_tb6612_wiring_implementation.md` | `hardware/20260402_phase3_tb6612_wiring_completed.md`（★AIN2はGPIO26に変更済み） |
| Task E: DS3218換装・アルミパンチルト台座移行 | Gemini | ✅ 完了 | `hardware/20260402_phase3_ds3218_swap_implementation.md` | `hardware/20260402_phase3_ds3218_swap_completed.md` |
| Task F: 統合ハードウェア検証 | Gemini | ✅ 完了 | `hardware/20260416_phase3_hw_integration_verification_implementation.md` | `hardware/20260416_phase3_hw_integration_verification_completed.md` |
| Task G: `move_robot()` ツール実装 | コーディング担当AI | ✅ 完了 | `coding/20260416_phase3_move_robot_implementation.md`（旧0402は中止） | `coding/20260416_phase3_move_robot_completed.md` |
| Task H: 走行・電源の統合テスト | コーディング担当AI + Gemini | ✅ 完了（Task G T-1〜T-7でカバー・運用で継続確認） | - | - |

### Phase 4（スキップ・運用しながら判断）

グリッパーキットは未手配。Phase 3完了時点で運用フェーズへ移行し、必要に応じて再開する。

---

### Phase 5：記憶と知性の進化（📋 計画中）

> アクションプラン: `plan/phase5_action_plan.md`
> 参照議論: `research/20260417_brain_evolution_discussion.md`

#### Phase 5.1：LLM Wiki型記憶システム（最優先・即着手可能）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| Task A〜E: 3層記憶 + OFFLINE処理 + 感情核記憶 + 忘却スケジュール + 退屈行動 | Antigravity | ✅ 完了 | `coding/20260418_phase5_1_memory_wiki_implementation.md` | `coding/20260418_phase5_1_memory_wiki_completed.md` |
| Task F: 統合テスト（T-1〜T-8） | ユーザー | ✅ 完了 | - | - |
| 運用改善: index wiki構造化・感情スコア相対評価・places/追加 | Claudeサブエージェント | ✅ 完了 | `coding/20260423_memory_wiki_improvements_implementation.md` | `coding/20260423_memory_wiki_improvements_completed.md` |
| v2: Sonnet移行・Lint/Cross-ref/surprise_score/dreams/log | Claudeサブエージェント | ✅ 完了 | `coding/20260423_memory_wiki_v2_implementation.md` | `coding/20260423_memory_wiki_v2_completed.md` |
| v3: スケール修正（ページ肥大化・重複統合・cross-reference差分化・コンパクション） | ClaudeCode | ✅ 完了 | `coding/20260428_memory_wiki_scale_fix_implementation.md` | `coding/20260428_memory_wiki_scale_fix_completed.md` |

#### Phase 5.x：sing_song ツール（並行タスク）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| sing_song ツール実装（音符列演奏 + 首振り） | gakukoma-coder | ✅ 完了 | `coding/20260424_sing_song_implementation.md` | `coding/20260424_sing_song_completed.md` |
| sing_song 首振りバグ修正・リズム連動 | ClaudeCode | ✅ 完了 | - | - |

#### Phase 5.2：顔認識 + person-wiki（Phase 5.1 運用3週間後に着手）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| Task A〜E: 顔認識導入 + person-wiki実装 + 統合テスト | Claudeサブエージェント | ✅ 完了 | `coding/20260423_phase5_2_face_recognition_implementation.md` | `coding/20260423_phase5_2_face_recognition_completed.md` |

#### Phase 5.3：場所記憶 + エンコーダー活用（Phase 5.2 と並行可）

| タスク | 担当 | 状態 | 指示書 | 完了報告書 |
|---|---|---|---|---|
| Task A: エンコーダー配線 | Gemini | 📋 指示中 | `hardware/20260423_phase5_3_encoder_wiring_implementation.md` | - |
| Task B〜F: オドメトリ + 場所記述 + マップ管理 + wiki更新 + 統合テスト | Antigravity | 📋 指示中 | `coding/20260423_phase5_3_place_memory_implementation.md` | - |

#### Phase 5.4以降（将来・着手時期未定）

Navigation Q-learning / 動的PRIMING更新 / YOLOv8 nano / REM睡眠模倣

---

## 状態凡例

| 記号 | 意味 |
|---|---|
| ⬜ 未着手 | 指示書未作成 |
| 📋 指示中 | 指示書作成済み・実装中 |
| ✅ 完了 | 完了報告書受領・確認済み |
| ⚠️ 保留 | 問題発生・要確認 |

---

## 完了済みタスクのサマリ

※ 完了報告書を受領したら以下に追記する

- **2026-03-13** 音声HWセットアップ（Gemini）: USBマイク `hw:3,0`・スピーカー `plughw:2,0` 認識確認。MAX98357A I2S DACをcard 2として認識。
- **2026-03-13** STT/TTS/Voice Loop実装（Antigravity）: Faster-Whisper `small`モデル・Piper TTS・Push-to-Talk voice_loop.py・OpenClaw統合 完了。TTSは暫定英語モデル（`en_US-lessac-medium`）使用中。
- **2026-03-14** TTSエンジン選定リサーチ（Gemini）: Piperは日本語の「子供らしい声」モデル不足・レイテンシ懸念あり。**Open JTalk（meiモデル）に変更決定**。タチコマ風声質をパラメータチューニングで実現する。
- **2026-03-15** TTS Open JTalk移行（Antigravity）: meiモデル導入・speak_text.py / voice_loop.py 書き換え完了。レイテンシ約76ms（旧Piper比1/13）。全テスト合格。
- **2026-03-15** MAX98357Aはんだ付け（ユーザー手作業）: ピンヘッダ固定完了。ノイズ問題解消。
- **2026-03-15** パン・チルト台座組み立て（Gemini）: SG90×2をブラケット固定・Webカメラ最上部に固定完了。手動可動確認済み。ホーン干渉はニッパーカットで解決。サーボセンター出しはPCA9685接続後に要調整。
- **2026-03-15** Phase 1 統合テスト・チューニング（ClaudeCode直接対応）: 不具合4件（HF認証警告・録音デバイス誤設定・LLM速度・STT固有名詞未認識）を発見・全修正。LLMをClaude Haiku切り替え・STT常駐化でレスポンス大幅改善。**Phase 1 全完了**。
- **2026-03-16** Webカメラ・OpenCV環境構築 + `see_around()`実装（Antigravity）: `/dev/video0`(EMEET SmartCam C960)認識・顔検出・Claude Vision API統合完了。`see_around`ツールをOpenClawから呼び出し可能。レイテンシ約4〜6秒。全テスト合格。
- **2026-03-16** PCA9685サーボドライバ配線（Gemini）: I2C `0x40`検出確認。ch0=パン・ch1=チルト。GNDはPin9使用（Pin6は既使用）。adafruit-circuitpython-pca9685導入（`--break-system-packages`）。SG90×2動作確認済み。※サーボ回転方向（パン135°方向・チルト110°方向）はユーザー確認待ち→Antigravity向け申し送りあり。
- **2026-03-16** `look_at_user()` ツール実装・統合テスト（Antigravity）: カメラ顔検出→パン・チルトサーボ追跡アルゴリズム実装完了。pan_gain=-0.1・tilt_gain=0.1に調整（サーボ回転方向補正）。`convergence_px=30`・`max_iterations=20`・ウォームアップ5フレーム。OpenClaw統合（TOOLS.md/SOUL.md更新）済み。全テスト合格。**Phase 2 全完了**。
- **2026-03-17** Wakeword/VAD実装（Antigravity）: `voice_loop.py` を全書き換え。sounddevice+webrtcvadによるハンズフリー対応。ウェイクワード「ガクコマ起動」検出（Whisper tiny）→アクティブ会話（Whisper small）→「おやすみ」で待機復帰のステートマシン完成。Idle時CPU 0.1%以下。サンプルレート48000Hz・volume_threshold=15000に調整済み。全テスト合格。
- **2026-03-18** パンチルト実機診断（Gemini）: pan=180°でI2C断線（0x70アドレス消失・配線物理干渉が原因）。チルト範囲はコード内60-120にハードコード済み（config.yaml動的化が必要）。サーボホーンが約45°時計回りにズレ。対処方針: pan_max=170°でソフト制限・config.yaml動的設定化・pan_offset追加。
- **2026-03-18** パンチルト設定動的化（Antigravity）: config.yamlにpan_min/pan_max/pan_offset/tilt_min/tilt_max追加。pan_tilt.pyを動的読み込み・クランプ・オフセット補正・OSErrorハンドリングに改修。look_directionの"left"をpan_maxに連動化。コード実装完了。ただしT-1テストでハング発生（I2Cバススタック）→ハードウェア電源リセット後に再テスト必要。
- **2026-03-19** パンチルト設定動的化 再テスト（Antigravity）: T-1〜T-6全合格。クランプ・動的設定・オフセット反映全て確認。I2Cハング再発なし。スクリプトパスは `/home/tukapontas/gakukoma/tools/` に確定。
- **2026-03-19** I2Cバス復旧・配線ゆとり修正（Gemini）: PCA9685電源リセット・配線余長確保完了。`i2cdetect -y 1`で0x40/0x70正常応答確認。set_pan_tilt.sh 90 90・look_direction.sh left・クランプ動作（pan_max=170°）全テスト合格。ハードウェア側ハング要因完全排除。
- **2026-03-17** 首振り方向指示ツール実装（Antigravity）: `pan_tilt.py` に `look_direction()`・`set_pan_tilt()` を追加。日本語/英語方向名対応。fcntlによるファイルベース排他ロック（`/tmp/gakukoma_servo.lock`）導入・I2Cバス競合解消。シェルスクリプト（`look_direction.sh`・`set_pan_tilt.sh`）作成・OpenClaw統合（TOOLS.md/SOUL.md更新）済み。全テスト合格（T-7〜T-12）。**Phase 2.1 全完了**。

---

## 申し送り事項・懸案事項

- **✅ はんだ付け完了（2026-03-15）**: MAX98357Aアンプ基板のピンヘッダ固定完了。ノイズ問題解消。
- **✅ TTS Open JTalk移行完了（2026-03-15）**: meiモデルによる日本語発話・レイテンシ76ms確認済み。
- **✅ Phase 1 全完了（2026-03-15）**: 統合テスト・全不具合修正・チューニング完了。
- **✅ Phase 2 全完了（2026-03-16）**: `look_at_user()` 実装・統合テスト完了。Phase 2 全タスク完了。
- **✅ Phase 2.1 全完了（2026-03-17）**: Wakeword / VAD / 首振り方向指示ツール 全タスク完了。
- **✅ Phase 2.2 全完了（2026-03-19）**: パン・チルト物理動作確認・release/deinitバグ修正・TOOLS.md整理・SKILLS.md削除完了。
- **✅ Wakeword チューニング（2026-03-20）**: volume_threshold 3000→200に修正（実測: 無音50・発声400〜700）。ストリーム初期化ノイズ対策（warm-up 15フレーム）追加。起動ワードを「ガクコマ起動」→「ガクコマ」単体に変更。wakeword転写の initial_prompt を空にしてハルシネーション誤検知リスクを排除。
- **✅ パン・チルト物理動作確認完了（2026-03-19）**: release()/deinit()バグ修正により全軸動作確認。0x70消失はadafruit_pca9685ライブラリ初期化時の正常動作（問題なし）。tilt_max=180°に拡張済み。
- **⚠️ コーディング担当AI向け恒久注意事項**: `pan_tilt.py` に `__del__` を追加してはならない。スクリプト終了時に `deinit()` が走りI2Cバスが切断される。`release()` メソッドは存在するが、`look_direction`・`set_pan_tilt`・`look_center` 内から呼び出してはならない（サーボが即脱力する）。
- **✅ Phase 3 ハードウェア手配完了（2026-03-20）**: タンクシャーシ・UPS HAT(B)・11.1V Li-ion・TB6612FNG・LM2596・消耗品全手配済み。
- **✅ Phase 3 ハードウェアアップグレード完了（2026-04-02）**: SG90+プラスチック台座 → DS3218（20kg-cm/金属ギア）+アルミ合金製パンチルト台座に変更。電源設計変更: LM2596を11.1V→6.0V固定でPCA9685 V+へ専用給電。1000μFコンデンサ（突入電流対策）追加。全パーツ手配・タンク組立完了。詳細: `hardware/20260402_hardware-procurement-upgrade_completed.md`。
- **✅ Phase 3 プラン策定完了（2026-04-02）**: `plan/phase3_action_plan.md` 作成。電源系統A確立→系統B構築→HW組立→SW実装の最適フロー（Task A1〜H）確定。
- **✅ Phase 2.3 Task C完了（2026-03-21）**: AGENTS.md 7,874B→821B（-90%）、SOUL.md英語部分除去、TOOLS.md listen_voice除去、IDENTITY.md・HEARTBEAT.md削除。推定-2,400トークン/ターン削減。T-6合格（わずかにそっけなさあり、許容範囲内）。T-7合格（体感で明確な速度改善確認。数値計測はTask A実装時にAntigravityが組み込み予定）。
- **✅ Phase 2.3 Task A完了（2026-03-21）**: プロンプトキャッシュ（cacheRetention: "short"）+ contextPruning（cache-ttl: 5m）をopenclaw.jsonに設定。LLMレイテンシ10秒超→1〜2秒に激減。全体5〜7秒を達成。`max_history_turns: 6` はconfig.yamlに記載のみで実装しないと決定（理由: セッションは「ガクコマ」ウェイクワードで自然リセットされるため、6ターンで文脈を切ると会話の継続性が損なわれる）。
- **✅ voice_loop 4ステートマシン化完了（2026-03-21）**: idle/listening/thinking/speakingの4状態管理。ACTIVEモード中ストリーム維持・flush_stream()でTTS残響排除。T-1〜T-7全PASS。LED拡張準備済み（self.stateに追記するだけで対応可能）。
- **✅ トークン削減・セッション管理修正完了（2026-03-22）**: voice_loop.pyにUUID生成を追加しセッション完全独立化。openclaw.jsonに13ツールのdenyリスト追加（exec/write/memory_getの3ツールのみ）。IDENTITY.md 1行に最小化。Turn 1 input ~88,000 → 30,105 tokens（**約66%削減**）。
- **✅ LED self-state可視化 コーディング完了（2026-03-25）**: `led_controller.py` 新規作成（gpiozero.RGBLED）+ `voice_loop.py` 8箇所にLED同期追加。T-1〜T-6全PASS。ステート追加時は `led_controller.py` の `set_state` に追記するだけ。
- **✅ LED self-state可視化 配線完了（2026-03-25）**: GPIO17(R)/GPIO27(G)/GPIO22(B)にRGB LEDコモンカソード配線。赤=speaking・緑=listening・青=idle・黄=thinking(R+G混色)の全色PASS。**重要: RPi.GPIOはPi5非対応（RuntimeError）→ `gpiozero` ライブラリを使用すること**。抵抗値: R/G=150Ω・B=47Ω。
- **✅ few-shot priming + ローカル会話履歴注入完了（2026-03-25）**: `voice_loop.py` に初回ターンのみfew-shot priming付加・2ターン目以降は最大5ターン分のローカル会話履歴注入を実装。定型フレーズ乱発・ユーザー発言繰り返し問題を解消。セッションリセット時に履歴・フラグ初期化確認。T-1〜T-4全合格。
- **✅ 定型フレーズ癖・冗長発話の追加修正（2026-03-25）**: 実機検証で依然として発話繰り返し・冗長応答が残存していたため3点修正。①`memory/2026-03-24.md` の「へぇ〜、ワクワクしちゃう！」を中立記述に書き換え。②`SOUL.md` 末尾に「応答の大原則（最重要）」セクションを追加（2〜3文以内・NG/OK例）。③`AGENTS.md` にmemory記録フォーマットと会話返答を混同しない注記を追加。さらに根本原因として **systemプロンプトより会話中の直接指示が効く** ことが判明したため、`voice_loop.py` の `_PRIMING_EXAMPLES` を「参考例の提示」から「ガクチョがルールを言い渡しがくこまが同意する会話形式」に変更。実機で完全改善を確認。
- **✅ ジェスチャー修正完了（2026-04-11）**: Thinkingパターンを大きな視点移動（右斜め上→左斜め上→右下、2.0〜2.5秒）に再設計。認識失敗時にlistening復帰前で `gesture.stop()` を実行しサーボ音誤検知ループを排除。T-1〜T-4全PASS（実機確認済み）。
- **✅ ビジュアル認識改善完了（2026-04-14）**: see_around視点プロンプトを一人称視野（「僕が今見ているもの」）に修正。survey_room.sh新規作成（左・正面・右の3方向撮影→Vision API一括送信）。TOOLS.mdにsurvey_roomエントリ追加。T-1〜T-7全PASS（実機確認済み）。**Phase 2.3 全タスク完了**。
- **✅ Phase 3 Task A1完了（2026-04-06）**: `PSU_MAX_CURRENT=5000` をEEPROMに書き込み・再起動後反映確認済み。UPS HAT(B)からの5V/5A給電をPi5が上限5Aとして正常認識。Task A2開始準備完了。
- **✅ Phase 3 Task A2完了（2026-04-07）**: UPS HAT(B)+NCR18650×2でACアダプタなし自律起動成功。`vcgencmd get_throttled=0x0`・`core=0.8803V`・パススルー充電も確認。**系統A（脳用電源）確立完了**。USBケーブル非依存の移動可能な「身体性」基盤が整った。
- **✅ Phase 3 Task B完了（2026-04-10）**: XL4015（CC/CV対応）で6.02V出力確立。1000μF/25V電解コンデンサ出力側実装。Pi5 Pin20 ↔ ブレッドボードGNDレールで共通GND確立。**系統B（動力系電源）基盤完成**。
  - ※降圧モジュールは仕様変更: LM2596 → XL4015（CC/CV個別調整対応版）
- **✅ Phase 3 Task C完了（2026-04-10）**: タンクシャーシ（YP100）搭載レイアウト決定・全基板固定完了。モーター動力線（赤+/黒-）識別済み。エンコーダー線（黄・白・緑・青）は現在未使用。搭載構成: 前方=カメラ+マイク、中央=ブレッドボード+TB6612FNG+XL4015+スピーカー、後方=Pi5（UPS HAT装着）。
- **✅ Phase 3 Task E完了（2026-04-10）**: DS3218×2をアルミ合金製台座に搭載・Webカメラ最上部固定・ch0(パン)/ch1(チルト)接続・6.12V安定供給確認。申し送り事項はClaudeCodeが直接対応・動作確認済み（詳細↓）。
- **✅ Phase 3 Task E ソフトウェア調整完了（2026-04-10、ClaudeCode直接対応）**:
  - `pan_max`: 170→160（Pi5本体との物理干渉防止）
  - `tilt_invert: true` 追加 + `set_tilt()` に物理反転処理を実装（`physical = tilt_min + tilt_max - logical`）
  - `tilt_min: 60 / tilt_max: 120`（合計180を維持しcenter=physical90°、UP端物理120°でボディ干渉なし）
  - `tilt_gain`: -0.1→0.1（物理反転をコードが吸収するため正値に戻す）
  - 全方向動作確認済み（up/down/left/right/center）
- **✅ GitHubリポジトリ作成（2026-04-13）**: https://github.com/akiratsukakoshi/gakukoma に初回push完了。管理対象: `gakukoma/`・`a2a/`・`.openclaw/workspace/`。`openclaw.json`（APIキー）は除外済み。
- **✅ workspace内部 .git 削除（2026-04-13）**: OpenClaw compaction用の内部gitを削除し、外側リポジトリに統合。バックアップ: `/home/tukapontas/backups/openclaw_workspace_git_20260413.tar.gz`。ロールバック手順は上記Phase 2.5セクション参照。
- **✅ GAKUKOMA Brain実装完了（2026-04-14、Claudeサブエージェント）**: `gakukoma_brain.py`新規作成・`voice_loop.py`修正完了。Anthropic SDK直接呼び出し（subprocess/OpenClaw廃止）・prompt caching・ツール実行ループ実装。import確認・構文確認PASS。実機テスト（T-3〜T-8）は次回セッションで実施。懸念: speak_text二重発話リスク・local_history上限なし（長時間セッションで増加）・max_tokens=200超過時空文字列返却の可能性。
- **✅ Phase 3 Task F完了（2026-04-16）**: 統合ハードウェア検証完了。電源系統・パンチルトサーボ・モータードライバ全て疎通確認済み。詳細: `hardware/20260416_phase3_hw_integration_verification_completed.md`。
  - 電源: 系統A=5.0V・系統B制御6.19V・動力12.3V・共通GND確立
  - サーボ: I2C 0x40認識・全方向動作確認
  - モーター: STBY疎通確認・左右モーター動作確認
  - **⚠️ Task G実装向け申し送り（重要）**:
    - 右モーター（BIN）は物理配線極性により「前進命令=後退回転」→ `move_robot()` 実装時にBINの正転/逆転ロジックを左と逆にすること
    - 左モーターは履帯の張りが強く PWM 0.3 では脱調（ピー音）発生 → **最小PWMデューティ比を 0.4〜0.6 以上から開始**すること
    - GPIOアサイン確定版は `20260416_phase3_hw_integration_verification_implementation.md` 参照（AIN2=GPIO26等）
- **✅ Phase 3 Task G完了（2026-04-16）**: T-1〜T-7 全PASS。実機調整で判明した事項: 両モーター配線極性が逆（`motor_a_invert: true`・`motor_b_invert: false`）。default_speed=70・turn_speed=65に調整。左右履帯の張り調整（物理）で直進・旋回とも良好。Brain統合（T-6）・走行+首振り同時（T-7）ともPASS。
- **→ Phase 3 次のステップ**: Task H（走行・電源の統合テスト T-1〜T-13）へ。指示書未作成。
- **✅ Phase 3 Task D完了（2026-04-16）**: TB6612FNG配線完了。VM=12V・VCC=3.3V実測確認。STBY疎通スクリプト正常動作確認。**★ AIN2ピン変更**: GPIO21（Pin40）がMAX98357Aと競合のため、GPIO26（Pin37）に恒久変更。GPIOアサイン確定版: PWMA=GPIO12, AIN1=GPIO20, **AIN2=GPIO26**, PWMB=GPIO13, BIN1=GPIO24, BIN2=GPIO25, STBY=GPIO16。
- **申し送り（Phase 3以降）**: サーボ駆動時の瞬間電流消費が大きいため、モーター増加時はPin 4ではなく外部電源（DCDC）からの供給推奨（Antigravityより）。
- **継続観測**: レスポンス速度が目標8秒未達の場合はストリーミング発話実装を検討。
- **✅ カメラ解像度改善（2026-04-18、ClaudeCode直接対応）**: `config.yaml` のカメラ解像度を 640×480 → **1280×720（HD）** に変更。原因: カメラは1080p対応だが設定がVGAに固定されており、Claude Vision APIに送る画像品質が大幅に低下していた（カメラ性能の約88%を未活用）。OpenCVは撮影のみでありこれが"目の悪さ"の主因。**⚠️ 改善が見られない場合の次の選択肢**:  ①Vision処理を `claude-haiku` → `claude-sonnet-4-6` に切り替える（`see_around.py:51` のモデル名変更のみ。見た目の精度は上がるがコスト・レスポンス数秒増）  ②解像度をさらに 1920×1080 に上げる（ただし API送信データが大きくなりレスポンス遅延増加のトレードオフ）  ③照明改善（暗い環境では解像度に関係なく認識精度が落ちる）
- **✅ 複数アクション連鎖対応（2026-04-18、ClaudeCode直接対応）**: `gakukoma_brain.py` の SYSTEM_PROMPT に「複合指示はツールを順番に呼び出して達成する」を追記。PRIMING_EXAMPLES に複数ステップの例（前進→右旋回）を追加。既存の `_call_api()` whileループがツール連鎖を処理するため追加実装不要。
- **✅ max_tokens 200→512へ拡張（2026-04-22、ClaudeCode直接対応）**: 複数ツール連鎖（特に `see_around` 後の複合報告）で200トークン超過→空文字列返却→沈黙になる問題を修正。`gakukoma_brain.py:286` を `max_tokens=512` に変更。SOULルール（2〜3文以内）が守られている限り実際の生成トークンは少ないため、レスポンス速度・コストへの影響は最小限。
- **✅ 自律探索行動の有効化（2026-04-22、ClaudeCode直接対応）**: 「あたりを動き回って見まわして」のような開放的指示に対して、Claude自身がmove_robot+see_aroundを計画・連続呼び出しできるよう対応。①SYSTEM_PROMPTに「探索系指示はツールを3〜5セット繰り返して達成する・実況speak_text可」を追記、②PRIMINGに探索の具体例を追加、③`_call_api()` にMAX_TOOL_ITERATIONS=20の安全上限を追加（無限ループ防止）。
- **✅ sing_song ツール実装・バグ修正完了（2026-04-24）**: LLMが音符列をその場で生成して渡す設計。公共ドメイン曲・自作メロディ・雰囲気指定（「悲しく」等）に対応。演奏前にPanTiltControllerを初期化し、累積0.3秒ごとに左右交互に首振り（リズム連動）。演奏後に正面戻し。**⚠️ スレッド設計は使わないこと**: I2C初期化が遅く短い曲で首が動かなくなる（初回実装で判明）。演奏ループに直接組み込む方式が正解。
- **✅ memory_processor cross-referenceエラー修正（2026-04-24、ClaudeCode直接対応）**: `_update_cross_references()` でLLMが返すJSONの `related_section` 文字列にリテラル改行が混入し `json.JSONDecodeError: Unterminated string` が発生していた問題を修正。`related_section`（マークダウン文字列）を廃止し、`related_places` / `related_people` / `related_memories` のリスト形式に変更。Python側でマークダウンを組み立てることで改行混入問題を根本排除。
- **✅ memory_processor cross-reference/lintエラー再発修正（2026-04-27、ClaudeCode直接対応）**: 2026-04-24の修正後も `_update_cross_references()` と `lint_wiki()` でJSONパースエラーが継続していた問題を修正。原因: LLMが `rem_association`（1〜2文の自由記述）などの文字列値にリテラル改行を混入させることが引き続き発生。対策: `_safe_parse_json()` ヘルパーを追加し、初回パース失敗時に全リテラル改行をスペース化して再試行するようにした。構造的な改行もスペースになるがjsonとして問題なし。`import re` もトップレベルに追加。
- **✅ voice_loop ACTIVEモードXRUNバグ修正（2026-04-27、ClaudeCode直接対応）**: 会話の途中で音声認識が止まる（LED緑のまま）問題を修正。原因: `sd.InputStream` をセッション全体で共有したまま thinking+call_brain+speak（合計10〜30秒超）の間バッファを読まず ALSA XRUN が発生、その後の `stream.read()` が無期限ブロックしていた。sing_song 追加でTTS長時間化が引き金に。対策（案A）: ストリームをlistenサイクルごとに開き直す方式に変更。`flush_stream()` 呼び出しも不要になったため削除。
- **✅ memory_processor スケール問題修正・感情スコア閾値変更（2026-04-28、ClaudeCode直接対応）**: cross-referenceエラーの根本原因がmax_tokensではなくwikiページの構造的肥大化・重複生成であることを特定。①重複ページ統合（そのさん/ソータ/がくこまの部屋/自分の部屋の4ファイルを正規ページにマージして削除）、②`wiki/known_names.json` エイリアステーブル + `resolve_name()` による名寄せ実装（以後同一人物が別名で登録されない）、③「最近の話題」を常に最新3件に保つコンパクション実装（古い分は行動パターンに圧縮）、④cross-referenceを「当日更新ページのみ」の差分処理に変更（出力JSON サイズを更新数に比例させる）。合わせてcore_memory保存の感情スコア閾値を8→7に変更。
