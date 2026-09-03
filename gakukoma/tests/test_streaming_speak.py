#!/usr/bin/env python3
"""WP-E ストリーミング応答 + 文単位TTS テスト（実API・実機不要）。

gakukoma_brain.py / voice_loop.py はimport時に anthropic / yaml / numpy /
sounddevice などを読み込むため、sys.modules へ最小スタブを注入して import を通す
（test_brain_caching.py / test_voice_loop_triggers.py の流儀に倣う）。
ANTHROPIC APIは呼ばない。モックストリーム（イベント列を吐く偽 messages.stream）
だけで検証する。

検証項目（受け入れ条件2）:
  (a) モックストリームで文単位にコールバックが発火する
      （デルタは文の途中で切れて届く前提。「。！？」で確定した時だけ渡す）
  (b) tool_use 割込みターンで文の欠落・重複がない
      （ツール実行前にフラッシュ要求が入り、実況→ツール の順序が保たれる）
  (c) 句読点で終わらない末尾テキストも最後に発話される
  (d) コールバック未指定時は従来動作（messages.create・stream不使用）
  (e) voice_loop.SentenceSpeaker が順序を保って裏で発話し、
      clean_text_for_tts を文ごとに適用し、二重発話の抑止判定を持つ

実行: python3 gakukoma/tests/test_streaming_speak.py
"""
import os
import sys
import time
import types
import shutil
import tempfile
import importlib.util
from pathlib import Path

sys.dont_write_bytecode = True  # __pycache__ を残さない


# ---------------------------------------------------------------------------
# import依存モジュールの最小スタブ
# ---------------------------------------------------------------------------
def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _install_brain_stubs():
    if "anthropic" not in sys.modules:
        class _Anthropic:  # 実際には object.__new__ 生成のため使われない
            def __init__(self, *a, **k):
                pass
        _stub("anthropic", Anthropic=_Anthropic)
    if "yaml" not in sys.modules:
        _stub("yaml")


def _install_voice_loop_stubs():
    np = types.ModuleType("numpy")
    np.float32 = float
    np.mean = lambda a: 0.0
    np.abs = lambda a: a
    sys.modules["numpy"] = np
    _stub("sounddevice", InputStream=lambda **kw: None)
    _stub("webrtcvad", Vad=lambda *a, **k: object())
    _stub("faster_whisper", WhisperModel=object)
    # gakukoma_brain はスタブしない（このテストで検証する実物を voice_loop に使わせる）
    _stub("led_controller", LedController=object)
    tts_pkg = _stub("tts")
    tts_pkg.__path__ = []
    _stub("tts.speak_text", OpenJTalkTTS=object)
    servo_pkg = _stub("servo")
    servo_pkg.__path__ = []
    _stub("servo.pan_tilt", PanTiltController=object)
    _stub("servo.gesture_controller", GestureController=object)


_install_brain_stubs()

_BRAIN_DIR = Path(__file__).resolve().parent.parent / "brain"
sys.path.insert(0, str(_BRAIN_DIR))

import gakukoma_brain as gb  # noqa: E402
from gakukoma_brain import GAKUKOMABrain, SentenceSplitter  # noqa: E402


def _load_voice_loop():
    """voice_loop を（実gakukoma_brainを使いつつ）スタブ環境で読み込む。"""
    _install_voice_loop_stubs()
    path = Path(__file__).resolve().parent.parent / "voice_loop" / "voice_loop.py"
    spec = importlib.util.spec_from_file_location("voice_loop", str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["voice_loop"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# モックストリーム（SDKの messages.stream 相当）
#   with client.messages.stream(...) as s: for ev in s: ...; s.get_final_message()
# ---------------------------------------------------------------------------
class _Delta:
    def __init__(self, text):
        self.type = "text_delta"
        self.text = text


class _Event:
    def __init__(self, type_, delta=None):
        self.type = type_
        self.delta = delta


class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _ToolUseBlock:
    def __init__(self, name, inp, id_="tu_1"):
        self.type = "tool_use"
        self.name = name
        self.input = inp
        self.id = id_


class _Usage:
    input_tokens = 10
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0
    output_tokens = 5


class _FinalMessage:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _Usage()


def _chunks(text, size=3):
    """文の途中で切れるデルタを作る（実ストリームは文境界を尊重しない）。"""
    return [text[i:i + size] for i in range(0, len(text), size)]


class _MockStream:
    """1ターン分のイベント列を吐き、get_final_message() で完全なMessageを返す。"""

    def __init__(self, turn):
        self._turn = turn
        self._entered = False

    def __enter__(self):
        self._entered = True
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for block in self._turn["blocks"]:
            yield _Event("content_block_start")
            if isinstance(block, _TextBlock):
                for c in _chunks(block.text):
                    yield _Event("content_block_delta", _Delta(c))
            yield _Event("content_block_stop")
        yield _Event("message_delta")
        yield _Event("message_stop")

    def get_final_message(self):
        return _FinalMessage(self._turn["blocks"], self._turn["stop_reason"])


class _MockMessages:
    def __init__(self, outer):
        self._outer = outer

    def stream(self, **kwargs):
        self._outer.stream_calls.append(kwargs)
        turn = self._outer.turns[self._outer._idx]
        self._outer._idx = min(self._outer._idx + 1, len(self._outer.turns) - 1)
        return _MockStream(turn)

    def create(self, **kwargs):
        self._outer.create_calls.append(kwargs)
        turn = self._outer.turns[self._outer._idx]
        self._outer._idx = min(self._outer._idx + 1, len(self._outer.turns) - 1)
        return _FinalMessage(turn["blocks"], turn["stop_reason"])


class MockClient:
    def __init__(self, turns):
        self.turns = turns
        self._idx = 0
        self.stream_calls = []
        self.create_calls = []
        self.messages = _MockMessages(self)


def _turn(blocks, stop_reason="end_turn"):
    return {"blocks": blocks, "stop_reason": stop_reason}


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="gakukoma_stream_test_"))


def _make_brain(turns):
    b = object.__new__(GAKUKOMABrain)
    b.client = MockClient(turns)
    b.config = {}
    b.session_id = None
    b.local_history = []
    b._memory_snapshot = ""
    b._face_recognizer = None
    return b


class Recorder:
    """on_sentence コールバック。flush() を持ち、呼び出し順を記録する。"""

    def __init__(self):
        self.sentences = []
        self.events = []

    def __call__(self, sentence):
        self.sentences.append(sentence)
        self.events.append(("say", sentence))

    def flush(self):
        self.events.append(("flush", None))


_results = []


def _check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
# (a) モックストリームで文単位にコールバック発火
# ---------------------------------------------------------------------------
def test_a_sentence_callbacks():
    text = "こんにちは！僕はがくこまだよ。今日はなにする？"
    b = _make_brain([_turn([_TextBlock(text)])])
    rec = Recorder()
    ret = b.invoke("やあ", on_sentence=rec)

    _check("(a) 文単位に3回発火",
           rec.sentences == ["こんにちは！", "僕はがくこまだよ。", "今日はなにする？"],
           f"got={rec.sentences}")
    _check("(a) 連結すると元の全文に一致", "".join(rec.sentences) == text,
           f"got={''.join(rec.sentences)!r}")
    _check("(a) 戻り値は全文（履歴用）", ret == text, f"got={ret!r}")
    _check("(a) stream が使われた", len(b.client.stream_calls) == 1,
           f"stream={len(b.client.stream_calls)} create={len(b.client.create_calls)}")
    _check("(a) create は使われていない", len(b.client.create_calls) == 0)
    # プロンプトキャッシュ構成（system2ブロック+最終ブロックcache_control）を壊していない
    sysblocks = b.client.stream_calls[0]["system"]
    _check("(a) system 2ブロック維持", isinstance(sysblocks, list) and len(sysblocks) == 2,
           f"got={sysblocks if not isinstance(sysblocks, list) else len(sysblocks)}")
    _check("(a) cache_control は最終ブロックのみ",
           "cache_control" not in sysblocks[0]
           and sysblocks[1].get("cache_control") == {"type": "ephemeral"})
    _check("(a) モデルは変更されていない",
           b.client.stream_calls[0]["model"] == "claude-haiku-4-5-20251001",
           f"got={b.client.stream_calls[0]['model']}")
    # 履歴には全文が入る
    _check("(a) local_history に全文", b.local_history == [("やあ", text)],
           f"got={b.local_history}")


# ---------------------------------------------------------------------------
# (b) tool_use 割込みターンで欠落・重複なし
# ---------------------------------------------------------------------------
def test_b_tool_use_turn_no_loss_no_dup():
    pre = "ちょっと見てみるね。前を確認するよ。"
    post = "本棚が見えた。右は壁だったよ。"
    turns = [
        _turn([_TextBlock(pre), _ToolUseBlock("see_around", {})], stop_reason="tool_use"),
        _turn([_TextBlock(post)], stop_reason="end_turn"),
    ]
    b = _make_brain(turns)
    rec = Recorder()

    # ツールは実行せず、呼び出し順だけ記録する（subprocessを起こさない）
    executed = []

    def _fake_exec(name, inp):
        executed.append(name)
        rec.events.append(("tool", name))
        return "本棚が見えた"

    b._execute_tool = _fake_exec

    ret = b.invoke("あたり見てきて", on_sentence=rec)

    expected = ["ちょっと見てみるね。", "前を確認するよ。", "本棚が見えた。", "右は壁だったよ。"]
    _check("(b) 全4文が過不足なく発火", rec.sentences == expected, f"got={rec.sentences}")
    _check("(b) 重複なし", len(rec.sentences) == len(set(rec.sentences)),
           f"got={rec.sentences}")
    _check("(b) 欠落なし（連結が元テキストと一致）",
           "".join(rec.sentences) == pre + post)
    _check("(b) ツールが1回実行された", executed == ["see_around"], f"got={executed}")
    _check("(b) 戻り値は最終ターンの全文", ret == post, f"got={ret!r}")
    _check("(b) 2ターン分 stream された", len(b.client.stream_calls) == 2,
           f"got={len(b.client.stream_calls)}")

    # 順序: 実況2文 → flush → ツール → 後半2文
    kinds = [e[0] for e in rec.events]
    tool_i = kinds.index("tool")
    flush_i = kinds.index("flush")
    _check("(b) ツール実行前にフラッシュ要求", flush_i < tool_i, f"events={rec.events}")
    _check("(b) 実況はツール実行より前に発話",
           rec.events[0] == ("say", "ちょっと見てみるね。")
           and rec.events[1] == ("say", "前を確認するよ。")
           and tool_i == 3, f"events={rec.events}")
    _check("(b) ツール後の文はツールより後",
           kinds[tool_i + 1:] == ["say", "say"], f"events={rec.events}")


# ---------------------------------------------------------------------------
# (c) 句読点で終わらない末尾テキストも最後に発話される
# ---------------------------------------------------------------------------
def test_c_trailing_text_without_punctuation():
    text = "うん、わかった。じゃあまたね"
    b = _make_brain([_turn([_TextBlock(text)])])
    rec = Recorder()
    b.invoke("おわり", on_sentence=rec)
    _check("(c) 末尾の無句読点テキストも発話",
           rec.sentences == ["うん、わかった。", "じゃあまたね"], f"got={rec.sentences}")

    # 句読点が1つも無いケース
    b2 = _make_brain([_turn([_TextBlock("そっか")])])
    rec2 = Recorder()
    b2.invoke("ふーん", on_sentence=rec2)
    _check("(c) 句読点ゼロでも1文として発話", rec2.sentences == ["そっか"], f"got={rec2.sentences}")

    # SentenceSplitter 単体: flush 後にバッファが空になる（=二度渡らない）
    got = []
    sp = SentenceSplitter(got.append)
    sp.feed("あ")
    sp.feed("い。う")
    sp.flush()
    sp.flush()
    _check("(c) flush は二度呼んでも重複しない", got == ["あい。", "う"], f"got={got}")

    # 空白のみの断片は発話しない
    got2 = []
    sp2 = SentenceSplitter(got2.append)
    sp2.feed("  \n ")
    sp2.flush()
    _check("(c) 空白のみは発話しない", got2 == [], f"got={got2}")


# ---------------------------------------------------------------------------
# (d) コールバック未指定時は従来動作（後方互換）
# ---------------------------------------------------------------------------
def test_d_backward_compatible_without_callback():
    text = "うん、いいよ。"
    b = _make_brain([_turn([_TextBlock(text)])])
    ret = b.invoke("ねえ")   # on_sentence を渡さない
    _check("(d) 戻り値は従来どおり全文", ret == text, f"got={ret!r}")
    _check("(d) messages.create が使われる", len(b.client.create_calls) == 1,
           f"got={len(b.client.create_calls)}")
    _check("(d) messages.stream は使われない", len(b.client.stream_calls) == 0,
           f"got={len(b.client.stream_calls)}")
    _check("(d) invoke のシグネチャが後方互換（位置引数1つで呼べる）", True)

    # tool_use を含む従来経路も壊れていない
    turns = [
        _turn([_TextBlock("見てみる。"), _ToolUseBlock("see_around", {})], stop_reason="tool_use"),
        _turn([_TextBlock("壁だったよ。")], stop_reason="end_turn"),
    ]
    b2 = _make_brain(turns)
    b2._execute_tool = lambda name, inp: "壁"
    ret2 = b2.invoke("見て")
    _check("(d) 非ストリームのtool loopも従来どおり", ret2 == "壁だったよ。", f"got={ret2!r}")
    _check("(d) 非ストリームは create 2回", len(b2.client.create_calls) == 2,
           f"got={len(b2.client.create_calls)}")


# ---------------------------------------------------------------------------
# (e) voice_loop.SentenceSpeaker: 順序保証・非ブロッキング・二重発話抑止
# ---------------------------------------------------------------------------
class SlowTTS:
    """aplay 相当の同期TTS（少し時間がかかる）。"""

    def __init__(self, delay=0.02):
        self.said = []
        self.delay = delay

    def speak(self, text):
        time.sleep(self.delay)
        self.said.append(text)


def test_e_sentence_speaker():
    vl = _load_voice_loop()
    Speaker = vl.SentenceSpeaker

    tts = SlowTTS()
    first = []
    sp = Speaker(tts, on_first_speech=lambda: first.append(len(tts.said)))

    # 積むだけで即返る（TTSにブロックされない）= ストリーム消費を止めない
    t0 = time.monotonic()
    for s in ["いち。", "に。", "さん。", "し。", "ご。"]:
        sp(s)
    enqueue_elapsed = time.monotonic() - t0
    _check("(e) 積む操作はTTSにブロックされない",
           enqueue_elapsed < 5 * tts.delay, f"elapsed={enqueue_elapsed:.3f}s")

    sp.flush()
    _check("(e) flush で全文を言い終える", len(tts.said) == 5, f"got={tts.said}")
    _check("(e) 発話順序が保たれる",
           tts.said == ["いち。", "に。", "さん。", "し。", "ご。"], f"got={tts.said}")
    _check("(e) 初回発話フックは発話開始直前に1回", first == [0], f"got={first}")

    sp("ろく。")
    sp.close()
    _check("(e) close で残りも言い終える", tts.said[-1] == "ろく。", f"got={tts.said}")
    _check("(e) 初回フックは1回だけ", len(first) == 1, f"got={first}")
    _check("(e) spoke_any が True（二重発話の抑止判定）", sp.spoke_any is True)

    # 文ごとに clean_text_for_tts が適用される（絵文字・Markdown除去）
    tts2 = SlowTTS(delay=0)
    sp2 = Speaker(tts2)
    sp2("**すごい**ね。")
    sp2.close()
    _check("(e) 文ごとに clean_text_for_tts 適用", tts2.said == ["すごいね。"], f"got={tts2.said}")

    # 一言も来なければ spoke_any は False（呼び出し側が従来経路で救済できる）
    tts3 = SlowTTS(delay=0)
    hook3 = []
    sp3 = Speaker(tts3, on_first_speech=lambda: hook3.append(1))
    sp3("   ")      # 空白のみ → 発話しない
    sp3.close()
    _check("(e) 空白のみでは spoke_any False", sp3.spoke_any is False)
    _check("(e) 発話ゼロなら初回フックも呼ばれない", hook3 == [], f"got={hook3}")
    _check("(e) 発話ゼロなら TTS も呼ばれない", tts3.said == [], f"got={tts3.said}")

    # 1文が失敗しても後続は発話される（頑健性）
    class FlakyTTS(SlowTTS):
        def speak(self, text):
            if text == "だめ。":
                raise RuntimeError("open_jtalk failed")
            self.said.append(text)

    tts4 = FlakyTTS(delay=0)
    sp4 = Speaker(tts4)
    sp4("だめ。")
    sp4("つぎ。")
    sp4.close()
    _check("(e) 1文のTTS失敗で後続が止まらない", tts4.said == ["つぎ。"], f"got={tts4.said}")


# ---------------------------------------------------------------------------
# (f) 補: エラー時もコールバック経由でお詫びが発話される
# ---------------------------------------------------------------------------
def test_f_call_brain_error_speaks_apology():
    vl = _load_voice_loop()
    VoiceLoop = vl.VoiceLoop
    loop = VoiceLoop.__new__(VoiceLoop)

    class BoomBrain:
        def invoke(self, text, on_sentence=None):
            raise RuntimeError("boom")

    loop.brain = BoomBrain()
    rec = Recorder()
    ret = loop.call_brain("やあ", on_sentence=rec)
    _check("(補) エラー時の戻り値はお詫び", ret == "すみません、エラーが発生しました。",
           f"got={ret!r}")
    _check("(補) エラー時もコールバックで発話される",
           rec.sentences == ["すみません、エラーが発生しました。"], f"got={rec.sentences}")

    # コールバック未指定なら従来どおり戻り値だけ
    class OkBrain:
        def __init__(self):
            self.kwargs_seen = []

        def invoke(self, text, **kw):
            self.kwargs_seen.append(kw)
            return "はい。"

    loop.brain = OkBrain()
    ret2 = loop.call_brain("やあ")
    _check("(補) コールバック未指定なら on_sentence を渡さない",
           ret2 == "はい。" and loop.brain.kwargs_seen == [{}],
           f"ret={ret2!r} kwargs={loop.brain.kwargs_seen}")


def main():
    gb.MEMORY_DIR = _TMP_ROOT
    tests = [
        test_a_sentence_callbacks,
        test_b_tool_use_turn_no_loss_no_dup,
        test_c_trailing_text_without_punctuation,
        test_d_backward_compatible_without_callback,
        test_e_sentence_speaker,
        test_f_call_brain_error_speaks_apology,
    ]
    try:
        for t in tests:
            t()
    finally:
        shutil.rmtree(_TMP_ROOT, ignore_errors=True)

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
    main()
