#!/usr/bin/env python3
"""
GAKUKOMA Memory Processor（OFFLINE処理）
深夜3時にcronから実行。RAWログを分析してwikiを更新し、古いログを削除する。
"""

import json
import anthropic
from pathlib import Path
from datetime import datetime, timedelta

MEMORY_DIR = Path("/home/tukapontas/gakukoma/memory")
OPENCLAW_CONFIG = "/home/tukapontas/.openclaw/openclaw.json"

def get_api_key() -> str:
    with open(OPENCLAW_CONFIG) as f:
        oc = json.load(f)
    return oc["models"]["providers"]["anthropic"]["apiKey"]

def load_todays_raw_logs() -> str:
    """前日のRAWログを全て読み込んで結合する（深夜3時実行のため前日分を処理）"""
    today = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    raw_dir = MEMORY_DIR / "raw"
    if not raw_dir.exists():
        return ""
    logs = []
    for p in sorted(raw_dir.glob(f"{today}_*.md")):
        content = p.read_text(encoding="utf-8").strip()
        if content:
            logs.append(content)
    return "\n\n---\n\n".join(logs)

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


def analyze_and_update_wiki(client: anthropic.Anthropic, raw_logs: str):
    """RAWログを分析してwikiの各ページを更新する"""

    if not raw_logs.strip():
        print("本日のRAWログなし。スキップ。")
        return

    wiki_dir = MEMORY_DIR / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # 既存のwikiページを読み込む
    existing_core = load_existing_wiki_page(wiki_dir / "core_memories.md")

    today = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

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
  "core_memory": "感情スコアが8以上の場合のみ記述。がくこまが長期記憶すべき重要な出来事（1〜2文）。8未満は空文字",
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
- 7: かなり特別な体験。初めての場所探索、新しい能力の発見など
- 8〜9: 非常に重要な体験。初めて会う人、重要な関係性の確立、感情が強く動いた
- 10: 人生レベルの出来事（がくこまの存在や目的に関わる重大体験）

重要: すでにcore_memoriesに記録済みの体験の「繰り返し」はスコアを2〜3下げること。

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
        # 最低限のサマリーだけ保存して終了
        _rebuild_index(wiki_dir, today, f"（分析失敗）本日は会話ログあり")
        return

    print(f"分析完了: emotion_score={analysis.get('emotion_score', 0)}, surprise_score={analysis.get('surprise_score', 0)}")

    # ---- Step 2: core_memories.md の更新 ----
    emotion_score = analysis.get("emotion_score", 0)
    core_memory_text = analysis.get("core_memory", "")
    if emotion_score >= 8 and core_memory_text:
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

    # 更新ログ追跡用リスト
    update_log = []
    if emotion_score >= 8 and core_memory_text:
        update_log.append(f"core_memory: emotion_score={emotion_score}")
    if surprise_score >= 6 and surprising_moment:
        update_log.append(f"surprises: surprise_score={surprise_score}")

    # ---- Step 3: people/ ページの更新 ----
    for person in analysis.get("people_mentioned", []):
        person_path = wiki_dir / "people" / f"{person}.md"
        person_path.parent.mkdir(parents=True, exist_ok=True)
        existing_person = load_existing_wiki_page(person_path)

        update_prompt = f"""ロボット「がくこま」の人物記憶ページを更新してください。

人物名: {person}
既存ページ:
{existing_person or "（新規）"}

本日の会話サマリー: {analysis.get('summary', '')}
新しく判明したこと: {analysis.get('new_facts_about_people', '')}
最終更新日: {today}

以下のフォーマットでページ全体を返してください（既存情報を保持しながら更新）：
# {person}
- 最後に話した日: {today}
- 初めて会った日: （わかる場合のみ）
- 関係性: （製作者・家族・友人等）
- 特徴・好み: （箇条書き）
- 行動パターン: （いつ現れる・どんな話し方をするか等）
- がくこまへの感情: （この人はがくこまに対してどういう気持ちを持っているか）
- 最近の話題: （{today}時点）
- がくこまの感情メモ: （この人に会うとがくこまはどう感じるか・一言）

重要: 既存ページの情報は**削除せず保持**すること。矛盾する新情報があれば「（更新: {today}）」として上書きし古い情報をコメントアウトしないこと。
注意: ページのMarkdownのみ返すこと。"""

        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                messages=[{"role": "user", "content": update_prompt}]
            )
            person_path.write_text(resp.content[0].text.strip(), encoding="utf-8")
            print(f"person-wiki更新: {person}")
            update_log.append(f"person:{person}")
        except Exception as e:
            print(f"person-wiki更新エラー（{person}）: {e}")

    # ---- Step 3b: places/ ページの更新 ----
    for place in analysis.get("places_mentioned", []):
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
        except Exception as e:
            print(f"place-wiki更新エラー（{place}）: {e}")

    # ---- Step 4: index.md の更新 ----
    summary = analysis.get("summary", "（サマリーなし）")
    _rebuild_index(wiki_dir, today, summary)

    # ---- Step 5: cross-reference の更新 ----
    _update_cross_references(client, wiki_dir)

    # ---- log.md への記録 ----
    if not update_log:
        update_log.append(f"summary: {summary[:60]}")
    _append_to_log(wiki_dir, today, update_log)

    print("wiki更新完了")


def _append_to_index(wiki_dir: Path, date: str, summary: str):
    """後方互換性のためのラッパー。_rebuild_index()に委譲する。"""
    _rebuild_index(wiki_dir, date, summary)


def cleanup_old_raw_logs():
    """7日超のRAWログを削除する"""
    cutoff = datetime.now() - timedelta(days=7)
    raw_dir = MEMORY_DIR / "raw"
    if not raw_dir.exists():
        return
    count = 0
    for p in raw_dir.glob("*.md"):
        try:
            # ファイル名の日付でフィルタ（YYYY-MM-DD_HHMMSS.md）
            date_str = p.stem[:10]
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                p.unlink()
                count += 1
        except (ValueError, OSError):
            pass
    if count:
        print(f"古いRAWログ {count}件 削除")


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


if __name__ == "__main__":
    main()
