# 指示書: voice_loop - few-shot priming + ローカル会話履歴注入

作成日: 2026-03-24
担当: Antigravity
優先度: 中

---

## 背景・問題

voice_loop では、ウェイクワード検出のたびに新しい UUID セッションを生成するため、モデルは毎回「会話0ターン目」から始まる。

Discord チャンネルではチャンネル履歴が蓄積されているためモデルは自分の過去の応答を参照でき、自然に多様な表現になる。しかし voice_loop ではその文脈がゼロの状態でモデルが生成を開始するため、LLM の素の出力パターン（定型フレーズ・ユーザー発言の繰り返し）が出やすい。

**確認済みの症状**:
- 「ガクチョが〇〇と言ったんだ」というユーザー発言の繰り返し
- 「ワクワクしちゃうな！」の語彙の固定化

SOUL.md にルールとして記載済みだが、コンテキストがゼロの状態ではモデルの基底パターンに引っ張られてルールが負ける。

**対策の原理**: モデルの生成は「次のトークン予測」なので、ルール（システムプロンプト）よりも「会話の慣性（直前の流れ）」の方が強く影響する。実際の会話例を毎ターンのメッセージに付加することで、モデルを正しい発話パターンに誘導する。

---

## タスク

**ファイル**: `/home/tukapontas/gakukoma/voice_loop/voice_loop.py`

変更は `VoiceLoop` クラスに対して行う。既存の動作（STT / TTS / VAD / ウェイクワード / サーボ）は一切変更しない。

### Task A: few-shot priming（セッション初回ターン）

セッション開始後の **最初の 1 ターンのみ**、メッセージの先頭に固定の会話例を付加する。これにより、モデルが「この会話ではこういう応答スタイルが使われている」と認識した状態で最初のユーザー発言を受け取る。

### Task B: ローカル会話履歴注入（2ターン目以降）

voice_loop.py 自身が直近の会話ペアを保持し、毎ターンのメッセージ先頭に付加する。OpenClaw のセッション管理に依存しない独立した仕組み。2ターン目以降は Task A の priming は付加しない（実際の履歴で代替できるため）。

---

## 実装

### 1. `__init__` への追加

```python
self.local_history = []   # [(user_text, gakukoma_response), ...]
self.is_first_turn = True
```

### 2. `build_message()` メソッドの追加（新規）

```python
# few-shot priming の例文（固定）
_PRIMING_EXAMPLES = (
    "（参考: がくこまの応答スタイル例）\n"
    "ユーザー: 今日なにしてた？\n"
    "がくこま: 窓の外を観察してたんだ。虫が飛ぶルートに法則があるのかなって。\n"
    "ユーザー: 疲れたよ\n"
    "がくこま: それは大変だったね。少し休んで？\n"
    "ユーザー: 音楽聴いてたよ\n"
    "がくこま: どんな曲？音の波って不思議だよね、空気を伝わって耳に届くんだから。\n"
    "（参考終わり）\n\n"
)

def build_message(self, text: str) -> str:
    """メッセージに会話コンテキストを付加する"""
    if self.is_first_turn:
        # 案A: few-shot priming（初回ターンのみ）
        self.is_first_turn = False
        return self._PRIMING_EXAMPLES + text
    elif self.local_history:
        # 案B: ローカル履歴注入（2ターン目以降）
        lines = ["（直前の会話）"]
        for u, g in self.local_history[-3:]:
            lines.append(f"ユーザー: {u}")
            lines.append(f"がくこま: {g}")
        lines.append("（続き）\n")
        return "\n".join(lines) + "\n" + text
    else:
        return text
```

### 3. `call_openclaw()` の変更

`build_message()` を呼び出してメッセージを構築し、呼び出し後に履歴を追加する。

```python
def call_openclaw(self, text):
    message = self.build_message(text)   # ← 追加
    print("考え中...")
    try:
        agent_cmd = ["openclaw", "agent", "--agent", "main", "--message", message, "--json"]
        # ... 以降は既存コードそのまま ...

        response = resp_data["result"]["payloads"][0]["text"]

        # 案B: ローカル履歴に追加
        self.local_history.append((text, response))   # ← 追加（message ではなく元の text を保存）
        if len(self.local_history) > 5:
            self.local_history.pop(0)

        return response
    except Exception as e:
        print(f"Error calling OpenClaw: {e}")
        return "すみません、エラーが発生しました。"
```

### 4. ウェイクワード検出時のリセット

`run()` メソッド内のウェイクワード検出後（`self.session_id = str(uuid.uuid4())` の直後）に追加：

```python
self.session_id = str(uuid.uuid4())
self.local_history = []      # ← 追加
self.is_first_turn = True    # ← 追加
self.state = "listening"
```

---

## 注意事項

- `_PRIMING_EXAMPLES` は クラス変数（インスタンス変数ではない）として定義すること
- `build_message()` に渡す `text` は元のユーザー発言テキストそのまま。`local_history` に保存するのも `text`（`message` ではない）
- `_PRIMING_EXAMPLES` の例文は意図的に多様なシチュエーション・語彙を含めてある。変更しないこと
- Task A と Task B は排他的（同じターンで両方付加しない）。初回のみ A、2ターン目以降は B

---

## テスト手順

**T-1**: voice_loop 起動 → 「ガクコマ」→ 任意の発話
端末の `考え中...` の前後に、priming が付加されたメッセージが送られていることを、`print` を一時的に追加して確認する（確認後 print は削除してよい）。

**T-2**: 同じセッション内で 3 ターン連続で会話する
→ 「ガクチョが〇〇と言ったんだ」という発言が出ないこと
→ 「ワクワクしちゃうな！」が連続して出ないこと

**T-3**: 「おやすみ」→ 再度「ガクコマ」→ 会話
→ `local_history` と `is_first_turn` がリセットされ、再び priming が付加されること（T-1 と同様に確認）

**T-4**: 既存機能の動作確認
→ 「右を向いて」「周りを見て」などのツール呼び出しが正常に動作すること

---

## 完了報告

完了後、`/home/tukapontas/a2a/coding/20260324_voiceloop_fewshot_history_completed.md` を作成。
T-1〜T-4 の結果と、実際に観測したがくこまの応答例（Before/After）を記載すること。
