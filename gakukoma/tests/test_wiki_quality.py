#!/usr/bin/env python3
"""
WP2 wiki品質のテスト（実API・実機不要）。

- 一時ディレクトリを GAKUKOMA_MEMORY_DIR に設定してから memory_processor を import する。
- client は messages.create がプロンプト内容で応答を出し分けるスタブ（実APIは呼ばない）。
- gakukoma_brain は anthropic/yaml をダミー化して import し、end_session のみを検証する
  （FaceRecognizer や実APIクライアントの初期化を避けるため __init__ は通さない）。
- 終了時に一時ディレクトリを完全に後始末する。

実行: python3 tests/test_wiki_quality.py
"""
import os
import sys
import json
import types
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

# --- 一時MEMORY_DIRを用意し、import前に環境変数へ設定 ---
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="gakukoma_wikitest_"))
os.environ["GAKUKOMA_MEMORY_DIR"] = str(_TMP_ROOT)

# brain/ を import パスに追加（このファイルは tests/ にある）
_BRAIN_DIR = Path(__file__).resolve().parent.parent / "brain"
sys.path.insert(0, str(_BRAIN_DIR))

import memory_processor as mp  # noqa: E402

# gakukoma_brain は重い依存（anthropic/yaml）を持つためダミー化してから import。
# end_session はモジュールグローバル MEMORY_DIR と self.local_history/session_id しか
# 使わないので、__init__ を通さずに検証できる。
sys.modules.setdefault("anthropic", types.ModuleType("anthropic"))
sys.modules.setdefault("yaml", types.ModuleType("yaml"))
import gakukoma_brain as gb  # noqa: E402


# ---------------------------------------------------------------------------
# スタブclient: messages.create がプロンプト内容で応答を出し分ける
# ---------------------------------------------------------------------------
class _StubContent:
    def __init__(self, text):
        self.text = text


class _StubResponse:
    def __init__(self, text):
        self.content = [_StubContent(text)]


class _StubMessages:
    def __init__(self, outer):
        self._outer = outer

    def create(self, **kwargs):
        model = kwargs.get("model", "")
        prompt = kwargs["messages"][0]["content"]
        return _StubResponse(self._outer._respond(model, prompt))


def _default_analysis():
    return {
        "summary": "テスト会話の要約。",
        "emotion_score": 2,
        "core_memory": "",
        "surprise_score": 0,
        "surprising_moment": "",
        "people_mentioned": [],
        "new_facts_about_people": "",
        "places_mentioned": [],
    }


class RoutingStub:
    """プロンプト内容で応答を出し分け、呼び出し（model, prompt）を全記録するスタブ。"""

    def __init__(self, analysis=None, people_extract=None, place_page=None, xref=None):
        self.analysis = analysis if analysis is not None else _default_analysis()
        self.people_extract = people_extract if people_extract is not None else {"people": []}
        self.place_page = place_page if place_page is not None else (
            "# 場所\n- 最後に訪れた日: 2026-07-01\n"
        )
        self.xref = xref if xref is not None else {"cross_references": []}
        self.calls = []  # [(model, prompt), ...]
        self.messages = _StubMessages(self)

    def _respond(self, model, prompt):
        self.calls.append((model, prompt))
        if "感情スコア基準" in prompt:
            return json.dumps(self.analysis, ensure_ascii=False)
        if "場所記憶ページを更新" in prompt:
            return self.place_page
        if "このログに登場した人物を抽出" in prompt:
            return json.dumps(self.people_extract, ensure_ascii=False)
        if "cross_references" in prompt:
            return json.dumps(self.xref, ensure_ascii=False)
        return "{}"

    def prompts(self):
        return [p for _, p in self.calls]


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------
def _reset_memory():
    """MEMORY_DIR をまっさらに戻す（テスト間の独立性確保）。"""
    if _TMP_ROOT.exists():
        shutil.rmtree(_TMP_ROOT)
    (_TMP_ROOT / "raw").mkdir(parents=True, exist_ok=True)


def _wiki():
    return _TMP_ROOT / "wiki"


def _write_person_page(name, text):
    d = _wiki() / "people"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.md"
    p.write_text(text, encoding="utf-8")
    return p


_RAW = "ユーザー: こんにちは\nがくこま: やあ！学長だ！"


# ---------------------------------------------------------------------------
# テスト本体
# ---------------------------------------------------------------------------
_results = []


def _check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((name, cond, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))


def test_a_person_write_path_step6_only():
    """(a) 1回のrunで人物ページの書き込み経路がStep6のみ（Sonnet全文再生成が発生しない）。"""
    _reset_memory()
    analysis = _default_analysis()
    analysis["people_mentioned"] = ["学長"]
    stub = RoutingStub(
        analysis=analysis,
        people_extract={"people": [{"name": "学長", "last_seen": "2026-07-01",
                                    "recent_topic": "一緒に遊んだ"}]},
    )
    mp.analyze_and_update_wiki(stub, _RAW, "2026-07-01")

    # 旧Step3の人物ページ全文再生成プロンプトが一度も呼ばれていないこと
    no_step3 = not any("人物記憶ページを更新" in p for p in stub.prompts())
    _check("(a) Sonnetによるpeople全文再生成コールが無い", no_step3)

    # 人物ページはStep6経由で作成されていること
    page = _wiki() / "people" / "学長.md"
    _check("(a) 人物ページはStep6で作成される", page.exists())
    if page.exists():
        txt = page.read_text(encoding="utf-8")
        _check("(a) Step6テンプレ（最後に会った日）で書かれている",
               "- 最後に会った日:" in txt and "- 最後に話した日:" not in txt,
               f"content={txt[:120]!r}")


def test_b_migrate_idempotent():
    """(b) 旧フィールド名がmigrateで統一され、2回目のmigrateは無変更（冪等）。"""
    _reset_memory()
    _write_person_page(
        "テスト太郎",
        "# テスト太郎\n- 最後に話した日: 2026-06-01\n- 関係性: 友人\n",
    )
    changed1 = mp.migrate_person_pages()
    txt = (_wiki() / "people" / "テスト太郎.md").read_text(encoding="utf-8")
    _check("(b) 旧フィールドが1件変換された", changed1 == 1, f"changed={changed1}")
    _check("(b) 「最後に話した日」が消え「最後に会った日」になる",
           "最後に話した日" not in txt and "- 最後に会った日: 2026-06-01" in txt,
           f"content={txt!r}")

    changed2 = mp.migrate_person_pages()
    _check("(b) 2回目のmigrateは無変更（冪等）", changed2 == 0, f"changed={changed2}")


def test_c_new_fact_no_duplicate():
    """(c) new_factsが「特徴・好み」に追記され、同一事実の2回目は重複追記されない。"""
    _reset_memory()
    date = "2026-07-01"
    fact = "ガクチョは猫を飼っている"
    stub = RoutingStub(
        people_extract={"people": [{"name": "ガクチョ", "last_seen": date,
                                    "recent_topic": "猫の話をした"}]},
    )

    # 1回目: 新規ページ作成 + 特徴・好みへ追記
    mp._update_person_wiki(stub, _wiki(), _RAW, date, new_facts=fact)
    page = _wiki() / "people" / "ガクチョ.md"
    txt1 = page.read_text(encoding="utf-8")
    fact_line = f"  - {fact}（{date}）"
    _check("(c) new_factが特徴・好み配下に追記される",
           "- 特徴・好み:" in txt1 and fact_line in txt1, f"content={txt1!r}")

    # 2回目: 既存ページ更新。同一事実は重複追記しない
    mp._update_person_wiki(stub, _wiki(), _RAW, date, new_facts=fact)
    txt2 = page.read_text(encoding="utf-8")
    _check("(c) 同一事実の2回目は重複しない",
           txt2.count(fact_line) == 1, f"count={txt2.count(fact_line)}")


def test_d_end_session_no_double_save():
    """(d) end_sessionを2回呼んでもrawファイルは1つ（保存後に履歴クリア）。"""
    _reset_memory()
    gb.MEMORY_DIR = _TMP_ROOT  # raw保存先を一時ディレクトリへ差し替え

    brain = object.__new__(gb.GAKUKOMABrain)  # __init__を通さずインスタンス化
    brain.local_history = [("こんにちは", "やあ！")]
    brain.session_id = "test-session-id"

    brain.end_session()
    cleared = brain.local_history == [] and brain.session_id is None
    _check("(d) 保存後に local_history と session_id がクリアされる", cleared,
           f"hist={brain.local_history} sid={brain.session_id}")

    brain.end_session()  # 2回目は履歴が空なので何もしない
    raw_files = list((_TMP_ROOT / "raw").glob("*.md"))
    _check("(d) 2回呼んでもrawファイルは1つ", len(raw_files) == 1,
           f"files={[f.name for f in raw_files]}")


def test_e_known_names_in_prompt():
    """(e) 既知ページ名が抽出プロンプトに含まれる（名寄せヒント注入）。"""
    _reset_memory()
    _write_person_page("南房総", "# 南房総\n- 最後に会った日: 2026-06-01\n")
    stub = RoutingStub()
    mp.analyze_and_update_wiki(stub, _RAW, "2026-07-01")

    included = any("南房総" in p for p in stub.prompts())
    _check("(e) 既知ページ名が抽出プロンプトに含まれる", included)


def test_f_unknown_name_not_paged():
    """(f) 「不明」を含む人物名・場所名はページ化されない。"""
    _reset_memory()
    analysis = _default_analysis()
    analysis["places_mentioned"] = ["不明な場所（左上）"]
    stub = RoutingStub(
        analysis=analysis,
        people_extract={"people": [
            {"name": "不明な人物（左上にいた人）", "last_seen": "2026-07-01",
             "recent_topic": "誰かがいた"},
        ]},
    )
    mp.analyze_and_update_wiki(stub, _RAW, "2026-07-01")

    people_dir = _wiki() / "people"
    places_dir = _wiki() / "places"
    people_unknown = list(people_dir.glob("*不明*.md")) if people_dir.exists() else []
    places_unknown = list(places_dir.glob("*不明*.md")) if places_dir.exists() else []
    _check("(f) 「不明」を含む人物ページが作られない", not people_unknown,
           f"files={[f.name for f in people_unknown]}")
    _check("(f) 「不明」を含む場所ページが作られない", not places_unknown,
           f"files={[f.name for f in places_unknown]}")


def main():
    tests = [
        test_a_person_write_path_step6_only,
        test_b_migrate_idempotent,
        test_c_new_fact_no_duplicate,
        test_d_end_session_no_double_save,
        test_e_known_names_in_prompt,
        test_f_unknown_name_not_paged,
    ]
    try:
        for t in tests:
            t()
    finally:
        # 完全後始末
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
