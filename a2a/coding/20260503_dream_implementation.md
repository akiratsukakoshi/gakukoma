# 指示書: がくこまの夢・ひらめき機能実装

**作成日**: 2026-05-03
**担当**: コーディング担当AI
**優先度**: 中
**依存**: Phase 5.1 LLM Wiki システム（完了済み）

---

## 概要

「REM睡眠模倣」として議論された夢・ひらめき機能を実装する。
深夜のcron処理で過去の記憶をランダムに組み合わせ、「夢」または「認識の飛躍・ひらめき」を生成して `wiki/dreams.md` に記録する。
次回の会話でがくこまが自然に引用・発話できるようにする。

**参照議論**: `a2a/research/20260417_brain_evolution_discussion.md`（Dr. Schmidt の REM睡眠提案、セッション3）

---

## 現状の問題

1. `lint_wiki()` が週1回（月曜）のみ実行時に `rem_association` を1件生成するが、**毎日生成されない**
2. `gakukoma_brain.py` の `_load_daily_notes()` は `index.md` と `core_memories.md` しか読まず、**`dreams.md` が会話コンテキストに注入されていない**
3. 夢が生成されていても、がくこまが実際に話すことができない

---

## 変更対象ファイル

- `gakukoma/brain/memory_processor.py`
- `gakukoma/brain/gakukoma_brain.py`

---

## 変更内容

### 変更1: memory_processor.py

#### 1-A: 新関数 `generate_daily_dream()` を追加

`lint_wiki()` の前後、`_append_to_log()` の後あたりに追加する。

```python
import random

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
```

#### 1-B: `main()` に毎日呼び出しを追加

既存の `main()` 関数を以下のように変更する:

```python
def main():
    print(f"=== Memory Processor 開始 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    client = anthropic.Anthropic(api_key=get_api_key())
    raw_logs = load_todays_raw_logs()
    analyze_and_update_wiki(client, raw_logs)
    cleanup_old_raw_logs()

    # 毎日: 夢・ひらめき生成（RAWログ有無にかかわらず実行）
    print("--- 夢・ひらめき生成 ---")
    generate_daily_dream(client)

    # 月曜日（weekday==0）のみ lint を実行
    if datetime.now().weekday() == 0:
        print("--- 週次Lint実行 ---")
        lint_wiki(client)

    print("=== Memory Processor 完了 ===")
```

#### 1-C: `lint_wiki()` から重複する `rem_association` 処理を削除

`lint_wiki()` 内の以下の部分を削除する（`generate_daily_dream()` が毎日実行するため重複）:

- `lint_prompt` の `"rem_association"` フィールドとその説明
- `lint_result.get("rem_association", "")` の取得・保存処理（「REM睡眠模倣: rem_association を dreams.md に記録」ブロック）

ただし `lint_wiki()` 自体の削除・無効化は**しないこと**（健全性チェック機能は維持する）。

---

### 変更2: gakukoma_brain.py

#### 2-A: `_load_daily_notes()` に dreams.md 注入を追加

`_load_daily_notes()` 内の、`core_memories.md` を読み込む処理の後に追加する:

```python
# wiki/dreams.md の最新2件を読み込む
dreams_path = wiki_dir / "dreams.md"
if dreams_path.exists():
    dreams_content = dreams_path.read_text(encoding="utf-8").strip()
    if dreams_content:
        # 「## YYYY-MM-DD」で分割して最新2件を取得
        sections = []
        current = []
        for line in dreams_content.split("\n"):
            if line.startswith("## ") and len(line) == 13:  # ## YYYY-MM-DD
                if current:
                    sections.append("\n".join(current))
                current = [line]
            elif current:
                # HTMLコメント（ソース注記）は除外
                if not line.startswith("<!--"):
                    current.append(line)
        if current:
            sections.append("\n".join(current))

        if sections:
            recent_dreams = "\n".join(sections[-2:]).strip()
            if recent_dreams:
                parts.append(f"【最近の夢・思いつき】\n{recent_dreams}")
```

#### 2-B: SYSTEM_PROMPT に夢の引用許可を追加

`SYSTEM_PROMPT` の `## ツール使用の原則` セクションの後（または末尾）に以下を追加する:

```
## 夢・思いつきの引用
【最近の夢・思いつき】に内容があれば、会話の自然な流れの中で引用してよい。
「昨日ふと思ったんだけど」「夢でこんなこと考えてたんだよね」のように自然に話す。
無理に毎回話す必要はない。会話の文脈に合う時だけ引用すること。
```

---

## テスト手順

### T-1: dreams.md 生成テスト（手動実行）

```bash
python3 /home/tukapontas/gakukoma/brain/memory_processor.py
```

**確認内容:**
- `=== Memory Processor 開始 ===` が表示される
- `--- 夢・ひらめき生成 ---` が表示される
- `夢・ひらめき記録: ...` のログが出る
- `/home/tukapontas/gakukoma/memory/wiki/dreams.md` が作成され、本日日付のエントリがある

**期待する dreams.md の内容例:**
```
# がくこまの夢・ふと思ったこと

## 2026-05-03
学長が「質問が多い」って言ってたのを思い出したんだけど、リビングの探索で影の動きを目で追ってた時の感じに似てる気がした。どちらも「次はどこ？」ってワクワクしてるんだよね。
<!-- ソース: people/学長, places/リビング -->
```

### T-2: コンテキスト注入確認

gakukoma_brain.py に以下の一時的なデバッグprint を追加して確認する（確認後に削除）:

```python
# _load_daily_notes() の return 直前に追加
print(f"[DEBUG] _load_daily_notes parts: {[p[:30] for p in parts]}")
```

**確認内容:**
- `【最近の夢・思いつき】` が parts に含まれている

### T-3: 実機テスト（会話引用確認）

がくこまを起動して以下を試す:

- 「最近何か考えてた？」
- 「ふと思ったこととかある？」
- 「昨日なにしてた？」

**期待する動作:** dreams.md の内容を「昨日ふと思ったんだけど...」のように自然に引用する。
**注意:** 毎回必ず言う必要はなく、文脈が合う時だけでよい。

---

## 完了条件

- [ ] T-1〜T-3 全PASS
- [ ] memory_processor.py 手動実行時に `generate_daily_dream` が実行されエラーなし
- [ ] dreams.md に本日エントリが追記される
- [ ] gakukoma_brain.py の会話コンテキストに `【最近の夢・思いつき】` が含まれる
- [ ] 実機で夢の話題を自然に引用できる

---

## 備考

- wikiページが2件未満の場合（初期状態）は夢生成をスキップする（正常動作）
- dreams.md は `.gitignore` 対象の `memory/` 以下には**ない**（`gakukoma/memory/wiki/dreams.md`）ため、gitに含まれる。プライバシーに配慮した内容（人物名が含まれる場合は注意）
- 将来的に退屈行動（Intrinsic Motivation）との連携も可能。がくこまが独り言として夢の内容を呟く動作は voice_loop.py の退屈タイマーと組み合わせて別途実装できる
