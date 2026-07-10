#!/usr/bin/env python3
"""WP-D モードゲートウェイ テスト（実GPIO・実機・実systemctl不要）。

button_monitor.py は import 時に gpiozero.Button を読むため、sys.modules に
gpiozero スタブを注入してから import する（test_button_modes.py の方式に倣う）。
systemctl 呼び出しは module の subprocess を FakeSubprocess に差し替えて捕捉し、
サービスの active 状態も内部で模擬する（start/stop が実際に状態遷移する）。
状態・トリガーファイルのパスはモジュール定数を tmp ディレクトリに差し替えて注入する。

HTTPレイヤは実際に 127.0.0.1 のエフェメラルポートへサーバを立て、urllib で叩く
（GET / ・GET /mode ・POST /mode を本物の経路で検証）。

検証項目（受け入れ条件2）:
  (a) mode導出（pilot/auto/off・フェイクsystemctl）
  (b) POST遷移3種が正しい systemctl 呼出列 + トリガーファイル生成になる
  (c) 不正body（不正mode値・壊れJSON）で4xx・systemctl未呼出
  (d) GET / が index.html を返す

一時ファイルは tmp ディレクトリ配下のみ（bytecodeキャッシュも無効化）。
実行: python3 gakukoma/tests/test_mode_gateway.py
"""
import os
import sys
import json
import types
import shutil
import tempfile
import threading
import importlib.util
import urllib.request
import urllib.error

sys.dont_write_bytecode = True  # __pycache__ を残さない

CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BM_PATH = os.path.join(CODE_ROOT, "button_monitor.py")


# ---------------------------------------------------------------------------
# gpiozero スタブ（import を通すためだけ）
# ---------------------------------------------------------------------------
def _load_button_monitor():
    if "gpiozero" not in sys.modules:
        gz = types.ModuleType("gpiozero")
        gz.Button = object
        sys.modules["gpiozero"] = gz
    spec = importlib.util.spec_from_file_location("button_monitor", BM_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["button_monitor"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# フェイク systemctl（subprocess.run を差し替え、サービス状態を模擬）
# ---------------------------------------------------------------------------
class _Completed:
    def __init__(self, stdout=""):
        self.stdout = stdout
        self.returncode = 0


class FakeSubprocess:
    def __init__(self, active=()):
        self.active = set(active)
        self.calls = []

    def run(self, cmd, **kwargs):
        verb, service = cmd[1], cmd[2]
        if verb == "is-active":
            return _Completed("active" if service in self.active else "inactive")
        self.calls.append((verb, service))
        if verb == "start":
            self.active.add(service)
        elif verb == "stop":
            self.active.discard(service)
        return _Completed("")


# ---------------------------------------------------------------------------
# 結果集計
# ---------------------------------------------------------------------------
_results = []


def _check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((name, cond, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
# テスト環境（tmp のパス注入 + 実サーバ起動）
# ---------------------------------------------------------------------------
class Env:
    def __init__(self, bm, tmp):
        self.bm = bm
        self.tmp = tmp
        bm.RUN_DIR = tmp
        bm.VOICE_STATE_FILE = os.path.join(tmp, "voice_state")
        bm.WAKE_TRIGGER_FILE = os.path.join(tmp, "wake_trigger")
        bm.SLEEP_TRIGGER_FILE = os.path.join(tmp, "sleep_trigger")
        bm.PILOT_PORT = 8801
        self.server = bm.build_gateway_server(host="127.0.0.1", port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def set_active(self, *services):
        self.bm.subprocess = FakeSubprocess(active=services)
        return self.bm.subprocess

    def set_voice_state(self, s):
        with open(self.bm.VOICE_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(s)

    def clear_triggers(self):
        for p in (self.bm.WAKE_TRIGGER_FILE, self.bm.SLEEP_TRIGGER_FILE):
            try:
                os.remove(p)
            except OSError:
                pass

    def req(self, method, path, body=None):
        # 壊れJSONを送りたいときは body に bytes を渡す（そのまま送出）。
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
        else:
            data = None
        req = urllib.request.Request(self.url(path), data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()


# ---------------------------------------------------------------------------
# (a) mode 導出
# ---------------------------------------------------------------------------
def test_a_derive_mode(env):
    env.set_active("gakukoma-pilot")
    pilot = env.bm.derive_mode()
    env.set_active("gakukoma")
    auto = env.bm.derive_mode()
    env.set_active()
    off = env.bm.derive_mode()
    # 両方 active（異常系）でも pilot を優先
    env.set_active("gakukoma", "gakukoma-pilot")
    both = env.bm.derive_mode()
    ok = pilot == "pilot" and auto == "auto" and off == "off" and both == "pilot"
    _check("(a) mode導出 pilot/auto/off（両activeはpilot優先）", ok,
           f"pilot={pilot} auto={auto} off={off} both={both}")


# ---------------------------------------------------------------------------
# (b) POST 遷移3種
# ---------------------------------------------------------------------------
def test_b_post_transitions(env):
    # pilot: 自律active → stop gakukoma → start pilot
    sp = env.set_active("gakukoma")
    env.clear_triggers()
    code, _ = env.req("POST", "/mode", {"mode": "pilot"})
    pilot_ok = (code == 200 and
                sp.calls == [("stop", "gakukoma"), ("start", "gakukoma-pilot")])

    # auto: pilot active → stop pilot → start gakukoma
    sp = env.set_active("gakukoma-pilot")
    env.clear_triggers()
    code, _ = env.req("POST", "/mode", {"mode": "auto"})
    auto_switch_ok = (code == 200 and
                      sp.calls == [("stop", "gakukoma-pilot"), ("start", "gakukoma")])

    # auto: 既に自律 & 会話中(speaking) → systemctl呼ばず sleep_trigger を生成
    sp = env.set_active("gakukoma")
    env.clear_triggers()
    env.set_voice_state("speaking")
    code, _ = env.req("POST", "/mode", {"mode": "auto"})
    auto_sleep_ok = (code == 200 and sp.calls == [] and
                     os.path.exists(env.bm.SLEEP_TRIGGER_FILE))

    # wake: 何も動いていない → start gakukoma + wake_trigger 生成
    sp = env.set_active()
    env.clear_triggers()
    code, _ = env.req("POST", "/mode", {"mode": "wake"})
    wake_ok = (code == 200 and sp.calls == [("start", "gakukoma")] and
               os.path.exists(env.bm.WAKE_TRIGGER_FILE))

    _check("(b) POST遷移3種の systemctl呼出列 + トリガー生成",
           pilot_ok and auto_switch_ok and auto_sleep_ok and wake_ok,
           f"pilot={pilot_ok} auto_switch={auto_switch_ok} "
           f"auto_sleep={auto_sleep_ok} wake={wake_ok}")


# ---------------------------------------------------------------------------
# (c) 不正body → 4xx・systemctl未呼出
# ---------------------------------------------------------------------------
def test_c_bad_body(env):
    # 不正mode値
    sp = env.set_active()
    env.clear_triggers()
    code_badmode, _ = env.req("POST", "/mode", {"mode": "explode"})
    badmode_ok = (400 <= code_badmode < 500 and sp.calls == [])

    # 壊れJSON
    sp = env.set_active()
    code_badjson, _ = env.req("POST", "/mode", b"{not json")
    badjson_ok = (400 <= code_badjson < 500 and sp.calls == [])

    # mode キー欠落
    sp = env.set_active()
    code_nokey, _ = env.req("POST", "/mode", {"foo": "bar"})
    nokey_ok = (400 <= code_nokey < 500 and sp.calls == [])

    _check("(c) 不正bodyで4xx・systemctl未呼出", badmode_ok and badjson_ok and nokey_ok,
           f"badmode={code_badmode} badjson={code_badjson} nokey={code_nokey}")


# ---------------------------------------------------------------------------
# (d) GET / が index.html を返す
# ---------------------------------------------------------------------------
def test_d_get_index(env):
    env.set_active()
    code, body = env.req("GET", "/")
    # index.html の特徴的な断片（操縦パッド・モードウィジェット）で同定
    ok = (code == 200 and b"stickBase" in body and b"modebox" in body)
    # GET /mode も併せて確認（pilot_port を含む）
    code2, body2 = env.req("GET", "/mode")
    j = json.loads(body2.decode("utf-8"))
    mode_ok = (code2 == 200 and j.get("pilot_port") == 8801 and "mode" in j
               and "voice_state" in j)
    # wake_pending: ウェイク予約の残存を反映する（無=false / 有=true）
    pending_off = (j.get("wake_pending") is False)
    open(env.bm.WAKE_TRIGGER_FILE, "w").close()
    _, body3 = env.req("GET", "/mode")
    pending_on = (json.loads(body3.decode("utf-8")).get("wake_pending") is True)
    env.clear_triggers()
    _check("(d) GET / が index.html を返す（+ GET /mode の形・wake_pending）",
           ok and mode_ok and pending_off and pending_on,
           f"index_code={code} mode_json={j if not mode_ok else 'ok'} "
           f"pending_off={pending_off} pending_on={pending_on}")


def main():
    bm = _load_button_monitor()
    tmp = tempfile.mkdtemp(prefix="gakukoma_gw_test_")
    env = Env(bm, tmp)
    try:
        test_a_derive_mode(env)
        test_b_post_transitions(env)
        test_c_bad_body(env)
        test_d_get_index(env)
    finally:
        env.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"\n=== {passed}/{total} checks passed ===")
    if passed != total:
        print("FAILED checks:")
        for name, ok, detail in _results:
            if not ok:
                print(f"  - {name} :: {detail}")
        sys.exit(1)
    print("ALL PASS")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(2)
