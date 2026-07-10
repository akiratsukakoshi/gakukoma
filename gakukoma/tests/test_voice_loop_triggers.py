#!/usr/bin/env python3
"""WP-D voice_loop 状態ファイル + ウェイク/スリープ注入テスト（オーディオHW不要）。

voice_loop.py はimport時に numpy / sounddevice / webrtcvad / faster_whisper /
gakukoma_brain / tts / led_controller / servo.* を読み込むため、sys.modules へ
最小スタブを注入して import を通す（test_voice_loop_wp4.py の流儀に倣う）。
VoiceLoop は __new__ で生成し、テストに必要な属性（fake led/brain/tts）だけ差し込む。
状態・トリガーファイルのパスはモジュール定数を tmp に差し替えて注入する。

検証項目（受け入れ条件3）:
  (a) wake_trigger 消費でウェイク遷移（返事 + new_session + listening）が起きる
  (b) sleep_trigger 消費で idle へ畳む（end_session + idle）
  (c) 状態ファイルが遷移(_set_state)で書き換わる

一時ファイルは tmp 配下のみ（bytecodeキャッシュも無効化）。
実行: python3 gakukoma/tests/test_voice_loop_triggers.py
"""
import os
import sys
import time
import types
import shutil
import tempfile
import importlib.util

sys.dont_write_bytecode = True  # __pycache__ を残さない

VOICE_LOOP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "voice_loop", "voice_loop.py",
)


# ---------------------------------------------------------------------------
# import 依存スタブ（test_voice_loop_wp4.py と同型）
# ---------------------------------------------------------------------------
def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _install_stubs():
    np = types.ModuleType("numpy")
    np.float32 = float
    np.mean = lambda a: 0.0
    np.abs = lambda a: a
    sys.modules["numpy"] = np
    _stub("sounddevice", InputStream=lambda **kw: None)
    _stub("webrtcvad", Vad=lambda *a, **k: object())
    _stub("faster_whisper", WhisperModel=object)
    _stub("gakukoma_brain", GAKUKOMABrain=object)
    _stub("led_controller", LedController=object)
    tts_pkg = _stub("tts")
    tts_pkg.__path__ = []
    _stub("tts.speak_text", OpenJTalkTTS=object)
    servo_pkg = _stub("servo")
    servo_pkg.__path__ = []
    _stub("servo.pan_tilt", PanTiltController=object)
    _stub("servo.gesture_controller", GestureController=object)


def _load_voice_loop():
    _install_stubs()
    spec = importlib.util.spec_from_file_location("voice_loop", VOICE_LOOP_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["voice_loop"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# フェイク協調オブジェクト
# ---------------------------------------------------------------------------
class FakeLed:
    def __init__(self):
        self.states = []

    def set_state(self, s):
        self.states.append(s)


class FakeBrain:
    def __init__(self):
        self.new_sessions = 0
        self.end_sessions = 0

    def new_session(self):
        self.new_sessions += 1

    def end_session(self):
        self.end_sessions += 1


class FakeTTS:
    def __init__(self):
        self.said = []

    def speak(self, text):
        self.said.append(text)


def _make_vl(mod):
    VoiceLoop = mod.VoiceLoop
    vl = VoiceLoop.__new__(VoiceLoop)
    vl.config = {}
    vl.state = "idle"
    vl.led = FakeLed()
    vl.brain = FakeBrain()
    vl.tts_engine = FakeTTS()
    vl._gesture = None
    vl._idle_start = None
    return vl


def _read_state(mod):
    with open(mod.VOICE_STATE_FILE, encoding="utf-8") as f:
        return f.read().strip()


# ---------------------------------------------------------------------------
# テスト本体
# ---------------------------------------------------------------------------
def run():
    mod = _load_voice_loop()
    tmp = tempfile.mkdtemp(prefix="gakukoma_vl_trig_")
    mod.RUN_DIR = tmp
    mod.VOICE_STATE_FILE = os.path.join(tmp, "voice_state")
    mod.WAKE_TRIGGER_FILE = os.path.join(tmp, "wake_trigger")
    mod.SLEEP_TRIGGER_FILE = os.path.join(tmp, "sleep_trigger")

    results = []
    try:
        # --- (a) wake_trigger 消費でウェイク遷移 --------------------------
        vl = _make_vl(mod)
        open(mod.WAKE_TRIGGER_FILE, "w").close()
        consumed = vl._consume_trigger(mod.WAKE_TRIGGER_FILE)
        assert consumed is True, "(a) wake_trigger を消費できていない"
        assert not os.path.exists(mod.WAKE_TRIGGER_FILE), "(a) wake_trigger が削除されていない"
        vl._enter_active_from_wake()
        assert vl.state == "listening", f"(a) state={vl.state}"
        assert vl.brain.new_sessions == 1, "(a) new_session が呼ばれていない"
        assert "はい、なんでしょう" in vl.tts_engine.said, "(a) 返事をしゃべっていない"
        assert _read_state(mod) == "listening", "(a) 状態ファイルが listening でない"
        # 二重消費されないこと
        assert vl._consume_trigger(mod.WAKE_TRIGGER_FILE) is False, "(a) 二重消費された"
        results.append("(a) wake_trigger 消費でウェイク遷移: PASS")

        # --- (b) sleep_trigger 消費で idle へ畳む -------------------------
        vl = _make_vl(mod)
        vl._set_state("speaking")  # 会話中の状態から
        open(mod.SLEEP_TRIGGER_FILE, "w").close()
        consumed = vl._consume_trigger(mod.SLEEP_TRIGGER_FILE)
        assert consumed is True, "(b) sleep_trigger を消費できていない"
        assert not os.path.exists(mod.SLEEP_TRIGGER_FILE), "(b) sleep_trigger が削除されていない"
        vl._collapse_to_idle("じゃあまたね")
        assert vl.state == "idle", f"(b) state={vl.state}"
        assert vl.brain.end_sessions == 1, "(b) end_session が呼ばれていない"
        assert _read_state(mod) == "idle", "(b) 状態ファイルが idle でない"
        results.append("(b) sleep_trigger 消費で idle へ畳む: PASS")

        # --- (c) 状態ファイルが遷移で書き換わる ---------------------------
        vl = _make_vl(mod)
        vl._set_state("thinking")
        s1 = _read_state(mod)
        vl._set_state("idle")
        s2 = _read_state(mod)
        assert s1 == "thinking" and s2 == "idle", f"(c) s1={s1} s2={s2}"
        # LED も同期して呼ばれている（単一チョークポイント）
        assert vl.led.states[-2:] == ["thinking", "idle"], f"(c) led={vl.led.states}"
        results.append("(c) 状態ファイルが遷移で書き換わる: PASS")

        # --- (d) 鮮度切れの残留トリガーは消費せず捨てる -------------------
        vl = _make_vl(mod)
        open(mod.WAKE_TRIGGER_FILE, "w").close()
        old = time.time() - (mod.TRIGGER_TTL_SEC + 60)
        os.utime(mod.WAKE_TRIGGER_FILE, (old, old))
        consumed = vl._consume_trigger(mod.WAKE_TRIGGER_FILE)
        assert consumed is False, "(d) 陳腐化トリガーが消費された"
        assert not os.path.exists(mod.WAKE_TRIGGER_FILE), "(d) 陳腐化トリガーが削除されていない"
        # 鮮度内なら従来どおり消費される
        open(mod.WAKE_TRIGGER_FILE, "w").close()
        assert vl._consume_trigger(mod.WAKE_TRIGGER_FILE) is True, "(d) 新鮮なトリガーが消費されない"
        results.append("(d) 鮮度切れトリガーは消費せず捨てる: PASS")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n".join(results))
    print("\nALL 4 CHECKS PASSED")


if __name__ == "__main__":
    try:
        run()
    except AssertionError as e:
        print("TEST FAILED:", e)
        sys.exit(1)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(2)
    sys.exit(0)
