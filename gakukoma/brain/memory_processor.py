#!/usr/bin/env python3
"""
GAKUKOMA Memory Processor（OFFLINE処理）
深夜3時にsystemd timerから実行。未処理RAWログを日付ごとに分析してwikiを更新し、
処理済み台帳(processed.json)を見て古い処理済みログのみ削除する。
"""
from __future__ import annotations

import os
import json
import re
import random
from pathlib import Path
from datetime import datetime, timedelta

try:
    import anthropic
except ImportError:
    # anthropicが無い環境（テスト等）でもimport可能にする。
    # 実APIを使う経路（main→get_api_key→Anthropic）でのみ必要。
    # テストはスタブclientを渡すため anthropic 本体は不要。
    anthropic = None


def _safe_parse_json(text: str) -> dict:
    """LLMが返すJSONを堅牢にパースする。
    コードフェンス除去後、パース失敗時はリテラル改行をスペース化して再試行。
    """
    # コードフェンスを除去
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # JSON文字列値内のリテラル改行をスペースに置換して再試行
        # 構造的な改行もスペースになるがjson.loadsはwhitespaceを許容するため問題なし
        return json.loads(re.sub(r'\n', ' ', text))

# MEMORY_DIRは環境変数で差し替え可能（テスト用の最小変更）。未設定なら実機の既定パス。
MEMORY_DIR = Path(os.environ.get("GAKUKOMA_MEMORY_DIR", "/home/tukapontas/gakukoma/memory"))


def resolve_name(raw_name: str, category: str) -> str:
    """known_names.jsonを参照してエイリアスを正規名に解決する。
    category は 'people' または 'places'。
    テーブルにない名前はそのまま返す。
    """
    known_names_path = MEMORY_DIR / "wiki" / "known_names.json"
    if not known_names_path.exists():
        return raw_name
    try:
        table = json.loads(known_names_path.read_text(encoding="utf-8"))
        return table.get(category, {}).get(raw_name, raw_name)
    except Exception:
        return raw_name


def _build_known_names_hint(wiki_dir: Path) -> str:
    """名寄せ用の「既知の名前リスト」文字列を組み立てる。
    known_names.jsonのエイリアス表と、people/・places/の既存ページ名を列挙する。
    STT由来の表記ゆれ（例:「南房総/南坊村/南坊装」）を既知の名前へ正規化させる
    ためのプロンプト補助。該当が無ければ空文字を返す。
    """
    lines = []
    # エイリアス表
    known_names_path = wiki_dir / "known_names.json"
    if known_names_path.exists():
        try:
            table = json.loads(known_names_path.read_text(encoding="utf-8"))
            for category in ("people", "places"):
                for alias, canonical in table.get(category, {}).items():
                    lines.append(f"- 「{alias}」→「{canonical}」")
        except Exception:
            pass
    # 既存ページ名（people/・places/のファイル名）
    for subdir in ("people", "places"):
        d = wiki_dir / subdir
        if d.exists():
            names = sorted(f.stem for f in d.glob("*.md"))
            if names:
                label = "人物" if subdir == "people" else "場所"
                lines.append(f"- 既存{label}ページ: {', '.join(names)}")
    if not lines:
        return ""
    return (
        "\n\n【既知の名前リスト】（表記ゆれは必ずこのリストの表記に正規化すること）\n"
        + "\n".join(lines)
    )


def migrate_person_pages() -> int:
    """people/*.md の旧フィールド名を新フィールド名へ1回だけ変換する（冪等）。
    「最後に話した日」→「最後に会った日」に統一する。変換対象が無ければ何もしない。
    2回目以降は旧フィールドが残っていないため無変更（冪等）。
    返り値: 変更したファイル数。
    """
    people_dir = MEMORY_DIR / "wiki" / "people"
    if not people_dir.exists():
        return 0
    replacements = {
        "最後に話した日": "最後に会った日",
    }
    changed = 0
    for p in sorted(people_dir.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        new_text = text
        for old, new in replacements.items():
            new_text = new_text.replace(old, new)
        if new_text != text:
            p.write_text(new_text, encoding="utf-8")
            changed += 1
    if changed:
        print(f"migrate_person_pages: {changed}件のページを新フィールド名へ変換")
    return changed


OPENCLAW_CONFIG = "/home/tukapontas/.openclaw/openclaw.json"

def get_api_key() -> str:
    with open(OPENCLAW_CONFIG) as f:
        oc = json.load(f)
    return oc["models"]["providers"]["anthropic"]["apiKey"]

def _processed_ledger_path() -> Path:
    """処理済み台帳 raw/processed.json のパス。"""
    return MEMORY_DIR / "raw" / "processed.json"


def load_processed_ledger() -> dict:
    """処理済み台帳を読み込む。{"<ファイル名>": "<処理日時ISO>"}。壊れていれば空。"""
    p = _processed_ledger_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_processed_ledger(ledger: dict):
    """処理済み台帳を書き出す。"""
    p = _processed_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


def find_unprocessed_dates() -> list:
    """未処理のRAWログを日付ごとにグループ化し、古い日付順に返す。

    返り値: [(date_str, [Path, ...]), ...]（古い日付が先頭）
    条件:
      (a) processed.json に記録が無い
      (b) ファイル名日付が「今日より前」（当日分は翌run送り＝日次単位の意味を維持）
    """
    raw_dir = MEMORY_DIR / "raw"
    if not raw_dir.exists():
        return []
    ledger = load_processed_ledger()
    today = datetime.now().strftime("%Y-%m-%d")
    groups: dict = {}
    for p in sorted(raw_dir.glob("*.md")):
        if p.name in ledger:
            continue  # 処理済み
        date_str = p.stem[:10]
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue  # 日付として不正なファイル名はスキップ
        if date_str >= today:
            continue  # 当日・未来分は処理しない（YYYY-MM-DDは辞書順=日付順）
        groups.setdefault(date_str, []).append(p)
    return [(d, groups[d]) for d in sorted(groups.keys())]

def load_existing_wiki_page(page_path: Path) -> str:
    if page_path.exists():
        return page_path.read_text(encoding="utf-8").strip()
    return ""

def _rebuild_index(wiki_dir: Path, date: str, summary: str):
    """index.mdをwiki構造で全体再生成する。登場人物・場所はファイル走査で動的生成。"""
    index_path = wiki_dir / "index.md"

    # 既存の「最近の出来事」エントリを抽出（30件まで保持）
    existing_events = []
    if index_path.exists():
        existing_text = index_path.read_text(encoding="utf-8")
        for line in existing_text.split("\n"):
            if line.startswith("- **"):
                existing_events.append(line)

    # 新しいエントリを追加（重複しない場合のみ）
    new_entry = f"- **{date}**: {summary}"
    date_already_exists = any(f"**{date}**" in e for e in existing_events)
    if not date_already_exists:
        existing_events.append(new_entry)

    # 30件に絞る
    if len(existing_events) > 30:
        existing_events = existing_events[-30:]

    # 登場人物セクション: people/ ディレクトリを走査
    people_section = "## 登場人物\n"
    people_dir = wiki_dir / "people"
    if people_dir.exists():
        people_files = sorted(people_dir.glob("*.md"))
        if people_files:
            for pf in people_files:
                name = pf.stem
                people_section += f"- [{name}](people/{name}.md)\n"
        else:
            people_section += "（まだ記録なし）\n"
    else:
        people_section += "（まだ記録なし）\n"

    # 知っている場所セクション: places/ ディレクトリを走査
    places_section = "## 知っている場所\n"
    places_dir = wiki_dir / "places"
    if places_dir.exists():
        places_files = sorted(places_dir.glob("*.md"))
        if places_files:
            for pf in places_files:
                name = pf.stem
                places_section += f"- [{name}](places/{name}.md)\n"
        else:
            places_section += "（まだ記録なし）\n"
    else:
        places_section += "（まだ記録なし）\n"

    # 最近の出来事セクション
    events_section = "## 最近の出来事\n"
    for e in reversed(existing_events):  # 新しい順
        events_section += e + "\n"

    # index.md全体を書き直す
    content = f"# がくこまの記憶インデックス\n\n{people_section}\n{places_section}\n{events_section}"
    index_path.write_text(content, encoding="utf-8")
    print(f"index.md再構築: {date}")


def _append_to_log(wiki_dir: Path, date: str, updates: list):
    """wiki/log.md に append-only で実行記録を追記する"""
    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        log_path.write_text("# がくこまの記憶更新ログ\n\n", encoding="utf-8")

    existing = log_path.read_text(encoding="utf-8")
    entry_lines = "\n".join(f"  - {u}" for u in updates)
    new_entry = f"\n## [{date}] memory-update\n{entry_lines}\n"
    log_path.write_text(existing + new_entry, encoding="utf-8")


def _update_cross_references(client: anthropic.Anthropic, wiki_dir: Path, updated_pages: list = None):
    """wikiページのクロスリファレンスを更新する。

    updated_pages が指定された場合はそのページのみ更新（差分処理）。
    None または空リストの場合は全ページを対象にする。
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

    # 差分処理: updated_pages が指定された場合はそのページのみ対象にする
    if updated_pages:
        target_keys = [p for p in updated_pages if p in all_pages]
        if not target_keys:
            print("cross-reference: 更新ページなし。スキップ。")
            return
    else:
        target_keys = list(all_pages.keys())

    # 全ページの概要を渡す（参照用）
    pages_summary = "\n\n---\n\n".join(
        f"=== {key} ===\n{content[:600]}"
        for key, content in all_pages.items()
    )

    target_clause = (
        f"対象ページ（本日更新分のみ）: {', '.join(target_keys)}\n"
        "上記の対象ページについてのみ cross_references を返すこと。他のページは不要。"
        if updated_pages else
        "全ページについて cross_references を返すこと。"
    )

    xref_prompt = f"""ロボット「がくこま」の記憶wikiの以下のページ一覧を読んでください。

{pages_summary}

各ページについて、**他のページとの関連**を抽出してください。

以下のJSONを返してください：
{{
  "cross_references": [
    {{
      "page": "people/学長",
      "related_places": ["リビング", "がくこまの部屋（和室）"],
      "related_people": ["そのさん", "ソータ"],
      "related_memories": ["core_memories"]
    }}
  ]
}}

{target_clause}

注意:
- 実際に存在するページのみ記載する
- related_places / related_people / related_memories は存在しない場合は空配列 [] にする
- JSONのみ返すこと"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": xref_prompt}]
        )
        xref_data = _safe_parse_json(resp.content[0].text)

        for item in xref_data.get("cross_references", []):
            page_key = item["page"]  # 例: "people/学長"

            # 構造化データからマークダウンを組み立てる（改行問題を回避）
            related_lines = []
            for place in item.get("related_places", []):
                related_lines.append(f"- 場所: [{place}](../places/{place}.md)")
            for person in item.get("related_people", []):
                related_lines.append(f"- 人物: [{person}](../people/{person}.md)")
            for mem in item.get("related_memories", []):
                related_lines.append(f"- 記憶: [{mem}](../{mem}.md)")
            if not related_lines:
                continue
            related_section = "## 関連\n" + "\n".join(related_lines)

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


def generate_daily_dream(client: anthropic.Anthropic):
    """毎日の深夜処理: 過去記憶からランダム連想を生成し dreams.md に追記する。

    処理手順:
    1. wiki以下の全記憶ページ（people/, places/, core_memories.md, surprises.md）を収集
    2. ランダムに2〜3件をサンプリング
    3. claude-haiku にランダム連想を依頼
    4. 結果を wiki/dreams.md に追記
    """
    wiki_dir = MEMORY_DIR / "wiki"
    if not wiki_dir.exists():
        print("generate_daily_dream: wikiなし。スキップ。")
        return

    # 全記憶ページを収集
    memory_pages = {}
    for subdir in ["people", "places"]:
        d = wiki_dir / subdir
        if d.exists():
            for f in d.glob("*.md"):
                content = f.read_text(encoding="utf-8").strip()
                if content:
                    memory_pages[f"{subdir}/{f.stem}"] = content[:400]

    for fname in ["core_memories.md", "surprises.md"]:
        p = wiki_dir / fname
        if p.exists():
            content = p.read_text(encoding="utf-8").strip()
            if content:
                memory_pages[fname] = content[:400]

    if len(memory_pages) < 2:
        print("generate_daily_dream: 記憶ページ不足（2件未満）。スキップ。")
        return

    # ランダムに2〜3件サンプリング
    sample_count = min(3, len(memory_pages))
    sampled = random.sample(list(memory_pages.items()), sample_count)

    pages_text = "\n\n---\n\n".join(
        f"=== {key} ===\n{content}"
        for key, content in sampled
    )

    today = datetime.now().strftime("%Y-%m-%d")

    dream_prompt = f"""ロボット「がくこま」の記憶の断片を以下に示します。

{pages_text}

これらの記憶を自由に結びつけて、がくこまが「昨日ふと思ったんだけど」「夢でこんなこと考えてた」として翌朝の会話で自然に話せる「思いつき・ひらめき・連想」を1〜2文で生成してください。

ルール:
- がくこまらしい子供っぽい好奇心で表現する（タチコマ的な明るさ）
- 記憶の表面的な繰り返しではなく、意外なつながりや気づきを含める
- 1〜2文の短い文章のみ返すこと（Markdownや説明文は不要）"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": dream_prompt}]
        )
        dream_text = resp.content[0].text.strip()
        if not dream_text:
            print("generate_daily_dream: 空の応答。スキップ。")
            return

        # wiki/dreams.md に追記
        dreams_path = wiki_dir / "dreams.md"
        if not dreams_path.exists():
            dreams_path.write_text("# がくこまの夢・ふと思ったこと\n\n", encoding="utf-8")

        existing = dreams_path.read_text(encoding="utf-8")

        # 本日エントリが既に存在する場合は上書きしない
        if f"## {today}" in existing:
            print(f"generate_daily_dream: {today} のエントリが既にあります。スキップ。")
            return

        # ソースページを記録（デバッグ用）
        source_keys = [key for key, _ in sampled]
        source_note = f"<!-- ソース: {', '.join(source_keys)} -->"

        new_entry = f"\n## {today}\n{dream_text}\n{source_note}\n"
        dreams_path.write_text(existing + new_entry, encoding="utf-8")
        print(f"夢・ひらめき記録: {dream_text[:60]}...")

    except Exception as e:
        print(f"generate_daily_dream エラー: {e}")


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
  "health_score": 0,
  "suggestions": ["改善提案（優先度順・最大3件）"]
}}

health_scoreは0〜10の整数（wiki全体の健全度。10=完璧に整合・充実）を設定してください。
注意: JSONのみ返すこと。"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": lint_prompt}]
        )
        lint_result = _safe_parse_json(resp.content[0].text)

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

    except Exception as e:
        print(f"lintエラー: {e}")


def analyze_and_update_wiki(client: anthropic.Anthropic, raw_logs: str, date: str) -> bool:
    """RAWログを分析してwikiの各ページを更新する。

    date: 処理対象日（YYYY-MM-DD）。呼び出し側がグループの日付を渡す。
    返り値: 分析成功=True / 分析失敗（Step 1例外）=False。
            Falseの場合、呼び出し側は processed.json に登録しない（次回再試行）。
    """

    if not raw_logs.strip():
        print("本日のRAWログなし。スキップ。")
        return True

    wiki_dir = MEMORY_DIR / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # 既存のwikiページを読み込む
    existing_core = load_existing_wiki_page(wiki_dir / "core_memories.md")

    today = date

    # 名寄せ用の既知の名前リスト（Step1分析・場所抽出・人物抽出で共有）
    known_names_hint = _build_known_names_hint(wiki_dir)

    # ---- Step 1: 会話分析 + 感情スコア ----
    analysis_prompt = f"""以下はロボット「がくこま」の本日（{today}）の会話ログです。

<logs>
{raw_logs[:8000]}
</logs>

<existing_core_memories>
{existing_core or "（まだなし）"}
</existing_core_memories>

以下を分析してJSON形式で返してください：
{{
  "summary": "本日の会話の要約（3〜5文）",
  "emotion_score": 0〜10の整数（下記基準に従って採点）,
  "core_memory": "感情スコアが7以上の場合のみ記述。がくこまが長期記憶すべき重要な出来事（1〜2文）。7未満は空文字",
  "surprise_score": 0〜10の整数（0=予想通り、5=少し意外、10=全く予想外の出来事）,
  "surprising_moment": "surprise_scoreが6以上の場合のみ記述。何が予想外だったか（1文）。6未満は空文字",
  "people_mentioned": ["会話に出てきた人物名のリスト"],
  "new_facts_about_people": "人物に関して新しくわかったこと（例：ガクチョは猫を飼っている）",
  "places_mentioned": ["会話や移動で出てきた場所名のリスト"]
}}

感情スコア基準（必ずこの基準に従って採点すること）:
- 0〜2: 日常的な短い会話、命令実行のみ、特に記憶すべきことなし
- 3〜4: 楽しい・普通の会話、すでに知っている人や場所の話
- 5〜6: 印象的な会話、新しい情報を得た、少し特別だった
- 7: かなり特別な体験。初めての場所探索、新しい能力の発見など → core_memoryに記録
- 8〜9: 非常に重要な体験。初めて会う人、重要な関係性の確立、感情が強く動いた → core_memoryに記録
- 10: 人生レベルの出来事（がくこまの存在や目的に関わる重大体験）

重要: すでにcore_memoriesに記録済みの体験の「繰り返し」はスコアを2〜3下げること。
{known_names_hint}

注意: JSONのみ返すこと。説明文は不要。"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": analysis_prompt}]
        )
        analysis_text = resp.content[0].text.strip()
        # JSON部分だけ抽出
        if "```" in analysis_text:
            analysis_text = analysis_text.split("```")[1]
            if analysis_text.startswith("json"):
                analysis_text = analysis_text[4:]
        analysis = json.loads(analysis_text)
    except Exception as e:
        print(f"分析エラー: {e}")
        # 最低限のサマリーだけ保存して終了。
        # ただし processed.json への登録はしない（Falseを返し次回再試行させる）。
        _rebuild_index(wiki_dir, today, f"（分析失敗）本日は会話ログあり")
        return False

    print(f"分析完了: emotion_score={analysis.get('emotion_score', 0)}, surprise_score={analysis.get('surprise_score', 0)}")

    # ---- Step 2: core_memories.md の更新 ----
    emotion_score = analysis.get("emotion_score", 0)
    core_memory_text = analysis.get("core_memory", "")
    if emotion_score >= 7 and core_memory_text:
        core_path = wiki_dir / "core_memories.md"
        existing = existing_core or "# がくこまの忘れられない記憶\n"
        new_entry = f"\n## {today}（感情スコア: {emotion_score}）\n{core_memory_text}\n"
        core_path.write_text(existing + new_entry, encoding="utf-8")
        print(f"核記憶を保存: {core_memory_text[:50]}...")

    # ---- Step 2b: surprises.md の更新 ----
    surprise_score = analysis.get("surprise_score", 0)
    surprising_moment = analysis.get("surprising_moment", "")
    if surprise_score >= 6 and surprising_moment:
        surprises_path = wiki_dir / "surprises.md"
        if not surprises_path.exists():
            surprises_path.write_text("# がくこまが驚いた瞬間\n\n", encoding="utf-8")
        existing_surprises = surprises_path.read_text(encoding="utf-8")
        surprise_entry = f"\n## {today}（驚きスコア: {surprise_score}）\n{surprising_moment}\n"
        surprises_path.write_text(existing_surprises + surprise_entry, encoding="utf-8")
        print(f"驚き記録: {surprising_moment[:50]}...")

    # 更新ログ追跡用リスト（cross-reference 差分処理にも使用）
    update_log = []
    updated_pages = []
    if emotion_score >= 7 and core_memory_text:
        update_log.append(f"core_memory: emotion_score={emotion_score}")
    if surprise_score >= 6 and surprising_moment:
        update_log.append(f"surprises: surprise_score={surprise_score}")

    # ---- Step 3(廃止): people全文書き直しはStep6 _update_person_wiki に一本化 ----
    # かつてはここでSonnetにページ全文を再生成させていたが、Step6と二重更新になり
    # フォーマット不一致（「話した日」vs「会った日」）でページがハイブリッド化していた。
    # 人物ページの書き手はStep6のみ。people_mentioned / new_facts_about_people は
    # Step6へ渡して反映する（下記 Step5 参照）。

    # ---- Step 3b: places/ ページの更新 ----
    for place in analysis.get("places_mentioned", []):
        place = resolve_name(place, "places")
        # 「不明」を含む場所名はページ化しない（コード強制。プロンプト任せにしない）
        if "不明" in place:
            print(f"place-wiki: 「不明」を含む場所名をスキップ: {place}")
            continue
        place_path = wiki_dir / "places" / f"{place}.md"
        place_path.parent.mkdir(parents=True, exist_ok=True)
        existing_place = load_existing_wiki_page(place_path)

        place_update_prompt = f"""ロボット「がくこま」の場所記憶ページを更新してください。

場所名: {place}
既存ページ:
{existing_place or "（新規）"}

本日の会話サマリー: {analysis.get('summary', '')}
最終更新日: {today}

以下のフォーマットでページ全体を返してください（既存情報を保持しながら更新）：
# {place}
- 最後に訪れた日: {today}
- 訪問回数: （わかる場合のみ）
- 場所の種類: （部屋・廊下・屋外など）
- 特徴・雰囲気: （箇条書き）
- 関連する人物: （この場所によく居る人）
- つながる場所: （ここからどこへ行けるか・どこから来るか）
- がくこまにとっての意味: （一言）
{known_names_hint}

注意: ページのMarkdownのみ返すこと。"""

        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": place_update_prompt}]
            )
            place_path.write_text(resp.content[0].text.strip(), encoding="utf-8")
            print(f"place-wiki更新: {place}")
            update_log.append(f"place:{place}")
            updated_pages.append(f"places/{place}")
        except Exception as e:
            print(f"place-wiki更新エラー（{place}）: {e}")

    # ---- Step 4: index.md の更新 ----
    summary = analysis.get("summary", "（サマリーなし）")
    _rebuild_index(wiki_dir, today, summary)

    # ---- Step 5: person-wiki の更新（人物ページの唯一の書き手）----
    # new_facts_about_people を渡して「特徴・好み」へ反映させる。
    # 更新したページキー（people/<name>）を受け取り cross-reference の差分対象に含める。
    person_pages = _update_person_wiki(
        client, wiki_dir, raw_logs, today,
        new_facts=analysis.get("new_facts_about_people", ""),
    )
    for pk in person_pages:
        updated_pages.append(pk)
        update_log.append(f"person:{pk.split('/')[-1]}")

    # ---- Step 6: cross-reference の更新（更新ページのみ差分処理）----
    _update_cross_references(client, wiki_dir, updated_pages)

    # ---- log.md への記録 ----
    if not update_log:
        update_log.append(f"summary: {summary[:60]}")
    _append_to_log(wiki_dir, today, update_log)

    print("wiki更新完了")
    return True


def _append_new_fact(content: str, fact: str, date: str) -> str:
    """人物ページに新事実を「- 特徴・好み:」配下へ `  - {事実}（{date}）` で追記する。
    既に同一行があればスキップ（重複防止）。節が無ければ追加する。冪等。
    """
    fact = (fact or "").strip()
    if not fact:
        return content
    fact_line = f"  - {fact}（{date}）"
    if fact_line in content.split("\n"):
        return content  # 同一事実の重複追記を防ぐ
    if "- 特徴・好み:" in content:
        content = content.replace("- 特徴・好み:", f"- 特徴・好み:\n{fact_line}", 1)
    else:
        content = content.rstrip() + f"\n- 特徴・好み:\n{fact_line}\n"
    return content


def _update_person_wiki(client: anthropic.Anthropic, wiki_dir: Path, raw_logs: str,
                        date: str, new_facts: str = "") -> list:
    """
    RAWログに登場した人物を特定し、wiki/people/各ページを更新する。
    人物ページの唯一の書き手（旧Step3廃止に伴い一本化）。

    処理手順:
    1. Haikuに「このログに登場した人物と、その人との出来事を抽出してJSON返せ」と依頼
    2. JSON結果を基に wiki/people/{name}.md の「最後に会った日」「最近の話題」を更新
    3. ページが存在しない人物は新規作成（初めて会った日=今日）
    4. new_facts（Step1の new_facts_about_people）があれば「特徴・好み」へ追記（重複防止）

    new_facts: 人物について新しく判明したこと（1つの文字列）。空なら追記しない。
    返り値: 更新/作成したページキーのリスト（例: ["people/学長"]）。cross-reference差分用。

    JSONスキーマ（Haikuに返させる形式）:
    {
      "people": [
        {
          "name": "学長",
          "last_seen": "2026-04-23",
          "recent_topic": "リビングを一緒に探索した",
          "impression": "優しく楽しい人"  // optional
        }
      ]
    }
    """
    if not raw_logs.strip():
        return []

    people_dir = wiki_dir / "people"
    people_dir.mkdir(parents=True, exist_ok=True)

    known_names_hint = _build_known_names_hint(wiki_dir)

    extract_prompt = f"""以下はロボット「がくこま」の会話ログです（日付: {date}）。

<logs>
{raw_logs[:6000]}
</logs>

このログに登場した人物を抽出してください。

以下のJSON形式で返してください：
{{
  "people": [
    {{
      "name": "人物名（例: 学長、そのさん）",
      "last_seen": "{date}",
      "recent_topic": "この日に何をしたか・話したか（1〜2文）",
      "impression": "がくこまが感じたこの人の印象（任意・1文）"
    }}
  ]
}}

注意:
- 会話ログに実際に登場した人物のみ抽出すること
- 人物名が不明な場合は「不明な人物」として記録しない（スキップ）
- JSONのみ返すこと{known_names_hint}"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": extract_prompt}]
        )
        extract_text = resp.content[0].text.strip()
        if "```" in extract_text:
            extract_text = extract_text.split("```")[1]
            if extract_text.startswith("json"):
                extract_text = extract_text[4:]
        extract_data = json.loads(extract_text)
    except Exception as e:
        print(f"_update_person_wiki 抽出エラー: {e}")
        return []

    updated_keys = []
    for person_entry in extract_data.get("people", []):
        name = person_entry.get("name", "").strip()
        if not name:
            continue
        name = resolve_name(name, "people")
        # 「不明」を含む人物名はページ化しない（コード強制。プロンプト任せにしない）
        if "不明" in name:
            print(f"_update_person_wiki: 「不明」を含む人物名をスキップ: {name}")
            continue
        last_seen = person_entry.get("last_seen", date)
        recent_topic = person_entry.get("recent_topic", "")
        impression = person_entry.get("impression", "")

        person_path = people_dir / f"{name}.md"

        if person_path.exists():
            # 既存ページを更新：「最後に会った日」と「最近の話題」を更新
            content = person_path.read_text(encoding="utf-8")

            # 「最後に会った日」を更新
            import re
            content = re.sub(
                r"- 最後に会った日:.*",
                f"- 最後に会った日: {last_seen}",
                content
            )

            # 「最近の話題」セクションに追記
            topic_entry = f"  - {last_seen}: {recent_topic}"
            if "- 最近の話題:" in content:
                content = content.replace(
                    "- 最近の話題:",
                    f"- 最近の話題:\n{topic_entry}"
                )
            else:
                content = content.rstrip() + f"\n- 最近の話題:\n{topic_entry}\n"

            # がくこまの印象を更新（任意）
            if impression:
                if "- がくこまの印象:" in content:
                    content = re.sub(
                        r"- がくこまの印象:.*",
                        f"- がくこまの印象: {impression}",
                        content
                    )
                else:
                    content = content.rstrip() + f"\n- がくこまの印象: {impression}\n"

            # コンパクション: 「最近の話題」が4件以上なら古い分を「行動パターン」に圧縮
            topic_lines = []
            in_topic = False
            for line in content.split("\n"):
                if line.strip() == "- 最近の話題:":
                    in_topic = True
                    continue
                if in_topic:
                    if line.startswith("  - "):
                        topic_lines.append(line)
                    elif line.startswith("- "):
                        in_topic = False

            if len(topic_lines) > 3:
                to_archive = topic_lines[:-3]
                keep = topic_lines[-3:]
                archive_text = "\n".join(
                    f"  （過去: {t.strip()[2:]}）" for t in to_archive
                )
                if "- 行動パターン:" in content:
                    content = content.replace(
                        "- 行動パターン:",
                        f"- 行動パターン:\n{archive_text}"
                    )
                else:
                    content = content.rstrip() + f"\n- 行動パターン:\n{archive_text}\n"
                new_topic_block = "- 最近の話題:\n" + "\n".join(keep)
                content = re.sub(
                    r"- 最近の話題:(\n  - .*)+",
                    new_topic_block,
                    content
                )
                print(f"  コンパクション実施: {name} ({len(to_archive)}件を行動パターンへ)")

            # 新事実を「特徴・好み」へ反映（重複防止）
            content = _append_new_fact(content, new_facts, date)

            person_path.write_text(content, encoding="utf-8")
            print(f"_update_person_wiki 更新: {name}")

        else:
            # 新規ページ作成
            lines = [
                f"# {name}",
                "",
                f"- 初めて会った日: {date}",
                f"- 最後に会った日: {last_seen}",
                "- 関係性: （未記録）",
                "- 特徴・好み:",
                "- 最近の話題:",
                f"  - {date}: {recent_topic}",
                "- 行動パターン:",
                "  （Haikuが推論・週次更新）",
                "- がくこまの印象:",
                f"  {impression}" if impression else "  （未記録）",
            ]
            content = "\n".join(lines) + "\n"
            # 新事実を「特徴・好み」へ反映（重複防止）
            content = _append_new_fact(content, new_facts, date)
            person_path.write_text(content, encoding="utf-8")
            print(f"_update_person_wiki 新規作成: {name}")

        updated_keys.append(f"people/{name}")

    return updated_keys


def process_unprocessed_logs(client: anthropic.Anthropic):
    """未処理の日付を古い順に処理する。日付ごとに分析成功した分だけ台帳に記録。

    分析失敗（analyze_and_update_wiki が False を返す／例外）時は登録しない
    ＝次回runで再試行される。
    """
    groups = find_unprocessed_dates()
    if not groups:
        print("未処理のRAWログなし。スキップ。")
        return

    for date_str, files in groups:
        # 同日付のログを結合（既存の結合フォーマットを踏襲）
        parts = []
        for p in files:
            content = p.read_text(encoding="utf-8").strip()
            if content:
                parts.append(content)
        raw_logs = "\n\n---\n\n".join(parts)

        print(f"--- {date_str} の未処理ログを分析（{len(files)}件）---")
        try:
            success = analyze_and_update_wiki(client, raw_logs, date_str)
        except Exception as e:
            # 想定外の例外も登録しない（次回再試行）
            print(f"{date_str} の処理で例外: {e}。processed登録せず。")
            continue

        if success:
            ledger = load_processed_ledger()
            now_iso = datetime.now().isoformat()
            for p in files:
                ledger[p.name] = now_iso
            save_processed_ledger(ledger)
            print(f"processed.json 記録: {date_str}（{len(files)}件）")
        else:
            print(f"{date_str} は分析失敗のため未登録（次回再試行）")


def cleanup_old_raw_logs():
    """processed.json に記録があり、かつ7日超のRAWログのみ削除する。

    削除したファイルは台帳からも除去する（台帳の無限成長防止）。
    未処理（台帳に無い）ファイルは7日超でも削除しない。
    """
    cutoff = datetime.now() - timedelta(days=7)
    raw_dir = MEMORY_DIR / "raw"
    if not raw_dir.exists():
        return
    ledger = load_processed_ledger()
    count = 0
    ledger_changed = False
    for p in list(raw_dir.glob("*.md")):
        if p.name not in ledger:
            continue  # 未処理ログは削除しない
        try:
            # ファイル名の日付でフィルタ（YYYY-MM-DD_HHMMSS.md）
            date_str = p.stem[:10]
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                p.unlink()
                count += 1
                del ledger[p.name]
                ledger_changed = True
            except OSError:
                pass
    if ledger_changed:
        save_processed_ledger(ledger)
    if count:
        print(f"古いRAWログ {count}件 削除")


def main():
    print(f"=== Memory Processor 開始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    client = anthropic.Anthropic(api_key=get_api_key())
    # 旧フィールド名（最後に話した日 等）を新フィールド名へ統一（冪等・対象なしなら無変更）
    migrate_person_pages()
    # 未処理の日付を古い順にキャッチアップ処理（成功分のみ台帳登録）
    process_unprocessed_logs(client)
    cleanup_old_raw_logs()

    # 毎日: 夢・ひらめき生成（RAWログ有無にかかわらず実行）
    print("--- 夢・ひらめき生成 ---")
    generate_daily_dream(client)

    # 月曜日（weekday==0）のみ lint を実行
    if datetime.now().weekday() == 0:
        print("--- 週次Lint実行 ---")
        lint_wiki(client)

    print("=== Memory Processor 完了 ===")


if __name__ == "__main__":
    main()
