#!/usr/bin/env python3
"""WP-B モード切替（起動ボタン長押し）テスト（実GPIO・実機・systemctl不要）。

button_monitor.py は import 時に gpiozero.Button を読み込むため、sys.modules に
gpiozero スタブを注入してから import する（test_motor_safety.py の方式に倣う）。
systemctl 呼び出しは module の subprocess を FakeSubprocess に差し替えて捕捉し、
サービスの active 状態も内部で模擬する（start/stop が実際に状態遷移する）。
時刻は注入した FakeClock で制御し、time.sleep には触れない。

検証項目（受け入れ条件1）:
  (a) 短押し（< 2秒）→ gakukoma をトグル（起動/停止の回帰なし）
  (b) 長押し（>= 2秒）→ gakukoma-pilot をトグル
  (c) 排他: pilot 起動時に gakukoma が active なら先に stop（逆も同様）
  (d) 判定はボタンを離した時点で行う（押しっぱなしでは発火しない）／
      デバウンス0.3秒でチャタリング（離した直後の再押下）を無視する

一時ファイルは生成しない（bytecodeキャッシュも無効化）。
実行: python3 gakukoma/tests/test_button_modes.py
"""
import os
import sys
import types
import importlib.util

sys.dont_write_bytecode = True  # __pycache__ を残さない

CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BM_PATH = os.path.join(CODE_ROOT, "button_monitor.py")


# ---------------------------------------------------------------------------
# gpiozero スタブ（import を通すためだけ。テストでは Button を使わない）
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
    """button_monitor.subprocess を差し替える。

    systemctl is-active/start/stop を解釈し、内部の active 集合を遷移させる。
    calls には (verb, service) を時系列で記録する。
    """
    def __init__(self, active=()):
        self.active = set(active)
        self.calls = []

    def run(self, cmd, **kwargs):
        verb, service = cmd[1], cmd[2]
        if verb == "is-active":
            # is-active は記録しない（状態の問い合わせなので副作用扱いしない）
            return _Completed("active" if service in self.active else "inactive")
        self.calls.append((verb, service))
        if verb == "start":
            self.active.add(service)
        elif verb == "stop":
            self.active.discard(service)
        return _Completed("")


# ---------------------------------------------------------------------------
# フェイクボタン / クロック
# ---------------------------------------------------------------------------
class FakeButton:
    def __init__(self):
        self.is_pressed = False


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


# ---------------------------------------------------------------------------
# ヘルパ: 1回の「押して離す」動作を模擬（立ち上がり poll → hold → 立ち下がり poll）
# ---------------------------------------------------------------------------
def _press_release(monitor, button, clock, hold_sec):
    button.is_pressed = True
    monitor.poll_once()          # 立ち上がりエッジ（press_start 記録）
    clock.advance(hold_sec)
    button.is_pressed = False
    monitor.poll_once()          # 立ち下がりエッジ（押下時間で判定・発火）


# ---------------------------------------------------------------------------
# テスト本体
# ---------------------------------------------------------------------------
_results = []


def _check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((name, cond, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))


def _make(bm, active=()):
    """FakeSubprocess を差し込んだ ButtonMonitor 一式を作る。"""
    fake_sp = FakeSubprocess(active=active)
    bm.subprocess = fake_sp
    button = FakeButton()
    clock = FakeClock()
    monitor = bm.ButtonMonitor(button, clock=clock, sleep=lambda _s: None)
    return monitor, button, clock, fake_sp


def test_a_short_press_toggles_gakukoma(bm):
    """(a) 短押し（0.2秒）→ gakukoma を start。もう一度でstop（回帰確認）。"""
    old = bm.subprocess
    try:
        monitor, button, clock, sp = _make(bm, active=())
        _press_release(monitor, button, clock, 0.2)     # 起動
        started = sp.calls == [("start", "gakukoma")]

        clock.advance(1.0)  # デバウンス期間外へ
        _press_release(monitor, button, clock, 0.2)     # 停止
        stopped = sp.calls[-1] == ("stop", "gakukoma")
        pilot_untouched = all(s != "gakukoma-pilot" for _, s in sp.calls)
    finally:
        bm.subprocess = old
    _check("(a) 短押しで gakukoma を起動→停止（pilot不介入）",
           started and stopped and pilot_untouched,
           f"calls={sp.calls}")


def test_b_long_press_toggles_pilot(bm):
    """(b) 長押し（2.0秒）→ gakukoma-pilot を start。もう一度でstop。"""
    old = bm.subprocess
    try:
        monitor, button, clock, sp = _make(bm, active=())
        _press_release(monitor, button, clock, 2.0)     # 起動
        started = sp.calls == [("start", "gakukoma-pilot")]

        clock.advance(1.0)
        _press_release(monitor, button, clock, 2.5)     # 停止
        stopped = sp.calls[-1] == ("stop", "gakukoma-pilot")
        gakukoma_untouched = all(s != "gakukoma" for _, s in sp.calls)
    finally:
        bm.subprocess = old
    _check("(b) 長押しで gakukoma-pilot を起動→停止（自律不介入）",
           started and stopped and gakukoma_untouched,
           f"calls={sp.calls}")


def test_c_exclusive_both_directions(bm):
    """(c) 排他: pilot起動時に gakukoma active なら先に stop。逆方向も同様。"""
    old = bm.subprocess
    try:
        # 自律 active の状態で長押し → pilot 起動前に gakukoma stop
        monitor, button, clock, sp = _make(bm, active=("gakukoma",))
        _press_release(monitor, button, clock, 2.0)
        # 期待: stop gakukoma → start gakukoma-pilot（順序も重要）
        pilot_excl = sp.calls == [("stop", "gakukoma"), ("start", "gakukoma-pilot")]

        # 操縦 active の状態で短押し → gakukoma 起動前に pilot stop
        monitor2, button2, clock2, sp2 = _make(bm, active=("gakukoma-pilot",))
        _press_release(monitor2, button2, clock2, 0.2)
        gk_excl = sp2.calls == [("stop", "gakukoma-pilot"), ("start", "gakukoma")]
    finally:
        bm.subprocess = old
    _check("(c) 排他: 起動時に他モードを先に停止（両方向）",
           pilot_excl and gk_excl,
           f"pilot_calls={sp.calls}, gk_calls={sp2.calls}")


def test_d_release_based_and_debounce(bm):
    """(d) 押しっぱなしでは発火しない（離した時点で判定）／デバウンスで再押下無視。"""
    old = bm.subprocess
    try:
        monitor, button, clock, sp = _make(bm, active=())

        # 押しっぱなし（複数poll）でも発火しないこと
        button.is_pressed = True
        monitor.poll_once()
        clock.advance(3.0)
        monitor.poll_once()          # まだ押している → 発火しない
        no_fire_while_held = (sp.calls == [])

        # 離す → ここで初めて発火（長押しなので pilot）
        clock.advance(0.0)
        button.is_pressed = False
        monitor.poll_once()
        fired_on_release = (len(sp.calls) >= 1 and sp.calls[-1][1] == "gakukoma-pilot")
        calls_after_release = len(sp.calls)

        # デバウンス: 離した直後（0.3秒以内）に再度押しても無視される
        clock.advance(0.1)           # last_toggle から 0.1秒（<0.3）
        _press_release(monitor, button, clock, 0.2)
        debounced = (len(sp.calls) == calls_after_release)
    finally:
        bm.subprocess = old
    _check("(d) 離した時点で判定・押下中は不発・デバウンスで再押下無視",
           no_fire_while_held and fired_on_release and debounced,
           f"held_calls_empty={no_fire_while_held}, "
           f"fired_on_release={fired_on_release}, debounced={debounced}, "
           f"calls={sp.calls}")


def main():
    bm = _load_button_monitor()

    test_a_short_press_toggles_gakukoma(bm)
    test_b_long_press_toggles_pilot(bm)
    test_c_exclusive_both_directions(bm)
    test_d_release_based_and_debounce(bm)

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
    except AssertionError as e:
        print("TEST FAILED:", e)
        sys.exit(1)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(2)
