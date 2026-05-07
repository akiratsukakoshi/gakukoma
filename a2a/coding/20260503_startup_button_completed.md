# 物理ボタンによるがくこま起動・停止（コーディング実装 完了報告書）

**作成日:** 2026-05-07
**作成者:** ClaudeCode（直接実装）
**指示書:** `coding/20260503_startup_button_implementation.md`

---

## 実装内容

### 新規作成ファイル

| ファイルパス | 内容 |
|---|---|
| `/home/tukapontas/gakukoma/button_monitor.py` | GPIO23 ボタン監視・gakukoma.service トグル（ポーリング方式） |
| `/etc/systemd/system/gakukoma.service` | がくこまメインサービス定義 |
| `/etc/systemd/system/gakukoma-button.service` | ボタン監視サービス定義（PYTHONUNBUFFERED=1 追加） |

### 変更ファイル

| ファイルパス | 内容 |
|---|---|
| `voice_loop.py` | **変更不要**（既に SIGTERM ハンドラ実装済み） |

---

## テスト結果

| テスト | 内容 | 判定 |
|---|---|---|
| T-1 | systemctl start/stop でがくこまが起動・停止 | ✅ 合格 |
| T-2 | gakukoma-button サービスが active かつログに起動メッセージ | ✅ 合格 |
| T-3 | ボタン1回押しでがくこまが起動（TTS・LED確認） | ✅ 合格 |
| T-4 | ボタン1回押しでがくこまが停止（TTS・LED確認） | ✅ 合格 |
| T-5 | sudo reboot 後にボタン監視サービスが自動復帰・ボタン動作 | ✅ 合格 |

---

## 特記事項

- `voice_loop.py` には既に SIGTERM ハンドラ（`_install_sigterm_handler()`）が実装済みだったため変更不要
- `when_pressed` コールバック方式は lgpio バックエンド + root 実行の組み合わせで反応しなかった。`is_pressed` ポーリング方式（50ms間隔・立ち上がりエッジ検出）に変更して解決
- `gakukoma.service` は `systemctl enable` していない（ボタン手動起動前提）
- `gakukoma-button.service` は `systemctl enable` 済み（Pi 起動時に自動スタート）
