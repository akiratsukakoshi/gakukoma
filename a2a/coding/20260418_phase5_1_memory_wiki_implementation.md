# 指示書: Phase 5.1 — LLM Wiki型記憶システム + 退屈行動（Intrinsic Motivation）

> **作成日**: 2026-04-18
> **担当**: Antigravity（コーディング担当AI）
> **優先度**: 高
> **背景**: `a2a/plan/phase5_action_plan.md` Phase 5.1 / `a2a/research/20260417_brain_evolution_discussion.md`

---

## 概要

現在のフラットな日次ログ（`/home/tukapontas/.openclaw/workspace/memory/YYYY-MM-DD.md`）を、**3層構造のLLM Wiki型記憶システム**に置き換える。

加えて、がくこまがアイドル時に自発的に周囲へ働きかける「**退屈行動**」を実装する。

### 変更のポイント

| 現在 | 変更後 |
|---|---|
| 生ログを直接コンテキスト注入（トークン大・ノイズ多） | wikiインデックス + 核記憶を注入（軽量・高品質） |
| end_session()がユーザー発言だけ記録 | 完全な会話ログ + 感情スコア + wiki更新を記録 |
| アイドル時は何もしない | 60秒後にランダム視線 / 稀に移動・呟き |
| 記憶は無限蓄積（忘却なし） | 7日でRAW削除、30日でエピソード圧縮 |

### ONLINE/OFFLINE設計

```
ONLINE（会話中）:
  wiki/index.md + wiki/core_memories.md をコンテキスト注入（read only, ~1,000 tokens）
  ← 既存の直近3日ログ注入から切り替え

OFFLINE（セッション終了後・深夜3時cron）:
  raw/本日ログ → Haikuが分析 → wiki/各ページ更新 + 感情スコア付与 + 7日超RAW削除
```

---

## 実装対象ファイル

| ファイル | 操作 | 概要 |
|---|---|---|
| `/home/tukapontas/gakukoma/brain/gakukoma_brain.py` | **修正** | 記憶ディレクトリ変更・end_session強化・コンテキスト注入変更 |
| `/home/tukapontas/gakukoma/brain/memory_processor.py` | **新規作成** | OFFLINE処理：wiki更新・感情スコア・忘却処理 |
| `/home/tukapontas/gakukoma/voice_loop/voice_loop.py` | **修正** | 退屈行動（アイドルタイマー追加） |
| crontab | **追加** | 深夜3時にmemory_processor.py実行 |

---

## 1. ディレクトリ構造の作成

実装開始前に以下のディレクトリを作成すること:

```bash
mkdir -p /home/tukapontas/gakukoma/memory/raw
mkdir -p /home/tukapontas/gakukoma/memory/episodes
mkdir -p /home/tukapontas/gakukoma/memory/wiki/people
mkdir -p /home/tukapontas/gakukoma/memory/wiki/places
```

### 各ディレクトリの役割

```
/home/tukapontas/gakukoma/memory/
├── raw/              # セッションごとの生ログ（保存7日・その後削除）
│   └── 2026-04-18_143052.md   # ファイル名: YYYY-MM-DD_HHMMSS.md
├── episodes/         # 週次サマリー（保存30日・その後wiki統合）
│   └── 2026-W16.md
└── wiki/             # 長期記憶（恒久保存）
    ├── index.md            # wikiの全ページ一覧（Haikuが毎回参照）
    ├── core_memories.md    # 感情スコア8以上の核記憶
    ├── people/             # 人物ページ
    │   └── ガクチョ.md
    └── places/             # 場所ページ（Phase 5.3で活用）
```

---

## 2. `gakukoma_brain.py` の修正

### 2-1. 定数の追加（ファイル先頭のインポート・定数部分）

既存の `PRIMING_EXAMPLES` の直後に以下を追加:

```python
MEMORY_DIR = Path("/home/tukapontas/gakukoma/memory")
LEGACY_MEMORY_DIR = Path("/home/tukapontas/.openclaw/workspace/memory")  # 旧ディレクトリ
```

### 2-2. `end_session()` の置き換え

現在の `end_session()` を以下で**完全に置き換え**る:

```python
def end_session(self):
    """おやすみ時に呼ぶ。完全な会話ログをraw/に保存する。"""
    if not self.local_history:
        return

    # raw/ に完全なセッションログを保存
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    raw_path = MEMORY_DIR / "raw" / f"{timestamp}.md"
    MEMORY_DIR.joinpath("raw").mkdir(parents=True, exist_ok=True)

    lines = [
        f"# セッションログ {timestamp}",
        f"session_id: {self.session_id}",
        "",
    ]
    for user_text, response in self.local_history:
        lines.append(f"**ユーザー**: {user_text}")
        lines.append(f"**がくこま**: {response}")
        lines.append("")

    raw_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"セッションログを {raw_path} に保存しました")

    # 旧ディレクトリへの後方互換ログも残す（念のため）
    today = datetime.now().strftime("%Y-%m-%d")
    legacy_path = LEGACY_MEMORY_DIR / f"{today}.md"
    if legacy_path.exists():
        # 旧ファイルがある場合はそのまま（上書きしない）
        pass
```

### 2-3. `_load_daily_notes()` の置き換え

現在の `_load_daily_notes()` を以下で**完全に置き換え**る:

```python
def _load_daily_notes(self, days: int = 3) -> str:
    """
    wikiのindex.md と core_memories.md を読み込んで返す。
    wikiが存在しない場合（初期状態）は旧ディレクトリのログをフォールバックで読む。
    """
    wiki_dir = MEMORY_DIR / "wiki"
    index_path = wiki_dir / "index.md"
    core_path = wiki_dir / "core_memories.md"

    parts = []

    # wiki/index.md が存在する場合（Phase 5.1稼働後）
    if index_path.exists():
        index_content = index_path.read_text(encoding="utf-8").strip()
        if index_content:
            parts.append(f"【記憶インデックス】\n{index_content}")

    # wiki/core_memories.md が存在する場合
    if core_path.exists():
        core_content = core_path.read_text(encoding="utf-8").strip()
        if core_content:
            parts.append(f"【忘れられない記憶】\n{core_content}")

    # wikiがまだ空（初期状態）の場合は旧ディレクトリをフォールバック
    if not parts:
        notes = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            # 新ディレクトリのrawログを試す
            raw_files = sorted((MEMORY_DIR / "raw").glob(f"{date}_*.md")) if (MEMORY_DIR / "raw").exists() else []
            if raw_files:
                for p in raw_files[-1:]:  # 当日最後のセッションのみ
                    content = p.read_text(encoding="utf-8").strip()
                    if content:
                        notes.append(f"[{date}]\n{content[:500]}")  # 500文字に制限
            else:
                # 旧ディレクトリ
                legacy_path = LEGACY_MEMORY_DIR / f"{date}.md"
                if legacy_path.exists():
                    content = legacy_path.read_text(encoding="utf-8").strip()
                    if content:
                        notes.append(f"[{date}]\n{content}")
        if notes:
            parts.append(f"【最近の記憶】\n" + "\n\n".join(notes))

    return "\n\n".join(parts) if parts else ""
```

---

## 3. `memory_processor.py` の新規作成

`/home/tukapontas/gakukoma/brain/memory_processor.py` を新規作成する。

このスクリプトはcronから呼び出され、当日のRAWログを分析してwikiを更新する。

```python
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
```

---

## 4. `voice_loop.py` の修正（退屈行動）

### 4-1. インポートの追加

`voice_loop.py` の先頭インポート部分に追加:

```python
import random
```

### 4-2. `config.yaml` への追加

`config.yaml` の末尾に以下を追加:

```yaml
# アイドル行動設定（Phase 5.1追加）
idle_behavior:
  enabled: true
  interval_sec: 300      # 退屈行動のインターバル（秒）。デフォルト5分
  time_restriction:      # この時間帯は退屈行動をOFF
    start_hour: 22       # 22時以降はOFF
    end_hour: 7          # 7時以前はOFF
```

### 4-3. `VoiceLoop.__init__()` への追加

`__init__` メソッドの末尾（`self.brain = GAKUKOMABrain(config)` の直後）に追加:

```python
self._idle_start = None   # アイドル開始時刻（Noneなら非アイドル）
```

### 4-4. 退屈行動メソッドの追加

クラスのメソッドとして以下を追加:

```python
def _maybe_do_idle_action(self):
    """
    アイドル一定時間経過後、確率的に自発行動を起こす。
    インターバルと時間制限はconfig.yamlの idle_behavior セクションで設定。
    """
    ib = self.config.get("idle_behavior", {})
    if not ib.get("enabled", True):
        return

    hour = datetime.now().hour
    start_h = ib.get("time_restriction", {}).get("start_hour", 22)
    end_h   = ib.get("time_restriction", {}).get("end_hour", 7)
    if hour >= start_h or hour < end_h:
        return  # 時間制限内は何もしない

    if self._idle_start is None:
        self._idle_start = datetime.now()
        return

    interval = ib.get("interval_sec", 300)
    idle_seconds = (datetime.now() - self._idle_start).total_seconds()
    if idle_seconds < interval:
        return

    # インターバル超えたらリセットして何かする（次の行動まで再度待つ）
    self._idle_start = datetime.now()

    roll = random.random()
    if roll < 0.50:
        # 50%: ランダムな方向を見る
        direction = random.choice(["left", "right", "up", "front"])
        subprocess.run(
            ["/home/tukapontas/gakukoma/tools/look_direction.sh", direction],
            capture_output=True
        )
    elif roll < 0.65:
        # 15%: 少し前進してすぐ止まる
        subprocess.run(
            ["/home/tukapontas/gakukoma/tools/move_robot.sh", "forward", "0.4"],
            capture_output=True
        )
        import time
        time.sleep(0.5)
        subprocess.run(
            ["/home/tukapontas/gakukoma/tools/move_robot.sh", "stop", "0"],
            capture_output=True
        )
    elif roll < 0.70:
        # 5%: 呟く（音声出力）
        phrases = [
            "んー、なんか音がしたような気がした",
            "今日は静かだな",
            "ちょっと周りを見てみようかな",
        ]
        text = random.choice(phrases)
        subprocess.run(
            ["/home/tukapontas/gakukoma/tools/speak_text.sh", text],
            capture_output=True
        )
    # 残り30%: 何もしない
```

### 4-4. IDLEループでの呼び出し

`voice_loop.py` のメインループ内、`state == "idle"` の処理部分を探して `_maybe_do_idle_action()` を呼び出す。

現在のIDLEループはwhileループの中に `if self.state == "idle":` のブロックがあるはず。そのブロックの末尾に以下を追加:

```python
self._maybe_do_idle_action()
```

アイドル状態から他の状態に移行したとき（ウェイクワード検出時）にタイマーをリセット:

```python
# brain.new_session() を呼ぶ直前に追加
self._idle_start = None
```

**【重要】タイマーリセットの条件について**

`_idle_start` をリセット（`None` または `datetime.now()`）するのは以下の2箇所**のみ**:
1. ウェイクワード検出 → アクティブ移行時（上記）
2. 退屈行動が実際に発動したとき（次のインターバルを計り直すため）

**物音を拾ってウェイクワードでなかった場合（認識不明・認識誤りを含む）はリセットしない。**
アイドルループの中で `is_wakeword()` が `False` を返してループ先頭に戻っても、`_idle_start` には触れないこと。これにより環境音が多い場所でも時間が正しく積み上がる。

---

## 5. cronの設定

以下のコマンドでcrontabを設定する:

```bash
(crontab -l 2>/dev/null; echo "0 3 * * * python3 /home/tukapontas/gakukoma/brain/memory_processor.py >> /home/tukapontas/gakukoma/memory/processor.log 2>&1") | crontab -
```

設定確認:
```bash
crontab -l
```

---

## 6. テスト項目

### T-1: ディレクトリ構造確認
```bash
ls -la /home/tukapontas/gakukoma/memory/
```
`raw/`・`episodes/`・`wiki/people/`・`wiki/places/` が存在すること。

### T-2: RAWログ保存確認
- ウェイクワードで起動 → 2〜3ターン会話 → 「おやすみ」
- `/home/tukapontas/gakukoma/memory/raw/` に `YYYY-MM-DD_HHMMSS.md` が生成されること
- ファイル内容に「**ユーザー**:」と「**がくこま**:」が両方含まれること

### T-3: memory_processor.py 手動実行
```bash
python3 /home/tukapontas/gakukoma/brain/memory_processor.py
```
- エラーなく完了すること
- `wiki/index.md` が更新されること
- `wiki/core_memories.md` が存在すること（感情スコアが低ければ核記憶なしでも可）

### T-4: wikiコンテキスト注入確認
- T-3実行後、再度会話を開始する
- コンソールログの `Tokens: input=XXXX` が旧方式（直近3日ログ注入）より減っていること、またはindex.mdの内容が応答に反映されていることを確認

### T-5: 退屈行動確認
- `config.yaml` の `idle_behavior.interval_sec` を一時的に `30` に設定してテスト
- 会話せずに35秒ほど待つ
- 首の向きが変わる / 軽い移動が起きる / 稀に呟くのいずれかが発生すること
- **`enabled: false` に設定すると発生しないこと**
- テスト後 `interval_sec` を `300`（5分）に戻すこと

### T-6: 忘却処理確認（8日後に確認 or 手動テスト）
手動テスト:
```bash
# 8日前のダミーファイルを作成
touch -d "2026-04-10" /home/tukapontas/gakukoma/memory/raw/2026-04-10_120000.md
# processor実行
python3 /home/tukapontas/gakukoma/brain/memory_processor.py
# ファイルが削除されていること
ls /home/tukapontas/gakukoma/memory/raw/
```

### T-7: フォールバック確認（wiki空の状態で起動）
- `wiki/index.md` を一時リネームして起動
- 旧ディレクトリのログが代わりに注入されること（または何も注入されず正常起動すること）
- リネームを戻す

### T-8: cron設定確認
```bash
crontab -l | grep memory_processor
```
`0 3 * * *` のエントリが存在すること。

---

## 7. 完了報告時の記載事項

完了報告書（`coding/20260418_phase5_1_memory_wiki_completed.md`）に記載すること:

1. T-1〜T-8の合否
2. RAWログのファイルサイズ（1セッション平均）
3. memory_processor.py の実行時間（手動実行時の秒数）
4. wiki/index.md のサンプル内容（数行）
5. 退屈行動の発動確認状況
6. コンテキストトークン数の変化（旧 vs 新、概算）
7. 気づいた点・懸念事項

---

## 8. 注意事項・申し送り

- **旧メモリディレクトリは削除しない**: `/home/tukapontas/.openclaw/workspace/memory/` は残す。OpenClawが参照している可能性がある。
- **`_load_daily_notes()` のフォールバックロジック**: wikiが空のうちは旧ディレクトリを読む実装にしてある。wikiが育ってきたら旧ディレクトリ参照は自然に不要になる。
- **memory_processor.py の API呼び出し**: Haiku呼び出しを2〜3回（分析 + 人物ページ更新）行う。セッションが多い日は人物が複数出るため最大5〜6回になる可能性がある。コスト試算: ~1,000〜3,000 tokens × Haikuレート。
- **退屈行動の `subprocess` 呼び出し**: voice_loop.pyのIDLEループはwhileで高速スピンしているため、`_maybe_do_idle_action()` の中で時刻チェックと60秒チェックを最初に行い、条件を満たさない場合は即returnすること（CPU負荷を上げない）。
- **move_robot.sh 呼び出し時**: 前進後に必ず stop を呼ぶこと。タイムアウト等でstopが呼ばれない場合に備え、move_robot.shの `duration` 引数を使えばスクリプト側で自動停止する（既存実装確認のこと）。
- **既存の申し送り事項（全て引き継ぐこと）**:
  - `pan_tilt.py` に `__del__` を追加してはならない
  - `release()` / `deinit()` を look_direction 内から呼び出してはならない

---

*作成: ClaudeCode, 2026-04-18*
