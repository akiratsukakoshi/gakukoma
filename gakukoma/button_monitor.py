#!/usr/bin/env python3
"""
GAKUKOMA 物理ボタンモニター（GPIO23）

押下時間でモードを切り替える:
  - 短押し（< 2秒）: 自律モード gakukoma.service をトグル起動/停止（従来動作）
  - 長押し（>= 2秒）: 操縦モード gakukoma-pilot.service をトグル起動/停止

両モードは相互排他。あるモードを「起動」するとき、もう一方が active なら
先に stop してから起動する。判定はボタンを「離した時点」の押下時間で行い、
チャタリング対策のデバウンス（0.3秒）は現行どおり維持する。

gakukoma-button.service から root で起動される。
"""
import os
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from gpiozero import Button

BUTTON_GPIO = 23
DEBOUNCE_SEC = 0.3     # デバウンス時間（秒）: 直近のトグル後この時間は次の押下開始を無視
POLL_INTERVAL = 0.05   # ポーリング間隔（秒）
LONG_PRESS_SEC = 2.0   # この時間以上の押下を「長押し」と判定（操縦モード）

GAKUKOMA_SERVICE = "gakukoma"            # 自律モード
PILOT_SERVICE = "gakukoma-pilot"         # 操縦モード


def _is_active(service: str) -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", service],
        capture_output=True, text=True
    )
    return result.stdout.strip() == "active"


def _start(service: str):
    subprocess.run(["systemctl", "start", service])


def _stop(service: str):
    subprocess.run(["systemctl", "stop", service])


def _toggle_service(target: str, other: str, label: str):
    """target をトグル。起動時は排他のため other が active なら先に停止する。"""
    if _is_active(target):
        print(f"ボタン: {label}を停止します...", flush=True)
        _stop(target)
        print(f"ボタン: {label} 停止完了", flush=True)
    else:
        if _is_active(other):
            print(f"ボタン: 排他のため他モードを停止します...", flush=True)
            _stop(other)
        print(f"ボタン: {label}を起動します...", flush=True)
        _start(target)
        print(f"ボタン: {label} 起動完了", flush=True)


def toggle_gakukoma():
    """自律モード(gakukoma)をトグル。起動時は操縦モードを停止する。"""
    _toggle_service(GAKUKOMA_SERVICE, PILOT_SERVICE, "自律モード（がくこま）")


def toggle_pilot():
    """操縦モード(gakukoma-pilot)をトグル。起動時は自律モードを停止する。"""
    _toggle_service(PILOT_SERVICE, GAKUKOMA_SERVICE, "操縦モード")


# ===========================================================================
# 常設HTTPゲートウェイ（WP-D）
#
# GPIOポーリングとは別スレッドで 0.0.0.0:GATEWAY_PORT に立てる。自律モード中でも
# スマホから (1)現在モードの可視化 (2)3状態(そうじゅう/じりつ/おはなし)への切替 を
# 可能にする。切替は既存の排他トグルを流用した固定遷移のみで、入力値を systemctl へ
# 渡さない（ホワイトリスト2サービス gakukoma / gakukoma-pilot 固定）。
# GPIOポーリングループ（ButtonMonitor）は一切改変しない。
# ===========================================================================
GATEWAY_PORT = 8800          # 常設ゲートウェイのHTTPポート（操縦サーバは8801へ移管）
DEFAULT_PILOT_PORT = 8801    # config が読めないときのフォールバック

# 状態・トリガーファイル（voice_loop と共有）。テスト容易性のため定数化し注入可能に。
RUN_DIR = "/run/gakukoma"
RUN_OWNER = "tukapontas"     # voice_loop は tukapontas で走るため所有者を合わせる
VOICE_STATE_FILE = os.path.join(RUN_DIR, "voice_state")
WAKE_TRIGGER_FILE = os.path.join(RUN_DIR, "wake_trigger")
SLEEP_TRIGGER_FILE = os.path.join(RUN_DIR, "sleep_trigger")

# UI（index.html）は操縦サーバと同じものをゲートウェイからも配る。
GATEWAY_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML_PATH = os.path.join(GATEWAY_DIR, "pilot", "index.html")
CONFIG_PATH = os.path.join(GATEWAY_DIR, "voice_loop", "config.yaml")

# GET /mode 応答で返す操縦ポート。main() が config から設定する（既定はフォールバック）。
PILOT_PORT = DEFAULT_PILOT_PORT


def load_pilot_port(config_path=None):
    """config.yaml の pilot.port を読む。PyYAML未導入や読取失敗なら 8801。"""
    if config_path is None:
        config_path = CONFIG_PATH
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return int((cfg.get("pilot") or {}).get("port", DEFAULT_PILOT_PORT))
    except Exception:
        return DEFAULT_PILOT_PORT


def ensure_run_dir():
    """RUN_DIR を作成し tukapontas 所有にする（root常駐の起動時に一度）。失敗は致命にしない。"""
    try:
        os.makedirs(RUN_DIR, exist_ok=True)
        import pwd
        info = pwd.getpwnam(RUN_OWNER)
        os.chown(RUN_DIR, info.pw_uid, info.pw_gid)
    except Exception as e:  # 権限/環境差異で失敗しても監視自体は続ける
        print(f"ゲートウェイ: RUN_DIR 準備に失敗（無視）: {e}", flush=True)


def derive_mode():
    """systemctl is-active 2発から現在モードを導出。pilot 優先 → auto → off。"""
    if _is_active(PILOT_SERVICE):
        return "pilot"
    if _is_active(GAKUKOMA_SERVICE):
        return "auto"
    return "off"


def read_voice_state():
    """voice_state ファイルの中身（状態文字列）を返す。無ければ None。"""
    try:
        with open(VOICE_STATE_FILE, encoding="utf-8") as f:
            s = f.read().strip()
        return s or None
    except OSError:
        return None


def _write_trigger(path):
    """トリガーファイルを作る（存在=要求。読んだ側が消費削除）。失敗は無視。"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("1")
    except OSError as e:
        print(f"ゲートウェイ: トリガー書込失敗（無視）: {e}", flush=True)


def apply_mode(requested):
    """3状態への固定遷移。requested は 'pilot'|'auto'|'wake' のみ。

    不正値は ValueError を送出し systemctl を一切呼ばない。入力値を systemctl へ渡さず、
    ホワイトリスト2サービス（gakukoma / gakukoma-pilot）だけを操作する。
    """
    if requested == "pilot":
        # 排他: gakukoma 停止 → pilot 起動（既に pilot active なら no-op）
        if _is_active(PILOT_SERVICE):
            return
        if _is_active(GAKUKOMA_SERVICE):
            _stop(GAKUKOMA_SERVICE)
        _start(PILOT_SERVICE)
    elif requested == "auto":
        if _is_active(PILOT_SERVICE):
            # 操縦中 → 停止して自律を起動
            _stop(PILOT_SERVICE)
            _start(GAKUKOMA_SERVICE)
        elif _is_active(GAKUKOMA_SERVICE):
            # 既に自律。会話中(listening/thinking/speaking)ならスリープtrigger、
            # idle なら何もしない。
            if read_voice_state() in ("listening", "thinking", "speaking"):
                _write_trigger(SLEEP_TRIGGER_FILE)
        else:
            # 両方 inactive → 自律を起動
            _start(GAKUKOMA_SERVICE)
    elif requested == "wake":
        # gakukoma を(必要なら排他起動して)active にし、ウェイクtriggerを書く。
        # 起動直後でもファイルは残るので IDLE ループ到達時に発火する。
        if _is_active(PILOT_SERVICE):
            _stop(PILOT_SERVICE)
        if not _is_active(GAKUKOMA_SERVICE):
            _start(GAKUKOMA_SERVICE)
        _write_trigger(WAKE_TRIGGER_FILE)
    else:
        raise ValueError("bad mode: %r" % (requested,))


class _GatewayHandler(BaseHTTPRequestHandler):
    """stdlib のみの最小HTTPハンドラ。GET / ・GET /mode ・POST /mode を捌く。"""
    server_version = "GakukomaGateway/1.0"

    def log_message(self, *args):  # noqa: A003 — アクセスログは黙らせる（journal保護）
        pass

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _serve_index(self):
        try:
            with open(INDEX_HTML_PATH, "rb") as f:
                body = f.read()
            code, ctype = 200, "text/html; charset=utf-8"
        except OSError:
            body, code, ctype = b"index.html not found", 500, "text/plain; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._serve_index()
        elif path == "/mode":
            self._send_json(200, {
                "mode": derive_mode(),
                "voice_state": read_voice_state(),
                "pilot_port": PILOT_PORT,
                # ウェイク予約が未消費で残っているか。自律モードの起動(Whisper読込)は
                # 数十秒かかり、その間トリガーは未消費のまま。UIはこれを見て
                # 「おはなし じゅんびちゅう…」を出す。
                "wake_pending": os.path.exists(WAKE_TRIGGER_FILE),
            })
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/mode":
            self._send_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            data = json.loads(raw.decode("utf-8"))
            requested = data["mode"]
        except Exception:
            self._send_json(400, {"error": "bad_request"})
            return
        try:
            apply_mode(requested)
        except ValueError:
            self._send_json(400, {"error": "bad_mode"})
            return
        self._send_json(200, {"ok": True, "mode": derive_mode()})


def build_gateway_server(host="0.0.0.0", port=None):
    """ゲートウェイHTTPサーバを作る（serve_forever は呼び出し側 / テストで注入可能）。"""
    if port is None:
        port = GATEWAY_PORT
    return ThreadingHTTPServer((host, port), _GatewayHandler)


def start_gateway():
    """ゲートウェイをデーモンスレッドで起動。GPIOループはメインスレッドのまま無改変。"""
    server = build_gateway_server()
    t = threading.Thread(target=server.serve_forever, name="gateway", daemon=True)
    t.start()
    print(f"ゲートウェイ起動 0.0.0.0:{GATEWAY_PORT}（UI配信 + /mode 可視化・切替）", flush=True)
    return server


class ButtonMonitor:
    """ポーリングでボタン押下時間を測り、離した時点でモードをトグルする。

    実機依存を避けるため button / clock / sleep を注入可能にしてある
    （テストはフェイクを渡して poll_once を直接駆動する）。
    """

    def __init__(self, button, clock=time.monotonic, sleep=time.sleep):
        self.button = button
        self.clock = clock
        self.sleep = sleep
        self._last_state = False        # False = 未押下
        self._press_start = None        # 立ち上がり時刻（未押下中は None）
        self._last_toggle = float("-inf")

    def poll_once(self):
        pressed = self.button.is_pressed
        now = self.clock()

        # 立ち上がりエッジ（未押下→押下）かつ直近トグルからデバウンス期間外
        if pressed and not self._last_state and (now - self._last_toggle) > DEBOUNCE_SEC:
            self._press_start = now

        # 立ち下がりエッジ（押下→未押下）: 離した時点の押下時間で判定
        elif (not pressed) and self._last_state and self._press_start is not None:
            held = now - self._press_start
            if held >= LONG_PRESS_SEC:
                toggle_pilot()
            else:
                toggle_gakukoma()
            self._last_toggle = now
            self._press_start = None

        self._last_state = pressed

    def run(self):
        while True:
            self.poll_once()
            self.sleep(POLL_INTERVAL)


def main():
    global PILOT_PORT
    ensure_run_dir()
    PILOT_PORT = load_pilot_port()
    start_gateway()          # 別スレッドの常設ゲートウェイ（GPIOループとは独立）
    btn = Button(BUTTON_GPIO, pull_up=True, bounce_time=None)
    print(f"ボタンモニター起動 (GPIO{BUTTON_GPIO})", flush=True)
    ButtonMonitor(btn).run()


if __name__ == "__main__":
    main()
