# ロボット仕様書：GAKUKOMA（がくこま） Ver. 1.4

「身体性を持つ自律エージェント（OpenClaw）」のプロトタイプ。
段階的な開発（Phased Development）により、知能から身体へと拡張する。

## 1. 基本コンセプト
- **脳 (Brain):** Raspberry Pi 5 (16GB) による高度な推論とエージェント動作
- **知覚 (Perception):** 視覚（OpenCV）と聴覚（Faster-Whisper）の統合
- **身体 (Body):** 金属製タンクシャーシ（YP100）による不整地走破
- **干渉 (Interference):** Piperによる発話とグリッパーによる物理操作

## 2. フェーズ別開発ロードマップ

### Phase 1: 脳の覚醒と対話（Brain & Voice）
まずは「動かないが賢い」デスクトップ・エージェントとして構築する。
- **目標:** OpenClaw環境の構築と、音声による意思疎通の実現。
- **主要パーツ:** Raspberry Pi 5 (16GB), アクティブクーラー, 64GB microSD (A2), USBマイク, スピーカー。
- **ソフトウェア:** Raspberry Pi OS (64-bit), OpenClaw / Claude Code, Faster-Whisper (STT), Piper (TTS)。

### Phase 2: 視覚と表情（Eyes & Neck）
周囲を認識し、特定の対象を追う機能を実装する。
- **目標:** 顔認識、物体検出、およびサーボによる首振り動作。
- **主要パーツ:** 広角USB Webカメラ, アルミ合金製パンチルト台座, DS3218高トルクサーボ（20kg-cm/金属ギア）×2, PCA9685 (サーボドライバ)。
  - ⚡ **2026-04-02変更:** パン・チルト機構をSG90+プラスチック台座 → DS3218+アルミ合金台座に強化。
- **ソフトウェア:** OpenCV, Arucoマーカー追跡, `look_at_user()` ツール。

### Phase 3: 大地への進出（Body & Power）
完全自律走行と、ACアダプタからの独立。
- **目標:** タンクシャーシの駆動と、独立電源系統（系統A/B）の確立。
- **主要パーツ:** SainSmart金属製タンクシャーシ（YP100）, TB6612FNG (モータードライバ), Waveshare UPS HAT(B) + NCR18650×2 (系統A), 11.1V 3S Li-ionパック (系統B), LM2596 降圧モジュール（6.0V/DS3218専用）, 1000μF平滑コンデンサ。
- **ソフトウェア:** `move_robot()` ツール, モーター制御スクリプト。

### Phase 4: 物理干渉（Hand）
物理的な物体に触れ、操作する機能を追加する。
- **目標:** グリッパーによる把持操作。
- **主要パーツ:** ロボットグリッパーキット（SG90駆動）。
- **ソフトウェア:** `pick_up_object()` 等の拡張ツール定義。

## 3. 共通ハードウェア・ソフトウェア仕様

### 3.1 制御系
- **計算機:** Raspberry Pi 5 (16GBモデル)
- **冷却:** 専用アクティブクーラー（必須）
- **ストレージ:** 64GB microSD (UHS-I U3, A2) ※将来的にNVMe SSD拡張を推奨

### 3.2 電源系統（Phase 3より導入）
- **系統A（脳用）:** Waveshare UPS HAT(B) + NCR18650生セル（65mm）×2 → Pi5へ5V/5A供給（Pogoピン経由・GPIO非占有）
- **系統B（動力用）:** 11.1V 3S Li-ionパック
  - → LM2596（**6.0V固定設定**）→ PCA9685 V+端子 → DS3218サーボ×2（+1000μFコンデンサ並列）
  - → TB6612FNG VM端子へ直結（DCモーター駆動）
- **共通接地:** 系統AとBのGNDは必ず共通にすること（未接地の場合、GPIO誤動作・通信エラーの原因となる）
- **EEPROM設定:** Pi5の `PSU_MAX_CURRENT=5000` を設定してUPS HAT(B)の5A給電を安定化させること

### 3.3 開発手法
- **Vibe Coding:** コーディング担当AI（Antigravity / Cline+GLM / Codex / Claudeサブエージェント等）を活用し、モジュール単位で迅速に実装
- **zRAM:** メモリ16GBを活かすためzRAMを有効化し、スワップを抑制

## 4. ツール定義 (OpenClaw追加分)
1. `see_around()`: 周囲をスキャンし画像を解析
2. `move_robot(direction, duration)`: 指定方向に移動
3. `listen_voice()`: 音声をテキスト化
4. `speak_text(text)`: 合成音声で発話
5. `look_at_user()`: ユーザーに顔（カメラ）を向ける