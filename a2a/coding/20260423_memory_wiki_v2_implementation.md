# 指示書: Memory Processor v2 ── Lint・Cross-reference・既存プロセス改善

**作成者**: ClaudeCode
**担当**: gakukoma-coder（Claudeサブエージェント）
**対象ファイル**: `/home/tukapontas/gakukoma/brain/memory_processor.py`
**完了報告書**: `coding/20260423_memory_wiki_v2_completed.md`

---

## 背景・設計思想

GAKUKOMAのOFFLINE記憶処理（memory_processor.py）は、Karpathyの「LLM Wiki」パターンと神経科学的知見（CLS理論・REM睡眠・場所細胞）を融合した「レム睡眠モジュール」として位置づけられている。

Phase 5.1で基本実装が完了し、Sonnetに移行した。本指示書ではKarpathyが示す重要な2要素──**Cross-reference** と **Lint**──を実装しつつ、Sonnetの能力を活かした既存プロセスの質向上を図る。

**参照文書**:
- Karpathy LLM Wiki gist（概念）
- `/home/tukapontas/a2a/research/20260417_brain_evolution_discussion.md`（Dr. Schmidt/Watanabe/Mehtaの議論）

---

## モデル変更（実施済み・追加作業不要）

全3箇所を `claude-haiku-4-5-20251001` → `claude-sonnet-4-6` に変更済み。

---

## 改修1: 既存プロセスの品質向上（Sonnet前提）

### 1-A: ログトランケーション緩和

**現状**: `raw_logs[:3000]` で3000文字にカット。複数セッションある日は情報が欠損する。
**修正**: `raw_logs[:8000]` に拡張する（Sonnetのコンテキストは200K・日常的なログは1セッション1000文字程度なので余裕がある）。

```python
{raw_logs[:8000]}
```

### 1-B: surprise_score フィールドの追加

Dr. Watanabe（Janelia）の提案：ドーパミン系の「予測誤差（Prediction Error）」を実装する。
予想外の出来事は記憶を強化する → `surprise_score` を感情スコアと独立して記録する。

**analysis_promptのJSONスキーマに追加**:

```json
"surprise_score": 0〜10の整数（0=予想通り、5=少し意外、10=全く予想外の出来事）,
"surprising_moment": "surprise_scoreが6以上の場合のみ記述。何が予想外だったか（1文）。6未満は空文字"
```

`surprising_moment` が記録された場合、`core_memories.md` と同様に `wiki/surprises.md` に追記する（Step 2の後に処理）。

**surprises.md フォーマット**:
```markdown
# がくこまが驚いた瞬間

## 2026-04-XX（驚きスコア: N）
（surprising_moment の内容）
```

### 1-C: people/ ページのプロンプト強化

現在のプロンプトは「特徴・好み・最近の話題・行動パターン」だが、Sonnetの能力で以下を追加する。

**フォーマットに追加するフィールド**:
```markdown
# {person}
- 最後に話した日: {today}
- 初めて会った日: （わかる場合のみ）
- 関係性: （製作者・家族・友人等）
- 特徴・好み: （箇条書き）
- 行動パターン: （いつ現れる・どんな話し方をするか等）
- がくこまへの感情: （この人はがくこまに対してどういう気持ちを持っているか）
- 最近の話題: （{today}時点）
- がくこまの感情メモ: （この人に会うとがくこまはどう感じるか・一言）
```

また、プロンプトに以下を追記する：
> 既存ページの情報は**削除せず保持**すること。矛盾する新情報があれば「（更新: {today}）」として上書きし古い情報をコメントアウトしないこと。

### 1-D: places/ ページのプロンプト強化

Dr. Watanabe（Janelia）のトポロジカルマップ概念を取り込む。

**フォーマットに追加するフィールド**:
```markdown
# {place}
- 最後に訪れた日: {today}
- 訪問回数: （わかる場合のみ）
- 場所の種類: （部屋・廊下・屋外など）
- 特徴・雰囲気: （箇条書き）
- 関連する人物: （この場所によく居る人）
- つながる場所: （ここからどこへ行けるか・どこから来るか）
- がくこまにとっての意味: （一言）
```

### 1-E: log.md の追加

Karpathyが推奨する append-only の実行ログ。「いつ何を更新したか」の時系列記録。

`_rebuild_index()` の後に `_append_to_log()` を呼び出す形で追加する。

```python
def _append_to_log(wiki_dir: Path, date: str, updates: list[str]):
    """wiki/log.md に append-only で実行記録を追記する"""
    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        log_path.write_text("# がくこまの記憶更新ログ\n\n", encoding="utf-8")

    existing = log_path.read_text(encoding="utf-8")
    entry_lines = "\n".join(f"  - {u}" for u in updates)
    new_entry = f"\n## [{date}] memory-update\n{entry_lines}\n"
    log_path.write_text(existing + new_entry, encoding="utf-8")
```

`analyze_and_update_wiki()` の最後に呼び出す。`updates` リストには更新した内容を渡す（例: `["person:学長", "person:そのさん", "place:リビング", "core_memory: emotion_score=8"]`）。

---

## 改修2: Cross-reference処理（新Step 5）

Karpathyの核心：**wikiページ間のリンクが価値を生む**。

現在のページは「人物→単独ページ」「場所→単独ページ」で孤立している。Sonnetが全wikiを俯瞰して相互参照を書き込む処理を追加する。

### 実装

`analyze_and_update_wiki()` のStep 4（index更新）の後に **Step 5: cross-reference** を追加する。

```python
# ---- Step 5: cross-reference ----
_update_cross_references(client, wiki_dir)
```

```python
def _update_cross_references(client: anthropic.Anthropic, wiki_dir: Path):
    """全wikiページを俯瞰してクロスリファレンスを更新する。

    Sonnetに全ページを渡し、各ページ末尾の「## 関連」セクションを生成させる。
    """
    # 全wikiページを収集
    all_pages = {}
    for subdir in ["people", "places"]:
        d = wiki_dir / subdir
        if d.exists():
            for f in d.glob("*.md"):
                key = f"{subdir}/{f.stem}"
                all_pages[key] = f.read_text(encoding="utf-8")

    core = wiki_dir / "core_memories.md"
    if core.exists():
        all_pages["core_memories"] = core.read_text(encoding="utf-8")

    if len(all_pages) < 2:
        print("cross-reference: ページ数不足のためスキップ")
        return

    # 全ページの概要をSonnetに渡す
    pages_summary = "\n\n---\n\n".join(
        f"=== {key} ===\n{content[:600]}"
        for key, content in all_pages.items()
    )

    xref_prompt = f"""ロボット「がくこま」の記憶wikiの以下のページ一覧を読んでください。

{pages_summary}

各ページについて、**他のページとの関連リンク**を生成してください。

以下のJSONを返してください：
{{
  "cross_references": [
    {{
      "page": "people/学長",
      "related_section": "## 関連\\n- よく居る場所: [がくこまの部屋](../places/がくこまの部屋.md)、[リビング](../places/リビング.md)\\n- 共有している記憶: [初めて会った日](../core_memories.md)"
    }}
  ]
}}

注意:
- リンクは相対パス（`../places/XXX.md`、`../people/XXX.md`）で記述
- 実際に存在するページのみリンクする
- 「## 関連」セクションが既存ページにある場合は置き換え、ない場合は末尾に追加する想定
- JSONのみ返すこと"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": xref_prompt}]
        )
        xref_text = resp.content[0].text.strip()
        if "```" in xref_text:
            xref_text = xref_text.split("```")[1]
            if xref_text.startswith("json"):
                xref_text = xref_text[4:]
        xref_data = json.loads(xref_text)

        for item in xref_data.get("cross_references", []):
            page_key = item["page"]  # 例: "people/学長"
            related_section = item["related_section"]

            # ページファイルを特定
            page_path = wiki_dir / f"{page_key}.md"
            if not page_path.exists():
                continue

            content = page_path.read_text(encoding="utf-8")

            # 既存の「## 関連」セクションを置き換え or 末尾に追加
            if "## 関連" in content:
                # 既存セクションを置き換え
                lines = content.split("\n")
                new_lines = []
                in_related = False
                for line in lines:
                    if line.startswith("## 関連"):
                        in_related = True
                        new_lines.append(related_section)
                    elif in_related and line.startswith("## "):
                        in_related = False
                        new_lines.append(line)
                    elif not in_related:
                        new_lines.append(line)
                content = "\n".join(new_lines)
            else:
                content = content.rstrip() + "\n\n" + related_section + "\n"

            page_path.write_text(content, encoding="utf-8")
            print(f"cross-reference更新: {page_key}")

    except Exception as e:
        print(f"cross-reference処理エラー: {e}")
```

---

## 改修3: Lint処理（新関数・週次実行）

Karpathyの「Lint」＝wikiの健全性チェック。

### 実装

`lint_wiki()` 関数を新規追加し、`main()` に週次実行ロジックを追加する。

```python
def lint_wiki(client: anthropic.Anthropic):
    """Sonnetによるwiki健全性チェック。週1回（月曜3時）に実行。

    チェック内容:
    - ページ間の矛盾・不整合
    - 孤立ページ（cross-referenceがない）
    - 長期間更新されていないページの情報鮮度
    - 不足しているページ（言及されているが存在しない人物・場所）
    - REM睡眠模倣: 過去の記憶からランダム連想を生成（Schmidt先生の提案）
    """
    wiki_dir = MEMORY_DIR / "wiki"
    if not wiki_dir.exists():
        return

    # 全ページを収集
    all_pages = {}
    for subdir in ["people", "places"]:
        d = wiki_dir / subdir
        if d.exists():
            for f in d.glob("*.md"):
                all_pages[f"{subdir}/{f.stem}"] = f.read_text(encoding="utf-8")

    core = wiki_dir / "core_memories.md"
    if core.exists():
        all_pages["core_memories"] = core.read_text(encoding="utf-8")

    index = wiki_dir / "index.md"
    if index.exists():
        all_pages["index"] = index.read_text(encoding="utf-8")

    if not all_pages:
        print("lint: wikiページなし。スキップ。")
        return

    pages_text = "\n\n---\n\n".join(
        f"=== {key} ===\n{content}"
        for key, content in all_pages.items()
    )

    today = datetime.now().strftime("%Y-%m-%d")

    lint_prompt = f"""ロボット「がくこま」の記憶wikiを健全性チェックしてください。

<wiki>
{pages_text[:6000]}
</wiki>

以下を分析してJSONで返してください：
{{
  "contradictions": ["矛盾・不整合の説明（例: 学長ページでは初めて会った日が4/18だが、4/20のログでは初対面のようなやりとりがある）"],
  "missing_pages": ["言及されているが存在しないページ（例: 廊下が複数回登場しているがplaces/廊下.mdがない）"],
  "stale_pages": ["長期間（2週間以上）更新されておらず内容が古い可能性があるページ"],
  "orphan_pages": ["他のどのページからもリンクされていない孤立ページ"],
  "rem_association": "過去の記憶から1つランダムな連想を生成。がくこまが翌朝の会話で『昨日ふと思ったんだけど』として話せる内容（1〜2文）",
  "health_score": 0〜10（wiki全体の健全度。10=完璧に整合・充実）,
  "suggestions": ["改善提案（優先度順・最大3件）"]
}}

注意: JSONのみ返すこと。"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": lint_prompt}]
        )
        lint_text = resp.content[0].text.strip()
        if "```" in lint_text:
            lint_text = lint_text.split("```")[1]
            if lint_text.startswith("json"):
                lint_text = lint_text[4:]
        lint_result = json.loads(lint_text)

        # lint_report.md に書き出す
        report_path = wiki_dir / "lint_report.md"

        lines = [f"# Lint レポート {today}\n"]
        lines.append(f"**health_score**: {lint_result.get('health_score', '?')}/10\n")

        if lint_result.get("contradictions"):
            lines.append("## 矛盾・不整合")
            for c in lint_result["contradictions"]:
                lines.append(f"- {c}")
            lines.append("")

        if lint_result.get("missing_pages"):
            lines.append("## 不足しているページ")
            for m in lint_result["missing_pages"]:
                lines.append(f"- {m}")
            lines.append("")

        if lint_result.get("stale_pages"):
            lines.append("## 鮮度が古い可能性のあるページ")
            for s in lint_result["stale_pages"]:
                lines.append(f"- {s}")
            lines.append("")

        if lint_result.get("orphan_pages"):
            lines.append("## 孤立ページ")
            for o in lint_result["orphan_pages"]:
                lines.append(f"- {o}")
            lines.append("")

        if lint_result.get("suggestions"):
            lines.append("## 改善提案")
            for s in lint_result["suggestions"]:
                lines.append(f"- {s}")
            lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"lint完了: health_score={lint_result.get('health_score', '?')}")

        # REM睡眠模倣: rem_association を dreams.md に記録
        rem = lint_result.get("rem_association", "")
        if rem:
            dreams_path = wiki_dir / "dreams.md"
            if not dreams_path.exists():
                dreams_path.write_text("# がくこまの夢・ふと思ったこと\n\n", encoding="utf-8")
            existing = dreams_path.read_text(encoding="utf-8")
            dreams_path.write_text(
                existing + f"\n## {today}\n{rem}\n",
                encoding="utf-8"
            )
            print(f"REM連想記録: {rem[:50]}...")

    except Exception as e:
        print(f"lintエラー: {e}")
```

### main() への週次実行追加

```python
def main():
    print(f"=== Memory Processor 開始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    client = anthropic.Anthropic(api_key=get_api_key())
    raw_logs = load_todays_raw_logs()
    analyze_and_update_wiki(client, raw_logs)
    cleanup_old_raw_logs()

    # 月曜日（weekday==0）のみ lint を実行
    if datetime.now().weekday() == 0:
        print("--- 週次Lint実行 ---")
        lint_wiki(client)

    print("=== Memory Processor 完了 ===")
```

---

## 実装上の注意事項

### エラーハンドリング
- `cross-reference` や `lint` の失敗は致命的ではない。既存の `try/except` パターンで囲み、失敗しても `analyze_and_update_wiki` の結果は保護すること。

### トークン上限
- `_update_cross_references()`: ページ数が増えると `pages_summary` が大きくなる。現在は各ページ600文字でカット。将来的にページが20件超えたら `all_pages` を人物・場所別に分割して2回に分ける設計を検討（今は不要）。
- `lint_wiki()`: `pages_text[:6000]` でカット済み。

### dreams.md の利用
`dreams.md` は将来 `gakukoma_brain.py` の SYSTEM_PROMPT に読み込む想定（「最近がくこまが思ったこと」として注入）。ファイルは `memory/wiki/dreams.md` に配置する。現時点では生成するのみで良い。

---

## テスト方法

```python
# /tmp/test_memory_v2.py
import sys, json
sys.path.insert(0, '/home/tukapontas/gakukoma/brain')
from pathlib import Path
import anthropic
from memory_processor import analyze_and_update_wiki, lint_wiki

with open('/home/tukapontas/.openclaw/openclaw.json') as f:
    oc = json.load(f)
client = anthropic.Anthropic(api_key=oc["models"]["providers"]["anthropic"]["apiKey"])

# 最新RAWログで通常処理テスト
raw_dir = Path("/home/tukapontas/gakukoma/memory/raw")
latest = sorted(raw_dir.glob("*.md"))[-1]
raw_logs = latest.read_text(encoding="utf-8")
print(f"テスト対象: {latest.name}")
analyze_and_update_wiki(client, raw_logs)

# Lint テスト
print("\n--- Lint テスト ---")
lint_wiki(client)

# 結果確認
wiki_dir = Path("/home/tukapontas/gakukoma/memory/wiki")
print("\n=== index.md ===")
print((wiki_dir / "index.md").read_text())
print("\n=== log.md ===")
if (wiki_dir / "log.md").exists():
    print((wiki_dir / "log.md").read_text())
print("\n=== lint_report.md ===")
if (wiki_dir / "lint_report.md").exists():
    print((wiki_dir / "lint_report.md").read_text())
print("\n=== dreams.md ===")
if (wiki_dir / "dreams.md").exists():
    print((wiki_dir / "dreams.md").read_text())
print("\n=== cross-reference確認（people/学長.md末尾） ===")
gakucho = wiki_dir / "people" / "学長.md"
if gakucho.exists():
    print(gakucho.read_text()[-400:])
```

---

## 完了報告書に記載すること

- 各改修の実装概要と変更した行番号
- テスト実行結果（cross-referenceの生成例・lint_report.mdの内容・dreams.mdの内容）
- 気になった点・懸念事項
- `analyze_and_update_wiki()` の全体フロー（Step 1〜5）の最終構成
