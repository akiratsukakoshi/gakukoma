#!/usr/bin/env python3
"""WP4 ロジック検証テスト（オーディオHW・sounddevice・whisper不要）。

voice_loop.py はimport時に numpy / sounddevice / webrtcvad / faster_whisper /
gakukoma_brain / tts / led_controller / servo.* を読み込むため、
sys.modules へ最小スタブを注入して import を通す。
VoiceLoop は __new__ で生成し、テストに必要な属性だけ差し込む方式。

検証項目:
  (a) 無音ストリームで record_wakeword_candidate がタイムアウトし None を返す
  (b) 音量トリガー後は既存どおりフレーム列(list[bytes])を返す
  (c) 常に is_speech=False の fake vad で record_vad_from_stream が
      no_speech_timeout_sec 相当で打ち切られ NO_SPEECH_TIMEOUT を返す
  (d) 発話開始→無音で従来どおり録音停止しフレームを返す

一時ファイルは一切生成しない（bytecodeキャッシュも無効化）。
実行: python3 tests/test_voice_loop_wp4.py
"""
import sys
import os
import struct
import types
import importlib.util

sys.dont_write_bytecode = True  # __pycache__ を残さない

# tests/ の親ディレクトリ = コードルート(voice_loop/ 等がある階層)
VOICE_LOOP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "voice_loop", "voice_loop.py",
)


# ---------------------------------------------------------------------------
# 最小限の機能を持つ numpy スタブ（volume計算に使う演算のみ実装）
# ---------------------------------------------------------------------------
class _FakeArray:
    def __init__(self, values):
        self.values = [float(v) for v in values]

    def astype(self, _dtype):
        return _FakeArray(self.values)

    def __sub__(self, scalar):
        return _FakeArray([v - scalar for v in self.values])

    def tobytes(self):
        return struct.pack("<%dh" % len(self.values),
                           *[int(v) for v in self.values])


def _np_mean(a):
    vals = a.values if isinstance(a, _FakeArray) else list(a)
    return sum(vals) / len(vals) if vals else 0.0


def _np_abs(a):
    return _FakeArray([abs(v) for v in a.values])


def _make_fake_numpy():
    m = types.ModuleType("numpy")
    m.float32 = float
    m.mean = _np_mean
    m.abs = _np_abs
    return m


# ---------------------------------------------------------------------------
# その他import依存モジュールのスタブ
# ---------------------------------------------------------------------------
def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _install_stubs():
    sys.modules["numpy"] = _make_fake_numpy()
    _stub("sounddevice", InputStream=lambda **kw: None)
    _stub("webrtcvad", Vad=lambda *a, **k: object())
    _stub("faster_whisper", WhisperModel=object)
    _stub("gakukoma_brain", GAKUKOMABrain=object)
    _stub("led_controller", LedController=object)

    # パッケージ形式（tts.speak_text / servo.pan_tilt / servo.gesture_controller）
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
# フェイクHW
# ---------------------------------------------------------------------------
class FakeStream:
    """read(n) が (provider(call_no, n), False) を返す。"""
    def __init__(self, provider):
        self.provider = provider
        self.calls = 0

    def read(self, n):
        self.calls += 1
        return self.provider(self.calls, n), False


class _FakeInputStreamCM:
    def __init__(self, stream):
        self.stream = stream

    def __enter__(self):
        return self.stream

    def __exit__(self, *a):
        return False


class _FakeSd:
    """voice_loop.sd を差し替えるためのオブジェクト。"""
    def __init__(self, stream):
        self._stream = stream

    def InputStream(self, **kwargs):
        return _FakeInputStreamCM(self._stream)


class FakeVad:
    """事前に与えたシーケンスに沿って is_speech を返す。"""
    def __init__(self, seq):
        self.seq = list(seq)
        self.i = 0

    def is_speech(self, _buf, _sr):
        if self.i < len(self.seq):
            v = self.seq[self.i]
        else:
            v = self.seq[-1] if self.seq else False
        self.i += 1
        return bool(v)


# ---------------------------------------------------------------------------
# テスト対象VoiceLoopの最小生成
# ---------------------------------------------------------------------------
def make_vl(VoiceLoop, config, vad=None):
    vl = VoiceLoop.__new__(VoiceLoop)
    vl.config = config
    vl.frame_duration_ms = 30
    vl.sample_rate = 48000
    vl.frame_size = int(vl.sample_rate * vl.frame_duration_ms / 1000)  # 1440
    vl.device = 0
    if vad is not None:
        vl.vad = vad
    return vl


def low_provider(_call, n):
    return _FakeArray([0] * n)


def loud_provider(_call, n):
    # 平均0・振幅1000 → volume≈1000（>閾値）
    return _FakeArray([1000 if i % 2 == 0 else -1000 for i in range(n)])


# ---------------------------------------------------------------------------
# 実テスト
# ---------------------------------------------------------------------------
def run():
    mod = _load_voice_loop()
    VoiceLoop = mod.VoiceLoop
    results = []

    # --- (a) 無音 → タイムアウトで None -----------------------------------
    cfg = {
        "wakeword": {"chunk_duration": 0.09, "volume_threshold": 200,
                     "monitor_timeout_sec": 0.3},  # max_monitor_frames = 10
    }
    vl = make_vl(VoiceLoop, cfg)
    stream = FakeStream(low_provider)
    mod.sd = _FakeSd(stream)
    res = vl.record_wakeword_candidate()
    assert res is None, f"(a) expected None, got {type(res)}"
    # 15(discard) + 10(monitor) = 25回で打ち切られ、無限ループしていない
    assert stream.calls == 25, f"(a) expected 25 reads, got {stream.calls}"
    results.append("(a) 無音でタイムアウト→None: PASS (reads=%d)" % stream.calls)

    # --- (b) 音量トリガー後はフレーム列 -----------------------------------
    cfg = {
        "wakeword": {"chunk_duration": 0.09, "volume_threshold": 10,
                     "monitor_timeout_sec": 5},
    }
    vl = make_vl(VoiceLoop, cfg)
    stream = FakeStream(loud_provider)
    mod.sd = _FakeSd(stream)
    res = vl.record_wakeword_candidate()
    assert isinstance(res, list), f"(b) expected list, got {type(res)}"
    # duration 0.09 → int(0.09*1000/30)=3 フレーム
    assert len(res) == 3, f"(b) expected 3 frames, got {len(res)}"
    assert all(isinstance(f, (bytes, bytearray)) for f in res), "(b) frames must be bytes"
    results.append("(b) 音量トリガー後はフレーム列(list[bytes]): PASS (frames=%d)" % len(res))

    # --- (c) 常に無音 → no_speech_timeout で NO_SPEECH_TIMEOUT ------------
    cfg = {
        "vad": {"silence_threshold": 1.5, "min_speech_duration": 0.8,
                "no_speech_timeout_sec": 0.3},  # no_speech_frames_max = 10
    }
    vl = make_vl(VoiceLoop, cfg, vad=FakeVad([False]))
    stream = FakeStream(low_provider)
    res = vl.record_vad_from_stream(stream)
    assert res is mod.NO_SPEECH_TIMEOUT, \
        f"(c) expected NO_SPEECH_TIMEOUT sentinel, got {res!r}"
    # 11フレーム目で no_speech_count(11) > 10 となり打ち切り
    assert stream.calls == 11, f"(c) expected 11 reads, got {stream.calls}"
    results.append("(c) 無音でno_speech_timeout→NO_SPEECH_TIMEOUT: PASS (reads=%d)" % stream.calls)

    # --- (d) 発話開始→無音で録音停止しフレームを返す ----------------------
    cfg = {
        "vad": {"silence_threshold": 1.5, "min_speech_duration": 0.8,
                "no_speech_timeout_sec": 90},
    }
    # 先頭60フレーム speech（2連続で即トリガー）→ 以降 silence
    seq = [True] * 60 + [False] * 200
    vl = make_vl(VoiceLoop, cfg, vad=FakeVad(seq))
    stream = FakeStream(low_provider)
    res = vl.record_vad_from_stream(stream)
    assert res is not mod.NO_SPEECH_TIMEOUT, "(d) must not be timeout sentinel"
    assert isinstance(res, list), f"(d) expected list, got {type(res)}"
    # min_speech_frames = int(0.8*1000/30)=26 を上回り「短い音」で捨てられない
    assert len(res) > 26, f"(d) expected >26 frames, got {len(res)}"
    assert all(isinstance(f, (bytes, bytearray)) for f in res), "(d) frames must be bytes"
    results.append("(d) 発話開始→無音で録音停止しフレーム返却: PASS (frames=%d)" % len(res))

    print("\n".join(results))
    print("\nALL 4 CHECKS PASSED")


if __name__ == "__main__":
    try:
        run()
    except AssertionError as e:
        print("TEST FAILED:", e)
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("TEST ERROR:", e)
        sys.exit(2)
    sys.exit(0)
