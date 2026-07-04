#!/usr/bin/env python3
"""WP5 記憶注入のプロンプトキャッシュ化テスト（実API・実機不要）。

gakukoma_brain.py はimport時に anthropic / yaml を読み込むため、
sys.modules へ最小スタブを注入して import を通す。
GAKUKOMABrain は object.__new__ で生成し（__init__のopenclaw.json読込・
FaceRecognizer初期化を回避）、テストに必要な属性だけ差し込む。
MEMORY_DIR は一時ディレクトリへ差し替え、終了時に完全後始末する。

検証項目:
  (a) messages.create に渡る system が list長2で、cache_control は最終ブロックのみ
  (b) ブロック1に SYSTEM_PROMPT 本文と会話例（PRIMING）が含まれる
  (c) ブロック2に記憶スナップショット（index/core/dreams）が含まれる。
      記憶ファイルが無い場合はプレースホルダになる
  (d) 2ターン目の user メッセージに【記憶】系の文字列が含まれない（軽量化の検証）
  (e) 記憶ロードがセッション内で1回のみ（2回invokeしても増えない）、
      new_session() で再ロードされる

実行: python3 tests/test_brain_caching.py
"""
import os
import sys
import types
import shutil
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # __pycache__ を残さない


# ---------------------------------------------------------------------------
# import依存モジュール（anthropic / yaml）の最小スタブ
# ---------------------------------------------------------------------------
def _install_stub_modules():
    if "anthropic" not in sys.modules:
        m = types.ModuleType("anthropic")

        class _Anthropic:  # 実際には object.__new__ 生成のため使われない
            def __init__(self, *a, **k):
                pass

        m.Anthropic = _Anthropic
        sys.modules["anthropic"] = m

    if "yaml" not in sys.modules:
        sys.modules["yaml"] = types.ModuleType("yaml")


_install_stub_modules()

# brain/ を import パスに追加（このファイルは tests/ にある）
_BRAIN_DIR = Path(__file__).resolve().parent.parent / "brain"
sys.path.insert(0, str(_BRAIN_DIR))

import gakukoma_brain as gb  # noqa: E402
from gakukoma_brain import GAKUKOMABrain  # noqa: E402


# ---------------------------------------------------------------------------
# スタブ client: messages.create の kwargs を記録し、end_turn 応答を返す
# ---------------------------------------------------------------------------
class _StubTextBlock:
    def __init__(self, text):
        self.text = text
        self.type = "text"


class _StubUsage:
    input_tokens = 10
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0
    output_tokens = 5


class _StubResponse:
    def __init__(self, text):
        self.content = [_StubTextBlock(text)]
        self.stop_reason = "end_turn"
        self.usage = _StubUsage()


class _StubMessages:
    def __init__(self, outer):
        self._outer = outer

    def create(self, **kwargs):
        self._outer.calls.append(kwargs)
        return _StubResponse("うん、わかったよ。")


class StubClient:
    def __init__(self):
        self.calls = []
        self.messages = _StubMessages(self)


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="gakukoma_cachetest_"))


def _write_wiki(index=None, core=None, dreams=None):
    """wiki/ にフィクスチャを書く。None のファイルは作らない。"""
    wiki = _TMP_ROOT / "wiki"
    if wiki.exists():
        shutil.rmtree(wiki)
    wiki.mkdir(parents=True, exist_ok=True)
    if index is not None:
        (wiki / "index.md").write_text(index, encoding="utf-8")
    if core is not None:
        (wiki / "core_memories.md").write_text(core, encoding="utf-8")
    if dreams is not None:
        (wiki / "dreams.md").write_text(dreams, encoding="utf-8")


def _clear_wiki():
    wiki = _TMP_ROOT / "wiki"
    if wiki.exists():
        shutil.rmtree(wiki)


def _make_brain():
    """__init__ を通さずに GAKUKOMABrain を生成し、必要属性を差し込む。"""
    b = object.__new__(GAKUKOMABrain)
    b.client = StubClient()
    b.config = {}
    b.session_id = None
    b.local_history = []
    b._memory_snapshot = None
    b._face_recognizer = None
    return b


# ---------------------------------------------------------------------------
# テスト本体
# ---------------------------------------------------------------------------
_results = []


def _check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((name, cond, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))


INDEX_TXT = "私は学長と暮らすロボット。庭を探索するのが好き。"
CORE_TXT = "初めて学長に名前を呼ばれた日のこと。"
DREAMS_TXT = "## 2026-07-04\n虫の飛ぶルートに法則がある気がする。\n"


def test_a_system_two_blocks_cache_on_last():
    """(a) system が list長2で cache_control は最終ブロックのみ。"""
    _write_wiki(index=INDEX_TXT, core=CORE_TXT, dreams=DREAMS_TXT)
    b = _make_brain()
    b.new_session()
    b.invoke("こんにちは")

    kwargs = b.client.calls[-1]
    system = kwargs["system"]
    _check("(a) system が list", isinstance(system, list), f"type={type(system)}")
    _check("(a) system 長さ2", len(system) == 2, f"len={len(system)}")
    _check("(a) ブロック1に cache_control なし",
           "cache_control" not in system[0])
    _check("(a) ブロック2に cache_control あり",
           system[1].get("cache_control") == {"type": "ephemeral"},
           f"got={system[1].get('cache_control')}")
    # toolsも渡っている（tools+system がキャッシュ対象になる前提）
    _check("(a) tools が渡っている", bool(kwargs.get("tools")))


def test_b_block1_has_prompt_and_examples():
    """(b) ブロック1に SYSTEM_PROMPT 本文と会話例が含まれる。"""
    _write_wiki(index=INDEX_TXT)
    b = _make_brain()
    b.new_session()
    b.invoke("やあ")

    block1 = b.client.calls[-1]["system"][0]["text"]
    # SYSTEM_PROMPT の特徴的な一節
    _check("(b) ブロック1に SYSTEM_PROMPT 本文", "フィジカルAIロボット「がくこま」" in block1)
    # 会話例の見出しとPRIMINGの特徴的な台詞
    _check("(b) ブロック1に会話例の見出し", "## 会話例" in block1)
    _check("(b) ブロック1にPRIMINGの台詞",
           "話す前にルールを確認するよ" in block1)


def test_c_block2_has_memory_or_placeholder():
    """(c) ブロック2に記憶スナップショット。無ければプレースホルダ。"""
    # 記憶ありケース
    _write_wiki(index=INDEX_TXT, core=CORE_TXT, dreams=DREAMS_TXT)
    b = _make_brain()
    b.new_session()
    b.invoke("記憶ある？")
    block2 = b.client.calls[-1]["system"][1]["text"]
    _check("(c) ブロック2 見出し", "【がくこまの記憶】" in block2)
    _check("(c) ブロック2に index 内容", INDEX_TXT in block2)
    _check("(c) ブロック2に core 内容", CORE_TXT in block2)
    _check("(c) ブロック2に dreams 内容", "虫の飛ぶルート" in block2)

    # 記憶なしケース → プレースホルダ
    _clear_wiki()
    b2 = _make_brain()
    b2.new_session()
    b2.invoke("記憶ある？")
    block2_empty = b2.client.calls[-1]["system"][1]["text"]
    _check("(c) 記憶無しでプレースホルダ", "まだ記憶はない。" in block2_empty)
    _check("(c) 記憶無しでも見出しはある", "【がくこまの記憶】" in block2_empty)


def test_d_second_turn_user_has_no_memory():
    """(d) 2ターン目の user メッセージに【記憶】系文字列が含まれない。"""
    _write_wiki(index=INDEX_TXT, core=CORE_TXT, dreams=DREAMS_TXT)
    b = _make_brain()
    b.new_session()
    b.invoke("1回目の発話")
    b.invoke("2回目の発話")

    user_msg = b.client.calls[-1]["messages"][0]["content"]
    _check("(d) 2ターン目 user に【記憶 なし", "【記憶" not in user_msg)
    _check("(d) 2ターン目 user に【がくこまの記憶 なし",
           "【がくこまの記憶】" not in user_msg)
    _check("(d) 2ターン目 user にPRIMING前置き なし",
           "話す前にルールを確認するよ" not in user_msg)
    # 直前の会話（1回目）と今回の発話は含まれる
    _check("(d) 2ターン目 user に直前会話が含まれる", "1回目の発話" in user_msg)
    _check("(d) 2ターン目 user に今回の発話が含まれる", "2回目の発話" in user_msg)


def test_e_memory_loaded_once_per_session():
    """(e) 記憶ロードはセッション内1回のみ。new_session() で再ロード。"""
    _write_wiki(index=INDEX_TXT)
    orig = GAKUKOMABrain._load_memory_snapshot
    counter = {"n": 0}

    def _counting(self):
        counter["n"] += 1
        return orig(self)

    GAKUKOMABrain._load_memory_snapshot = _counting
    try:
        b = _make_brain()
        b.new_session()          # ロード1回目
        _check("(e) new_session で1回ロード", counter["n"] == 1, f"n={counter['n']}")

        b.invoke("あ")
        b.invoke("い")           # 2回invokeしても増えない
        _check("(e) invoke 2回でロード増えない", counter["n"] == 1, f"n={counter['n']}")

        b.new_session()          # 再ロード
        _check("(e) new_session で再ロード", counter["n"] == 2, f"n={counter['n']}")
    finally:
        GAKUKOMABrain._load_memory_snapshot = orig


def test_f_invoke_before_new_session_defensive():
    """(補) new_session 未実行で invoke しても壊れない（防御ロード）。"""
    _write_wiki(index=INDEX_TXT)
    b = _make_brain()
    # new_session を呼ばずに invoke
    b.invoke("いきなり発話")
    block2 = b.client.calls[-1]["system"][1]["text"]
    _check("(補) 防御ロードで記憶が入る", INDEX_TXT in block2)


def main():
    # MEMORY_DIR を一時ディレクトリへ差し替え
    gb.MEMORY_DIR = _TMP_ROOT

    tests = [
        test_a_system_two_blocks_cache_on_last,
        test_b_block1_has_prompt_and_examples,
        test_c_block2_has_memory_or_placeholder,
        test_d_second_turn_user_has_no_memory,
        test_e_memory_loaded_once_per_session,
        test_f_invoke_before_new_session_defensive,
    ]
    try:
        for t in tests:
            t()
    finally:
        if _TMP_ROOT.exists():
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
