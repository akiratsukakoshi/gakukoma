#!/usr/bin/env python3
"""
WP1 記憶パイプラインのテスト（実API・実機不要）。

- 一時ディレクトリを GAKUKOMA_MEMORY_DIR に設定してから memory_processor を import する。
- client は messages.create が固定JSONを返すスタブ。
- 終了時に一時ディレクトリを完全に後始末する。

実行: python3 tests/test_memory_pipeline.py
"""
import os
import sys
import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# --- 一時MEMORY_DIRを用意し、import前に環境変数へ設定 ---
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="gakukoma_memtest_"))
os.environ["GAKUKOMA_MEMORY_DIR"] = str(_TMP_ROOT)

# brain/ を import パスに追加（このファイルは tests/ にある）
_BRAIN_DIR = Path(__file__).resolve().parent.parent / "brain"
sys.path.insert(0, str(_BRAIN_DIR))

import memory_processor as mp  # noqa: E402


# ---------------------------------------------------------------------------
# スタブclient: messages.create が固定JSONテキストを返す（実APIは呼ばない）
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
        if self._outer.raise_exc:
            raise RuntimeError("stub API error（意図的な失敗）")
        return _StubResponse(self._outer.text)


class StubClient:
    """messages.create が固定テキストを返すスタブ。raise_exc=Trueで例外を投げる。"""
    # 分析Step1が json.loads できる最小の妥当な応答
    DEFAULT_ANALYSIS = json.dumps({
        "summary": "テスト会話の要約。",
        "emotion_score": 2,
        "core_memory": "",
        "surprise_score": 0,
        "surprising_moment": "",
        "people_mentioned": [],
        "new_facts_about_people": "",
        "places_mentioned": [],
    }, ensure_ascii=False)

    def __init__(self, text=None, raise_exc=False):
        self.text = text if text is not None else self.DEFAULT_ANALYSIS
        self.raise_exc = raise_exc
        self.messages = _StubMessages(self)


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------
def _reset_memory():
    """MEMORY_DIR をまっさらに戻す（テスト間の独立性確保）。"""
    if _TMP_ROOT.exists():
        shutil.rmtree(_TMP_ROOT)
    (_TMP_ROOT / "raw").mkdir(parents=True, exist_ok=True)


def _write_raw(date_str, content="ユーザー: こんにちは\nがくこま: やあ！", suffix="120000"):
    """raw/<date>_<suffix>.md を作成し Path を返す。"""
    p = _TMP_ROOT / "raw" / f"{date_str}_{suffix}.md"
    p.write_text(content, encoding="utf-8")
    return p


def _read_ledger():
    p = _TMP_ROOT / "raw" / "processed.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _days_ago(n):
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# テスト本体
# ---------------------------------------------------------------------------
_results = []


def _check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((name, cond, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))


def test_a_multiple_dates_processed_oldest_first():
    """(a) 複数日付の未処理ログ→全日付が古い順に処理され processed.json に記録される。"""
    _reset_memory()
    d1, d2, d3 = _days_ago(5), _days_ago(4), _days_ago(3)
    f1, f2, f3 = _write_raw(d1), _write_raw(d2), _write_raw(d3)

    # 古い順に返るか
    groups = mp.find_unprocessed_dates()
    dates = [d for d, _ in groups]
    _check("(a) find_unprocessed_dates が古い順", dates == sorted(dates) and dates == [d1, d2, d3],
           f"got={dates}")

    mp.process_unprocessed_logs(StubClient())
    ledger = _read_ledger()
    all_recorded = all(f.name in ledger for f in (f1, f2, f3))
    _check("(a) 全日付が processed.json に記録", all_recorded, f"ledger keys={list(ledger)}")


def test_b_today_not_processed():
    """(b) 当日日付のログは処理されない。"""
    _reset_memory()
    today = datetime.now().strftime("%Y-%m-%d")
    ftoday = _write_raw(today)

    groups = mp.find_unprocessed_dates()
    excluded = today not in [d for d, _ in groups]
    _check("(b) 当日は find_unprocessed_dates に含まれない", excluded)

    mp.process_unprocessed_logs(StubClient())
    ledger = _read_ledger()
    _check("(b) 当日ログは processed.json に記録されない", ftoday.name not in ledger,
           f"ledger keys={list(ledger)}")
    _check("(b) 当日ログのファイルは残る", ftoday.exists())


def test_c_old_unprocessed_not_deleted():
    """(c) 7日超でも未処理のログは削除されない。"""
    _reset_memory()
    old = _days_ago(20)
    fold = _write_raw(old)
    # 台帳に登録せずに cleanup を実行
    mp.cleanup_old_raw_logs()
    _check("(c) 7日超でも未処理ログは削除されない", fold.exists())


def test_d_old_processed_deleted_and_ledger_pruned():
    """(d) 7日超かつ処理済みのログは削除され、台帳からも消える。"""
    _reset_memory()
    old = _days_ago(20)
    fold = _write_raw(old)
    # 台帳に処理済みとして登録
    mp.save_processed_ledger({fold.name: datetime.now().isoformat()})

    mp.cleanup_old_raw_logs()
    deleted = not fold.exists()
    ledger = _read_ledger()
    pruned = fold.name not in ledger
    _check("(d) 7日超かつ処理済みログは削除される", deleted)
    _check("(d) 削除に伴い台帳からも除去される", pruned, f"ledger keys={list(ledger)}")


def test_e_analysis_failure_not_recorded():
    """(e) 分析失敗（スタブが例外）時に processed.json へ記録されない。"""
    _reset_memory()
    d = _days_ago(3)
    f = _write_raw(d)

    mp.process_unprocessed_logs(StubClient(raise_exc=True))
    ledger = _read_ledger()
    _check("(e) 分析失敗時は processed.json に記録されない", f.name not in ledger,
           f"ledger keys={list(ledger)}")
    _check("(e) 分析失敗ログのファイルは残る（次回再試行可能）", f.exists())


def main():
    tests = [
        test_a_multiple_dates_processed_oldest_first,
        test_b_today_not_processed,
        test_c_old_unprocessed_not_deleted,
        test_d_old_processed_deleted_and_ledger_pruned,
        test_e_analysis_failure_not_recorded,
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
