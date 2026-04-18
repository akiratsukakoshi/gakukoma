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
    """今日のRAWログを全て読み込んで結合する"""
    today = datetime.now().strftime("%Y-%m-%d")
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

def analyze_and_update_wiki(client: anthropic.Anthropic, raw_logs: str):
    """RAWログを分析してwikiの各ページを更新する"""

    if not raw_logs.strip():
        print("本日のRAWログなし。スキップ。")
        return

    wiki_dir = MEMORY_DIR / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # 既存のwikiページを読み込む
    existing_index = load_existing_wiki_page(wiki_dir / "index.md")
    existing_core = load_existing_wiki_page(wiki_dir / "core_memories.md")

    today = datetime.now().strftime("%Y-%m-%d")

    # ---- Step 1: 会話分析 + 感情スコア ----
    analysis_prompt = f"""以下はロボット「がくこま」の本日（{today}）の会話ログです。

<logs>
{raw_logs[:3000]}
</logs>

以下を分析してJSON形式で返してください：
{{
  "summary": "本日の会話の要約（3〜5文）",
  "emotion_score": 0〜10の整数（0=退屈・普通、5=楽しい会話、10=非常に感情的・印象的な出来事）,
  "core_memory": "感情スコアが8以上の場合のみ記述。がくこまが長期記憶すべき重要な出来事（1〜2文）。8未満は空文字",
  "people_mentioned": ["会話に出てきた人物名のリスト"],
  "new_facts_about_people": "人物に関して新しくわかったこと（例：ガクチョは猫を飼っている）",
  "places_mentioned": ["会話や移動で出てきた場所名のリスト"]
}}

注意: JSONのみ返すこと。説明文は不要。"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
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
        _append_to_index(wiki_dir, today, f"（分析失敗）本日は会話ログあり")
        return

    print(f"分析完了: emotion_score={analysis.get('emotion_score', 0)}")

    # ---- Step 2: core_memories.md の更新 ----
    emotion_score = analysis.get("emotion_score", 0)
    core_memory_text = analysis.get("core_memory", "")
    if emotion_score >= 8 and core_memory_text:
        core_path = wiki_dir / "core_memories.md"
        existing = existing_core or "# がくこまの忘れられない記憶\n"
        new_entry = f"\n## {today}（感情スコア: {emotion_score}）\n{core_memory_text}\n"
        core_path.write_text(existing + new_entry, encoding="utf-8")
        print(f"核記憶を保存: {core_memory_text[:50]}...")

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
- 関係性: （製作者・友人等）
- 特徴・好み: （箇条書き）
- 最近の話題: （{today}時点）
- 行動パターン: （わかっている場合）

注意: ページのMarkdownのみ返すこと。"""

        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{"role": "user", "content": update_prompt}]
            )
            person_path.write_text(resp.content[0].text.strip(), encoding="utf-8")
            print(f"person-wiki更新: {person}")
        except Exception as e:
            print(f"person-wiki更新エラー（{person}）: {e}")

    # ---- Step 4: index.md の更新 ----
    summary = analysis.get("summary", "（サマリーなし）")
    _append_to_index(wiki_dir, today, summary)

    print("wiki更新完了")


def _append_to_index(wiki_dir: Path, date: str, summary: str):
    """index.mdに本日のエントリを追記する"""
    index_path = wiki_dir / "index.md"
    if not index_path.exists():
        index_path.write_text("# がくこまの記憶インデックス\n\n", encoding="utf-8")

    existing = index_path.read_text(encoding="utf-8")

    # 同日エントリが既にあれば上書きしない
    if date in existing:
        return

    new_entry = f"- **{date}**: {summary}\n"
    # 直近30日分のみ保持（それ以上は末尾を削除）
    lines = existing.split("\n")
    diary_lines = [l for l in lines if l.startswith("- **")]
    if len(diary_lines) > 30:
        # 古い行を削除（先頭ヘッダーは保持）
        header = [l for l in lines if not l.startswith("- **")]
        lines = header + diary_lines[-29:]
        existing = "\n".join(lines)
        if not existing.endswith("\n"):
            existing += "\n"

    index_path.write_text(existing + new_entry, encoding="utf-8")
    print(f"index.md更新: {date}")


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
    print("=== Memory Processor 完了 ===")


if __name__ == "__main__":
    main()
