#!/usr/bin/env python3
"""WP-K 「おはなし」直行起動テスト（オーディオHW不要）。

スマホの「おはなし」ボタン = ゲートウェイが gakukoma.service を起動して
wake_trigger を書く。voice_loop はウェイク注入つき起動を検知したら、
「がくこまが起動しました」を省略して「はい、なんでしょう」だけで
会話待ち受けへ直行する（返事はモデル読込前に発話される）。

スタブ注入・ファイルパス差し替えは test_voice_loop_triggers.py の流儀に倣う。

検証項目:
  (a) _fresh_trigger_pending: 新鮮=True(消費しない) / 陳腐=False / 無し=False
  (b) _startup_greeting(ウェイク注入つき): 起動アナウンス無し・返事の二重発話無し・
      トリガー消費・listening直行・new_session
  (c) _startup_greeting(通常起動): 従来どおり「がくこまが起動しました。」のみ
  (d) _enter_active_from_wake() は既定で従来どおり返事する（後方互換）

実行: python3 gakukoma/tests/test_wake_direct_start.py
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


class FakeLed:
    def set_state(self, s):
        pass


class FakeBrain:
    def __init__(self):
        self.new_sessions = 0

    def new_session(self):
        self.new_sessions += 1


class FakeTTS:
    def __init__(self):
        self.said = []

    def speak(self, text):
        self.said.append(text)


def _make_vl(mod, wake_on_start=False):
    VoiceLoop = mod.VoiceLoop
    vl = VoiceLoop.__new__(VoiceLoop)
    vl.config = {}
    vl.state = "idle"
    vl.led = FakeLed()
    vl.brain = FakeBrain()
    vl.tts_engine = FakeTTS()
    vl._gesture = None
    vl._idle_start = None
    vl._wake_on_start = wake_on_start
    return vl


def run():
    mod = _load_voice_loop()
    tmp = tempfile.mkdtemp(prefix="gakukoma_wake_start_")
    mod.RUN_DIR = tmp
    mod.VOICE_STATE_FILE = os.path.join(tmp, "voice_state")
    mod.WAKE_TRIGGER_FILE = os.path.join(tmp, "wake_trigger")
    mod.SLEEP_TRIGGER_FILE = os.path.join(tmp, "sleep_trigger")

    results = []
    try:
        # --- (a) _fresh_trigger_pending は peek のみ ------------------------
        assert mod._fresh_trigger_pending(mod.WAKE_TRIGGER_FILE) is False, \
            "(a) ファイル無しで True になった"
        open(mod.WAKE_TRIGGER_FILE, "w").close()
        assert mod._fresh_trigger_pending(mod.WAKE_TRIGGER_FILE) is True, \
            "(a) 新鮮なトリガーを検知できない"
        assert os.path.exists(mod.WAKE_TRIGGER_FILE), \
            "(a) peek のはずが消費(削除)された"
        old = time.time() - (mod.TRIGGER_TTL_SEC + 60)
        os.utime(mod.WAKE_TRIGGER_FILE, (old, old))
        assert mod._fresh_trigger_pending(mod.WAKE_TRIGGER_FILE) is False, \
            "(a) 陳腐化トリガーで True になった"
        os.remove(mod.WAKE_TRIGGER_FILE)
        results.append("(a) _fresh_trigger_pending は peek のみ: PASS")

        # --- (b) ウェイク注入つき起動は直行する ----------------------------
        vl = _make_vl(mod, wake_on_start=True)
        open(mod.WAKE_TRIGGER_FILE, "w").close()
        vl._startup_greeting()
        assert "がくこまが起動しました。" not in vl.tts_engine.said, \
            "(b) 起動アナウンスが省略されていない"
        assert "はい、なんでしょう" not in vl.tts_engine.said, \
            "(b) 返事が二重発話されている（__init__で発話済みの想定）"
        assert not os.path.exists(mod.WAKE_TRIGGER_FILE), \
            "(b) wake_trigger が消費されていない"
        assert vl.state == "listening", f"(b) state={vl.state}（listening直行でない）"
        assert vl.brain.new_sessions == 1, "(b) new_session が呼ばれていない"
        results.append("(b) ウェイク注入つき起動は会話待ち受けへ直行: PASS")

        # --- (c) 通常起動は従来どおり --------------------------------------
        vl = _make_vl(mod, wake_on_start=False)
        vl._startup_greeting()
        assert vl.tts_engine.said == ["がくこまが起動しました。"], \
            f"(c) said={vl.tts_engine.said}"
        assert vl.state == "idle", f"(c) state={vl.state}"
        assert vl.brain.new_sessions == 0, "(c) 通常起動で new_session された"
        results.append("(c) 通常起動は従来どおり起動アナウンス: PASS")

        # --- (d) _enter_active_from_wake は既定で返事する（後方互換） ------
        vl = _make_vl(mod)
        vl._enter_active_from_wake()
        assert vl.tts_engine.said == ["はい、なんでしょう"], \
            f"(d) said={vl.tts_engine.said}"
        assert vl.state == "listening", f"(d) state={vl.state}"
        results.append("(d) _enter_active_from_wake の後方互換: PASS")

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
