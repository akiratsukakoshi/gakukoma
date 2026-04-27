# 完了報告書: sing_song ツール実装

**日付**: 2026-04-24
**担当**: gakukoma-coder（Claudeサブエージェント）

## 実装内容

### Task 1: `gakukoma/tools/sing_song.py` 新規作成 ✅

- 引数1: JSON文字列（音符リスト）、引数2: tempo倍率（省略時=1.0）
- numpy + sounddevice でsin波を生成して再生
- `FADE_SAMPLES = int(44100 * 0.005)` (5ms) のフェードイン/アウトエンベロープでクリックノイズを防止
- 休符（freq=0または省略）は `np.zeros()` で無音再生
- 首振りスレッド: `daemon=True` の `threading.Thread` で並行実行
  - pan値: left=130 / front=90 / right=50 を 0.25秒ステップで繰り返す（1周期=1.0秒）
  - tiltは変更しない
  - 演奏終了後に `stop_event.set()` でスレッド停止 → `look_center()` で正面に戻す
- エラーハンドリング:
  - sounddevice/numpy 未インポート → "sounddeviceまたはnumpyが利用できない" を出力して終了
  - PanTiltController 初期化失敗 → 首振りなしで音だけ再生（エラーにしない）
  - JSONパースエラー → "notes JSONが不正" を出力して終了
- 出力: `演奏完了（N音符, X.X秒）`

### Task 2: `gakukoma/tools/sing_song.sh` 新規作成 ✅

- `chmod +x` 適用済み
- `NOTES="${1:-[]}"` / `TEMPO="${2:-1.0}"` でデフォルト値設定
- `python3 /home/tukapontas/gakukoma/tools/sing_song.py "$NOTES" "$TEMPO"` を呼び出す

### Task 3: `gakukoma/brain/gakukoma_brain.py` 更新 ✅

**3-1. TOOLS リストに sing_song を追加**
- `notes`（required: 音符配列）と `tempo`（optional: 倍率）を定義
- input_schema の items に freq/duration の型定義を記述

**3-2. `_execute_tool` の dispatch に追加 + timeout=120 個別分岐**
- dispatch dict に `sing_song` エントリを追加（sing_song.sh + notes JSON + tempo）
- `if name == "sing_song":` の if分岐で `timeout=120` を個別指定
- 通常ツールの `timeout=30` ブロックとは分離されており、長い曲でもタイムアウトしない

**3-3. SYSTEM_PROMPT に歌の指示を追加**
- 「探索・巡回・見回し」段落の直後に4行追加
- sing_song ツールの使用条件・曲名指定なし時の自作メロディ生成・speak_text の一言添えを記述

**3-4. PRIMING_EXAMPLES に sing_song の例を追加**
- 末尾（`\n\n"` の前）に2組のQ&Aを追加
- ハッピーバースデーの音符例（一部）と「なんか歌って」→自作メロディの例を記述

## 変更ファイル

| ファイル | 操作 |
|---|---|
| `/home/tukapontas/gakukoma/tools/sing_song.py` | 新規作成 |
| `/home/tukapontas/gakukoma/tools/sing_song.sh` | 新規作成（chmod +x済み） |
| `/home/tukapontas/gakukoma/brain/gakukoma_brain.py` | 更新（TOOLS / _execute_tool / SYSTEM_PROMPT / PRIMING_EXAMPLES） |

## テスト準備

| # | テスト内容 | 実装側の対応 |
|---|---|---|
| T-1 | 「ハッピーバースデーうたって」 | LLMが音符を生成してsing_songを呼び出す。首振りスレッドが並行実行 |
| T-2 | 「きらきら星うたって」 | 同上 |
| T-3 | 「なんか歌って」 | PRIMINGとSYSTEM_PROMPTで自作メロディ生成を誘導 |
| T-4 | 「速めで歌って」 | tempo > 1.0 を渡すと duration / tempo で短くなる |
| T-5 | 演奏終了後に首が正面に戻る | stop_event→join後にlook_center()を呼ぶ実装 |
| T-6 | 「悲しい感じの曲うたって」 | SYSTEM_PROMPTで短調メロディ生成を誘導 |

## 特記事項・懸念事項

- **PanTiltController のロック**: `look_center()` は内部で `CrossProcessLock` を使用している。首振りスレッド内では `set_pan()` を直接呼び出す（ロックなし）。これは指示書の「演奏中に別ツールからサーボが呼ばれる状況はない」の前提のもと意図的な設計。ただし `look_center()` 呼び出しタイミング（演奏終了直後）でロック競合が起きた場合は "look_center失敗: 他の操作が実行中です" の文字列が返るが、その後の動作に影響はない。
- **release() は呼ばない**: 指示書通り、PanTiltController の `release()` は呼ばない実装になっている。
- **sounddevice の排他**: 既存の VAD / STT が sounddevice を使っている場合、演奏中に同時使用が発生すると競合する可能性がある。voice_loop側のMIC入力と演奏出力がデバイスとして分離されていれば問題ないが、要確認。
- 両ファイルともに `python3 -c "import ast; ast.parse(...)"` で構文チェック済み。
