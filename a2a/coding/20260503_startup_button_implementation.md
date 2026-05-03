# 物理ボタンによるがくこま起動・停止（コーディング実装）

**作成日:** 2026-05-03
**作成者:** ClaudeCode（司令塔）
**担当:** コーディング担当AI
**前提条件:** Gemini によるボタン配線完了（`hardware/20260503_startup_button_wiring_implementation.md`）

---

## 目的

GPIO23 に接続した物理ボタンのワンプッシュで、がくこまの起動・停止をターミナルなしで切り替えられるようにする。

実現方法:
1. `gakukoma.service` として systemd 登録（`systemctl start/stop` で制御可能にする）
2. `gakukoma-button.service` として常駐するボタン監視スクリプトを作成
3. `voice_loop.py` に SIGTERM ハンドラを追加（`systemctl stop` 時にセッションを正常終了させる）

---

## 現在のアーキテクチャ（必ず把握すること）

```
voice_loop.py
  └─ GAKUKOMABrain.invoke()
       └─ Anthropic API（直接呼び出し）

LED 制御: led_controller.py（gpiozero.RGBLED）
  GPIO17(R) / GPIO27(G) / GPIO22(B)

使用済み GPIO（変更不可）:
  GPIO2/3   : I2C (SDA/SCL)
  GPIO12/13 : PWMA/PWMB（モーター速度）
  GPIO16    : STBY（モーター有効化）
  GPIO17    : LED Red
  GPIO20    : AIN1
  GPIO22    : LED Blue
  GPIO24    : BIN1
  GPIO25    : BIN2
  GPIO26    : AIN2
  GPIO27    : LED Green
```

ボタン割り当て: **GPIO23（Pin 16）** ← 未使用・確定

---

## 実装対象ファイル

### 新規作成

| ファイルパス | 内容 |
|---|---|
| `/etc/systemd/system/gakukoma.service` | がくこまメインサービス定義 |
| `/home/tukapontas/gakukoma/button_monitor.py` | ボタン監視スクリプト |
| `/etc/systemd/system/gakukoma-button.service` | ボタン監視サービス定義 |

### 変更

| ファイルパス | 内容 |
|---|---|
| `/home/tukapontas/gakukoma/voice_loop/voice_loop.py` | SIGTERM ハンドラ追加 |

---

## 実装仕様

### 1. `/etc/systemd/system/gakukoma.service`

```ini
[Unit]
Description=GAKUKOMA Voice Loop
After=network.target sound.target

[Service]
ExecStart=/usr/bin/python3 /home/tukapontas/gakukoma/voice_loop/voice_loop.py
WorkingDirectory=/home/tukapontas/gakukoma/voice_loop
User=tukapontas
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM
Environment=PYTHONPATH=/home/tukapontas/gakukoma

[Install]
WantedBy=multi-user.target
```

**注意**: `WantedBy=multi-user.target` にしているが `systemctl enable gakukoma` は **しない**（ボタン操作で手動起動が前提。自動起動は不要）。

---

### 2. `/home/tukapontas/gakukoma/button_monitor.py`

```python
#!/usr/bin/env python3
"""
GAKUKOMA 物理ボタンモニター
GPIO23 のボタン押下で gakukoma.service をトグル起動/停止する。
gakukoma-button.service から root で起動される。
"""
import subprocess
import sys
from gpiozero import Button
from signal import pause

BUTTON_GPIO = 23
BOUNCE_TIME = 0.3  # デバウンス時間（秒）


def is_gakukoma_running() -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", "gakukoma"],
        capture_output=True, text=True
    )
    return result.stdout.strip() == "active"


def toggle_gakukoma():
    if is_gakukoma_running():
        print("ボタン: がくこまを停止します...")
        subprocess.run(["systemctl", "stop", "gakukoma"])
        print("ボタン: 停止完了")
    else:
        print("ボタン: がくこまを起動します...")
        subprocess.run(["systemctl", "start", "gakukoma"])
        print("ボタン: 起動完了")


def main():
    btn = Button(BUTTON_GPIO, pull_up=True, bounce_time=BOUNCE_TIME)
    btn.when_pressed = toggle_gakukoma
    print(f"ボタンモニター起動 (GPIO{BUTTON_GPIO})")
    pause()  # イベントループ維持


if __name__ == "__main__":
    main()
```

---

### 3. `/etc/systemd/system/gakukoma-button.service`

```ini
[Unit]
Description=GAKUKOMA Button Monitor
After=multi-user.target

[Service]
ExecStart=/usr/bin/python3 /home/tukapontas/gakukoma/button_monitor.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**注意**: `User=` を指定しない（root で動作）。root であることで `systemctl start/stop gakukoma` が sudo なしで実行可能。

---

### 4. `voice_loop.py` への SIGTERM ハンドラ追加

`systemctl stop gakukoma` は SIGTERM を送信する。現状は KeyboardInterrupt（Ctrl+C）のみ捕捉しているため、SIGTERM では `end_session()` が呼ばれずセッション（raw log）が失われる。

**変更箇所**: `voice_loop.py` の `import` セクション末尾に以下を追加する。

```python
import signal

def _install_sigterm_handler():
    """SIGTERM を KeyboardInterrupt に変換して正常終了フローを通す"""
    def _handler(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _handler)
```

そして `main()` 関数の先頭で呼び出す:

```python
def main():
    _install_sigterm_handler()   # ← この行を追加
    config = load_config()
    loop = VoiceLoop(config)
    loop.run()
```

---

## セットアップ手順（実装後に実行する）

```bash
# 1. サービスファイルを systemd に登録
sudo systemctl daemon-reload

# 2. ボタン監視サービスを有効化・起動（Pi 起動時に自動スタート）
sudo systemctl enable gakukoma-button
sudo systemctl start gakukoma-button

# 3. サービス起動を確認
sudo systemctl status gakukoma-button
```

---

## テスト手順

### T-1: systemd によるがくこま起動・停止

```bash
sudo systemctl start gakukoma
sleep 5
sudo systemctl status gakukoma   # Active: active (running) を確認
sudo systemctl stop gakukoma
sleep 3
sudo systemctl status gakukoma   # Active: inactive を確認
```

**合格条件**: 起動後に TTS「がくこまが起動しました」が聞こえ、停止後に TTS「がくこまをシャットダウンします」が聞こえること

### T-2: ボタン監視サービスが起動しているか確認

```bash
sudo systemctl status gakukoma-button
```

**合格条件**: `Active: active (running)` かつ `ボタンモニター起動 (GPIO23)` がログに出ること

### T-3: 物理ボタンで起動

がくこまが停止中の状態でボタンを1回押す。

**合格条件**: TTS「がくこまが起動しました」が流れ、LEDが青点灯（idle）になること

### T-4: 物理ボタンで停止

がくこまが起動中の状態でボタンを1回押す。

**合格条件**: TTS「がくこまをシャットダウンします」が流れ、LEDが消灯すること

### T-5: Pi 再起動後にボタン監視サービスが自動復帰するか確認

```bash
sudo reboot
# 再起動後
sudo systemctl status gakukoma-button   # active を確認
```

**合格条件**: 再起動後もボタン監視サービスが自動起動し、ボタンでがくこまをトグルできること

---

## 完了報告

`coding/20260503_startup_button_completed.md` を作成して ClaudeCode に報告すること。
T-1〜T-5 の合否と実機確認結果を記載すること。
