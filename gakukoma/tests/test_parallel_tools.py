#!/usr/bin/env python3
"""WP-I 並列ツール実行（動きながらしゃべる）テスト（実API・実機不要）。

1応答に複数tool_useが含まれるとき、音声レーン(speak_text/sing_song)と
ボディレーン(それ以外)を並列実行する2レーン方式を検証する。
_execute_tool をモック（実行時刻記録つき・sleepで所要時間を模擬）し、
subprocess・ネットワーク・実デバイス・APIキーは一切使わない。
スタブ注入の流儀は test_streaming_speak.py / test_brain_caching.py に倣う。

検証項目:
  (a) 音声2ツール(speak_text, sing_song)は時間的に重ならない（音声レーン内直列）
  (b) 音声×ボディ(speak_text × move_robot)は時間的に重なる（2レーン並列）
  (c) tool_results の順序と tool_use_id が元ブロック順に一致する
  (d) 音声含みバッチで _flush_speech が呼ばれ、音声なしバッチでは呼ばれない
  (e) 片ツールが例外を投げても全 tool_results が揃う（欠落なし・エラー文字列化）

実行: python3 gakukoma/tests/test_parallel_tools.py
"""
import sys
import time
import types
import shutil
import tempfile
import threading
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
        class _Anthropic:  # object.__new__ 生成のため実際には使われない
            def __init__(self, *a, **k):
                pass
        _stub("anthropic", Anthropic=_Anthropic)
    if "yaml" not in sys.modules:
        _stub("yaml")


_install_brain_stubs()

_BRAIN_DIR = Path(__file__).resolve().parent.parent / "brain"
sys.path.insert(0, str(_BRAIN_DIR))

import gakukoma_brain as gb  # noqa: E402
from gakukoma_brain import GAKUKOMABrain, AUDIO_TOOLS  # noqa: E402


# ---------------------------------------------------------------------------
# モックのブロック/メッセージ/クライアント（test_streaming_speak.py と同型）
# ---------------------------------------------------------------------------
class _TextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _ToolUseBlock:
    def __init__(self, name, inp=None, id_="tu_1"):
        self.type = "tool_use"
        self.name = name
        self.input = inp or {}
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


class _MockStream:
    """イベントを吐かない最小ストリーム（本テストはツール実行タイミングだけ見る）。"""

    def __init__(self, turn):
        self._turn = turn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(())

    def get_final_message(self):
        return _FinalMessage(self._turn["blocks"], self._turn["stop_reason"])


class _MockMessages:
    def __init__(self, outer):
        self._outer = outer

    def _next_turn(self):
        turn = self._outer.turns[self._outer._idx]
        self._outer._idx = min(self._outer._idx + 1, len(self._outer.turns) - 1)
        return turn

    def stream(self, **kwargs):
        self._outer.stream_calls.append(kwargs)
        return _MockStream(self._next_turn())

    def create(self, **kwargs):
        self._outer.create_calls.append(kwargs)
        turn = self._next_turn()
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
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="gakukoma_parallel_test_"))

DELAY = 0.15  # ツール1本の模擬所要時間（重なり判定に十分な長さ）


def _make_brain(turns, durations=None, fail_tools=()):
    """モック脳を作る。_execute_tool は実行時刻を記録し sleep で所要時間を模擬。"""
    b = object.__new__(GAKUKOMABrain)
    b.client = MockClient(turns)
    b.config = {}
    b.session_id = None
    b.local_history = []
    b._memory_snapshot = ""
    b._face_recognizer = None

    lock = threading.Lock()
    b.exec_records = []  # (name, start, end)

    durations = durations or {}

    def _fake_exec(name, inp):
        start = time.monotonic()
        if name in fail_tools:
            # 記録してから例外を漏らす（設計4: スレッド内例外の防御を検証）
            with lock:
                b.exec_records.append((name, start, time.monotonic()))
            raise RuntimeError(f"boom:{name}")
        time.sleep(durations.get(name, DELAY))
        end = time.monotonic()
        with lock:
            b.exec_records.append((name, start, end))
        return f"{name}-ok"

    b._execute_tool = _fake_exec
    return b


class Recorder:
    """on_sentence コールバック。flush() を持ち、呼び出し時刻を記録する。"""

    def __init__(self):
        self.sentences = []
        self.flush_times = []

    def __call__(self, sentence):
        self.sentences.append(sentence)

    def flush(self):
        self.flush_times.append(time.monotonic())


def _interval(brain, name):
    for rec_name, start, end in brain.exec_records:
        if rec_name == name:
            return start, end
    raise AssertionError(f"{name} が実行されていない: {brain.exec_records}")


def _overlaps(iv1, iv2):
    return iv1[0] < iv2[1] and iv2[0] < iv1[1]


def _tool_results_of(brain, call_index=1):
    """call_index 番目のAPI呼び出しに渡された messages から tool_results を取り出す。"""
    calls = brain.client.stream_calls or brain.client.create_calls
    msgs = calls[call_index]["messages"]
    return msgs[-1]["content"]  # 直近の user メッセージ = tool_results


_results = []


def _check(name, cond, detail=""):
    _results.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))


# ---------------------------------------------------------------------------
# (a) 音声2ツールは時間的に重ならない（音声レーン内直列）
# ---------------------------------------------------------------------------
def test_a_audio_tools_serialized():
    turns = [
        _turn([_ToolUseBlock("speak_text", {"text": "歌うよ"}, "tu_sp"),
               _ToolUseBlock("sing_song", {"notes": []}, "tu_sg")],
              stop_reason="tool_use"),
        _turn([_TextBlock("歌ったよ。")]),
    ]
    b = _make_brain(turns)
    b.invoke("うたって", on_sentence=Recorder())

    sp = _interval(b, "speak_text")
    sg = _interval(b, "sing_song")
    _check("(a) 音声2ツールが両方実行された", len(b.exec_records) == 2,
           f"got={b.exec_records}")
    _check("(a) speak_text と sing_song が時間的に重ならない", not _overlaps(sp, sg),
           f"speak={sp} sing={sg}")
    _check("(a) 音声レーン内はブロック順（speak→sing）", sp[1] <= sg[0],
           f"speak_end={sp[1]} sing_start={sg[0]}")
    _check("(a) AUDIO_TOOLS の定義が設計どおり",
           AUDIO_TOOLS == {"speak_text", "sing_song"}, f"got={AUDIO_TOOLS}")


# ---------------------------------------------------------------------------
# (b) 音声×ボディは時間的に重なる（2レーン並列）
# ---------------------------------------------------------------------------
def test_b_audio_body_parallel():
    turns = [
        _turn([_ToolUseBlock("speak_text", {"text": "前進するよ"}, "tu_sp"),
               _ToolUseBlock("move_robot", {"direction": "forward"}, "tu_mv")],
              stop_reason="tool_use"),
        _turn([_TextBlock("進んだよ。")]),
    ]
    b = _make_brain(turns)
    t0 = time.monotonic()
    b.invoke("前進しながら言って", on_sentence=Recorder())
    elapsed = time.monotonic() - t0

    sp = _interval(b, "speak_text")
    mv = _interval(b, "move_robot")
    _check("(b) speak_text と move_robot が時間的に重なる", _overlaps(sp, mv),
           f"speak={sp} move={mv}")
    _check("(b) 直列(2×DELAY)より短時間で完了（並列の傍証）", elapsed < 2 * DELAY * 0.95,
           f"elapsed={elapsed:.3f}s serial={2 * DELAY:.3f}s")


# ---------------------------------------------------------------------------
# (c) tool_results の順序と tool_use_id が元ブロック順に一致
# ---------------------------------------------------------------------------
def test_c_tool_results_order():
    # 音声・ボディを交互に混ぜた4ツール（並列でも組み立て順は元のまま）
    turns = [
        _turn([_TextBlock("やってみる。"),
               _ToolUseBlock("speak_text", {"text": "行くよ"}, "tu_1"),
               _ToolUseBlock("move_robot", {"direction": "forward"}, "tu_2"),
               _ToolUseBlock("sing_song", {"notes": []}, "tu_3"),
               _ToolUseBlock("see_around", {}, "tu_4")],
              stop_reason="tool_use"),
        _turn([_TextBlock("できたよ。")]),
    ]
    b = _make_brain(turns)
    ret = b.invoke("動きながら歌って見て", on_sentence=Recorder())

    results = _tool_results_of(b, call_index=1)
    _check("(c) tool_results は4件", len(results) == 4, f"got={results}")
    _check("(c) 全件 type=tool_result",
           all(r.get("type") == "tool_result" for r in results), f"got={results}")
    _check("(c) tool_use_id が元ブロック順に一致",
           [r.get("tool_use_id") for r in results] == ["tu_1", "tu_2", "tu_3", "tu_4"],
           f"got={[r.get('tool_use_id') for r in results]}")
    _check("(c) 各resultの中身が対応ツールの出力",
           [r.get("content") for r in results]
           == ["speak_text-ok", "move_robot-ok", "sing_song-ok", "see_around-ok"],
           f"got={[r.get('content') for r in results]}")
    # ボディレーン内も直列（move → see の順）
    mv = _interval(b, "move_robot")
    sa = _interval(b, "see_around")
    _check("(c) ボディレーン内はブロック順に直列", mv[1] <= sa[0] and not _overlaps(mv, sa),
           f"move={mv} see={sa}")
    _check("(c) 最終応答は従来どおり返る", ret == "できたよ。", f"got={ret!r}")


# ---------------------------------------------------------------------------
# (d) 音声含みバッチで flush、音声なしバッチで flush なし
# ---------------------------------------------------------------------------
def test_d_flush_discipline():
    # 音声含みバッチ → flush が1回、かつ全ツール開始より前
    turns_audio = [
        _turn([_ToolUseBlock("speak_text", {"text": "こんにちは"}, "tu_sp"),
               _ToolUseBlock("move_robot", {"direction": "forward"}, "tu_mv")],
              stop_reason="tool_use"),
        _turn([_TextBlock("おわり。")]),
    ]
    b1 = _make_brain(turns_audio)
    rec1 = Recorder()
    b1.invoke("挨拶して進んで", on_sentence=rec1)
    _check("(d) 音声含みバッチで flush が呼ばれる", len(rec1.flush_times) == 1,
           f"got={len(rec1.flush_times)}")
    first_start = min(start for _, start, _ in b1.exec_records)
    _check("(d) flush は全ツール実行より前",
           rec1.flush_times and rec1.flush_times[0] <= first_start,
           f"flush={rec1.flush_times} first_start={first_start}")

    # 音声なしバッチ → flush は呼ばれない（実況TTSとモーターが重なるのは意図）
    turns_body = [
        _turn([_ToolUseBlock("move_robot", {"direction": "forward"}, "tu_mv"),
               _ToolUseBlock("see_around", {}, "tu_sa")],
              stop_reason="tool_use"),
        _turn([_TextBlock("見たよ。")]),
    ]
    b2 = _make_brain(turns_body)
    rec2 = Recorder()
    b2.invoke("進んで見てきて", on_sentence=rec2)
    _check("(d) 音声なしバッチで flush が呼ばれない", rec2.flush_times == [],
           f"got={rec2.flush_times}")
    _check("(d) 音声なしバッチでもツールは全実行",
           sorted(n for n, _, _ in b2.exec_records) == ["move_robot", "see_around"],
           f"got={b2.exec_records}")


# ---------------------------------------------------------------------------
# (e) 片ツール例外時も全 tool_results が揃う
# ---------------------------------------------------------------------------
def test_e_exception_keeps_all_results():
    # 並列バッチ内のボディツールが例外 → 音声側の結果もエラー側の結果も揃う
    turns = [
        _turn([_ToolUseBlock("speak_text", {"text": "動くよ"}, "tu_sp"),
               _ToolUseBlock("move_robot", {"direction": "forward"}, "tu_mv"),
               _ToolUseBlock("see_around", {}, "tu_sa")],
              stop_reason="tool_use"),
        _turn([_TextBlock("ごめん。")]),
    ]
    b = _make_brain(turns, fail_tools={"move_robot"})
    ret = b.invoke("動いて見て", on_sentence=Recorder())

    results = _tool_results_of(b, call_index=1)
    _check("(e) 例外時も tool_results は3件揃う", len(results) == 3, f"got={results}")
    _check("(e) id 対応が崩れない",
           [r.get("tool_use_id") for r in results] == ["tu_sp", "tu_mv", "tu_sa"],
           f"got={[r.get('tool_use_id') for r in results]}")
    by_id = {r["tool_use_id"]: r["content"] for r in results}
    _check("(e) 例外ツールはエラー文字列になる",
           "実行エラー" in by_id["tu_mv"] and "boom:move_robot" in by_id["tu_mv"],
           f"got={by_id['tu_mv']!r}")
    _check("(e) 他ツールの結果は正常", by_id["tu_sp"] == "speak_text-ok",
           f"got={by_id['tu_sp']!r}")
    _check("(e) 例外後もレーン内の後続ツールが実行される", by_id["tu_sa"] == "see_around-ok",
           f"got={by_id['tu_sa']!r}")
    _check("(e) ループは継続し最終応答が返る", ret == "ごめん。", f"got={ret!r}")

    # 音声レーン側の例外も同様に揃う
    turns2 = [
        _turn([_ToolUseBlock("speak_text", {"text": "あ"}, "tu_sp"),
               _ToolUseBlock("move_robot", {"direction": "forward"}, "tu_mv")],
              stop_reason="tool_use"),
        _turn([_TextBlock("うん。")]),
    ]
    b2 = _make_brain(turns2, fail_tools={"speak_text"})
    b2.invoke("言いながら進んで", on_sentence=Recorder())
    results2 = _tool_results_of(b2, call_index=1)
    by_id2 = {r["tool_use_id"]: r["content"] for r in results2}
    _check("(e) 音声レーン例外でも2件揃う",
           len(results2) == 2 and "実行エラー" in by_id2["tu_sp"]
           and by_id2["tu_mv"] == "move_robot-ok",
           f"got={results2}")


# ---------------------------------------------------------------------------
# (補) 単ツール・後方互換: 片レーン空ならインライン実行、非ストリーム経路も動く
# ---------------------------------------------------------------------------
def test_f_single_lane_and_backward_compat():
    # 音声のみ1本（on_sentenceなし = create経路）でも従来どおり動く
    turns = [
        _turn([_ToolUseBlock("speak_text", {"text": "やあ"}, "tu_sp")],
              stop_reason="tool_use"),
        _turn([_TextBlock("言ったよ。")]),
    ]
    b = _make_brain(turns)
    ret = b.invoke("言って")  # on_sentence を渡さない
    _check("(補) 非ストリーム経路でも単ツール実行できる", ret == "言ったよ。", f"got={ret!r}")
    _check("(補) create が使われ stream は使われない",
           len(b.client.create_calls) == 2 and len(b.client.stream_calls) == 0,
           f"create={len(b.client.create_calls)} stream={len(b.client.stream_calls)}")
    results = _tool_results_of(b, call_index=1)
    _check("(補) 単ツールの tool_result も正しい",
           len(results) == 1 and results[0]["tool_use_id"] == "tu_sp"
           and results[0]["content"] == "speak_text-ok", f"got={results}")


def main():
    gb.MEMORY_DIR = _TMP_ROOT
    tests = [
        test_a_audio_tools_serialized,
        test_b_audio_body_parallel,
        test_c_tool_results_order,
        test_d_flush_discipline,
        test_e_exception_keeps_all_results,
        test_f_single_lane_and_backward_compat,
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
