#!/usr/bin/env python3
"""WP3 モーター安全テスト（実機・実GPIO・実API不要）。

move_robot_cmd.py は import時に motor.motor_driver → tb6612_ctrl → gpiozero を
読み込むため、sys.modules に FakeMotorDriver を持つ motor.motor_driver スタブを
注入して import を通す。gakukoma_brain.py も anthropic 依存を避けるため
sys.modules に anthropic スタブを注入し、__new__ でインスタンスだけ生成して
_execute_tool を直接叩く（__init__ の実API/顔認識初期化は通さない）。

検証項目:
  (a) duration=9999 が MAX_MOVE_DURATION(10.0) にクランプされる
  (b) SIGTERM受信で driver.cleanup() が呼ばれる（走行中の強制停止でも止まる）
  (c) 非数値引数で友好的エラー+exit 1（生トレースバックを出さない）
  (d) brain側dispatchで duration=60 → 10 にクランプされる
  (e) brain側 move_robot タイムアウト時に stop コマンドが発行される

一時ファイルは生成しない（bytecodeキャッシュも無効化）。
実行: python3 gakukoma/tests/test_motor_safety.py
"""
import os
import sys
import types
import signal
import subprocess
import importlib.util

sys.dont_write_bytecode = True  # __pycache__ を残さない

# tests/ の親ディレクトリ = コードルート(motor/・brain/ 等がある階層)
CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOVE_CMD_PATH = os.path.join(CODE_ROOT, "motor", "move_robot_cmd.py")
BRAIN_PATH = os.path.join(CODE_ROOT, "brain", "gakukoma_brain.py")


# ---------------------------------------------------------------------------
# フェイクMotorDriver（実GPIOを触らない。呼ばれたメソッドとcleanupを記録）
# ---------------------------------------------------------------------------
_created_drivers = []  # main() が生成したインスタンスを回収する


class FakeMotorDriver:
    def __init__(self):
        self.calls = []
        self.cleaned = False
        self.reached_after_signal = False
        self._raise_signal = False
        _created_drivers.append(self)

    def _record(self, name, **kw):
        self.calls.append((name, kw))
        if self._raise_signal:
            # 走行中(time.sleep相当)にSIGTERMが来た状況を再現
            os.kill(os.getpid(), signal.SIGTERM)
            # SystemExit が上がるのでここには到達しないはず
            self.reached_after_signal = True

    def forward(self, **kw):     self._record("forward", **kw)
    def backward(self, **kw):    self._record("backward", **kw)
    def turn_left(self, **kw):   self._record("turn_left", **kw)
    def turn_right(self, **kw):  self._record("turn_right", **kw)
    def spin_left(self, **kw):   self._record("spin_left", **kw)
    def spin_right(self, **kw):  self._record("spin_right", **kw)
    def stop(self, **kw):        self._record("stop", **kw)

    def cleanup(self):
        self.cleaned = True


def _load_move_cmd():
    """motor.motor_driver をスタブしてから move_robot_cmd を読み込む。"""
    motor_pkg = types.ModuleType("motor")
    motor_pkg.__path__ = []
    sys.modules["motor"] = motor_pkg
    md_mod = types.ModuleType("motor.motor_driver")
    md_mod.MotorDriver = FakeMotorDriver
    sys.modules["motor.motor_driver"] = md_mod

    spec = importlib.util.spec_from_file_location("move_robot_cmd", MOVE_CMD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["move_robot_cmd"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_brain():
    """anthropic をスタブしてから gakukoma_brain を読み込む。"""
    if "anthropic" not in sys.modules:
        anth = types.ModuleType("anthropic")
        anth.Anthropic = object
        sys.modules["anthropic"] = anth
    spec = importlib.util.spec_from_file_location("gakukoma_brain", BRAIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gakukoma_brain"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# フェイクsubprocess（brainの subprocess.run を差し替える）
# ---------------------------------------------------------------------------
class _FakeCompleted:
    def __init__(self, stdout=""):
        self.stdout = stdout
        self.returncode = 0


class FakeSubprocess:
    """gakukoma_brain.subprocess を差し替える。run呼び出しを記録する。

    timeout_on_first=True の場合、最初のrunで TimeoutExpired を送出する。
    TimeoutExpired は本物のクラスを使う（brainがそれを except するため）。
    """
    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self, timeout_on_first=False, stdout="前進 完了"):
        self.calls = []
        self.timeout_on_first = timeout_on_first
        self.stdout = stdout

    def run(self, cmd, **kwargs):
        self.calls.append((list(cmd), kwargs))
        if self.timeout_on_first and len(self.calls) == 1:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))
        return _FakeCompleted(self.stdout)


# ---------------------------------------------------------------------------
# テスト本体
# ---------------------------------------------------------------------------
_results = []


def _check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((name, cond, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))


def test_a_duration_clamped(mc):
    """(a) duration=9999 → MAX_MOVE_DURATION(10.0) にクランプ。"""
    direction, duration, speed, clamped = mc.parse_args(["prog", "forward", "9999"])
    _check("(a) duration=9999 が10.0にクランプ",
           duration == mc.MAX_MOVE_DURATION and clamped is True,
           f"duration={duration}, clamped={clamped}")


def test_b_sigterm_cleanup(mc):
    """(b) 走行中にSIGTERM → SystemExit → finallyのcleanupが呼ばれる。"""
    _created_drivers.clear()
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    raised_system_exit = False
    try:
        # forward呼び出し中にSIGTERMを自分へ送る仕込み
        # main が生成するインスタンスに後付けできないので、生成直後フックする
        orig_init = FakeMotorDriver.__init__

        def hooked_init(self):
            orig_init(self)
            self._raise_signal = True
        FakeMotorDriver.__init__ = hooked_init
        try:
            mc.main(["prog", "forward", "3"])
        except SystemExit:
            raised_system_exit = True
        finally:
            FakeMotorDriver.__init__ = orig_init
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)

    drv = _created_drivers[-1] if _created_drivers else None
    ok = (drv is not None and drv.cleaned and raised_system_exit
          and not drv.reached_after_signal)
    _check("(b) SIGTERM受信でcleanupが呼ばれる",
           ok,
           f"cleaned={getattr(drv,'cleaned',None)}, "
           f"system_exit={raised_system_exit}, "
           f"reached_after={getattr(drv,'reached_after_signal',None)}")


def test_c_non_numeric_arg(mc):
    """(c) 非数値引数 → 友好的エラー+exit 1、driverは生成されない。"""
    _created_drivers.clear()
    code = None
    try:
        mc.main(["prog", "forward", "abc"])
    except SystemExit as e:
        code = e.code
    _check("(c) 非数値引数で exit 1",
           code == 1 and len(_created_drivers) == 0,
           f"exit_code={code}, drivers={len(_created_drivers)}")


def test_d_brain_dispatch_clamp(brain_mod):
    """(d) brain側dispatchで duration=60 → 10 にクランプされる。"""
    brain = brain_mod.GAKUKOMABrain.__new__(brain_mod.GAKUKOMABrain)
    brain._face_recognizer = None
    fake_sp = FakeSubprocess(stdout="前進 完了（10.0秒・速度デフォルト）")
    old_sp = brain_mod.subprocess
    brain_mod.subprocess = fake_sp
    try:
        brain._execute_tool("move_robot", {"direction": "forward", "duration": 60})
    finally:
        brain_mod.subprocess = old_sp

    # 発行された move_robot.sh の duration引数（cmd[2]）が "10.0"
    cmd = fake_sp.calls[0][0] if fake_sp.calls else []
    duration_arg = cmd[2] if len(cmd) > 2 else None
    _check("(d) brain dispatchで duration=60→10にクランプ",
           duration_arg == "10.0",
           f"duration_arg={duration_arg}, cmd={cmd}")


def test_e_brain_timeout_issues_stop(brain_mod):
    """(e) brain側 move_robot タイムアウト時に stop が発行される。"""
    brain = brain_mod.GAKUKOMABrain.__new__(brain_mod.GAKUKOMABrain)
    brain._face_recognizer = None
    fake_sp = FakeSubprocess(timeout_on_first=True)
    old_sp = brain_mod.subprocess
    brain_mod.subprocess = fake_sp
    try:
        ret = brain._execute_tool("move_robot", {"direction": "forward", "duration": 5})
    finally:
        brain_mod.subprocess = old_sp

    # 2回目の run が stop コマンドであること
    stop_issued = (len(fake_sp.calls) >= 2
                   and "stop" in fake_sp.calls[1][0])
    _check("(e) タイムアウト時にstopが発行される",
           stop_issued and "停止済み" in ret,
           f"calls={[c[0] for c in fake_sp.calls]}, ret={ret!r}")


def main():
    mc = _load_move_cmd()
    brain_mod = _load_brain()

    test_a_duration_clamped(mc)
    test_b_sigterm_cleanup(mc)
    test_c_non_numeric_arg(mc)
    test_d_brain_dispatch_clamp(brain_mod)
    test_e_brain_timeout_issues_stop(brain_mod)

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
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("TEST ERROR:", e)
        sys.exit(2)
