import os
import sys
import subprocess
import yaml
import re
import time
import wave
import collections
import random
import numpy as np
import signal
from pathlib import Path
import sounddevice as sd
import webrtcvad
from datetime import datetime


# record_vad_from_stream() が「発話が一度も始まらないまま無音タイムアウトした」
# ことを run() 側へ伝えるためのセンチネル。
# 「短すぎる音を無視した(None)」や「録音成功(frames list)」とは区別する。
NO_SPEECH_TIMEOUT = object()

# 状態・トリガーファイル（button_monitor の常設ゲートウェイと共有・WP-D）。
# テスト容易性のため定数化し注入可能に（実機依存を避ける既存流儀に合わせる）。
#   voice_state : 現在状態(idle/listening/thinking/speaking)。ゲートウェイが可視化に使う。
#   wake_trigger: スマホからのウェイク注入（存在=要求。IDLEループが消費削除）。
#   sleep_trigger: スマホからのスリープ注入（存在=要求。ACTIVEループが消費削除）。
RUN_DIR = "/run/gakukoma"
VOICE_STATE_FILE = os.path.join(RUN_DIR, "voice_state")
WAKE_TRIGGER_FILE = os.path.join(RUN_DIR, "wake_trigger")
SLEEP_TRIGGER_FILE = os.path.join(RUN_DIR, "sleep_trigger")
# トリガーの鮮度上限（秒）。これより古い残留トリガーは消費せず捨てる。
# （例: 起動途中で自律モードを止められると未消費の wake_trigger が残り、後日の
#   自律起動時に突然「はい、なんでしょう」と言い出すのを防ぐ。自律モードの
#   起動=Whisper読込の数十秒は跨げる長さにしてある）
TRIGGER_TTL_SEC = 120


def _install_sigterm_handler():
    """SIGTERM を KeyboardInterrupt に変換して正常終了フローを通す"""
    def _handler(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _handler)

# Add parent directory to sys.path to import tts module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append("/home/tukapontas/gakukoma/brain")
from gakukoma_brain import GAKUKOMABrain

from tts.speak_text import OpenJTalkTTS
from faster_whisper import WhisperModel
from led_controller import LedController
from servo.pan_tilt import PanTiltController
from servo.gesture_controller import GestureController

def load_config():
    config_path = "/home/tukapontas/gakukoma/voice_loop/config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def clean_text_for_tts(text: str) -> str:
    """絵文字・Markdownを除去してopen_jtalk失敗を防ぐ"""
    # 絵文字除去
    text = re.sub(r'[\U00010000-\U0010FFFF\U0001F000-\U0001FFFF]', '', text)
    # Markdownの強調（**text**）を地のテキストに変換
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # 残った記号（#、`、~等）を除去
    text = re.sub(r'[#`~>|]', '', text)
    return text.strip()

def speak(text, tts_engine):
    if not text:
        return
    text = clean_text_for_tts(text)
    if not text:
        return
    # Split by Japanese punctuation
    sentences = re.split(r'([。！？])', text)
    # Re-combine sentences with their punctuation
    combined = []
    for i in range(0, len(sentences)-1, 2):
        combined.append(sentences[i] + sentences[i+1])
    if len(sentences) % 2 == 1 and sentences[-1]:
        combined.append(sentences[-1])
    
    for s in combined:
        if s.strip():
            print(f"GAKUKOMA: {s.strip()}")
            tts_engine.speak(s.strip())

class VoiceLoop:
    def __init__(self, config):
        self.config = config
        self.tts_engine = OpenJTalkTTS()
        
        # Load STT Models
        print("STTモデル(small)をロード中...")
        self.stt_model = WhisperModel("small", device="cpu", compute_type="int8")
        
        if self.config["wakeword"]["enabled"]:
            print("Wakewordモデル(tiny)をロード中...")
            self.wakeword_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        else:
            self.wakeword_model = None

        self.vad = webrtcvad.Vad(self.config["vad"]["aggressiveness"])
        self.sample_rate = self.config["audio"]["sample_rate"]
        self.frame_duration_ms = 30
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        
        self.state = "idle" # "idle" | "listening" | "thinking" | "speaking"
        self.led = LedController()
        self._set_state("idle")   # LED + 状態ファイル(起動時idle)をまとめて初期化
        self.brain = GAKUKOMABrain(config)
        self.audio_file = self.config["temp"]["audio_file"]
        self._idle_start = None   # アイドル開始時刻（Noneなら非アイドル）

        # ジェスチャーコントローラー初期化
        try:
            self._pan_tilt = PanTiltController()
            self._gesture = GestureController(self._pan_tilt)
        except Exception as e:
            print(f"Warning: ジェスチャーコントローラー初期化失敗 ({e}). ジェスチャー機能は無効。")
            self._pan_tilt = None
            self._gesture = None
        # sounddeviceはALSA文字列("hw:3,0")を受け付けないため、
        # sounddevice_deviceに数値インデックスを優先使用する
        # arecordフォールバックはrecord_device(ALSA文字列)を引き続き使用
        self.device = self.config["audio"].get("sounddevice_device",
                                                self.config["audio"]["record_device"])

    def _write_voice_state(self, state):
        """状態ファイルをアトミック(tmp書き→rename)に書き換える。失敗は無視。

        RUN_DIR が無い/権限が無い環境（開発機・テスト）でも例外で落とさない。
        """
        try:
            tmp = VOICE_STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(state)
            os.replace(tmp, VOICE_STATE_FILE)
        except OSError:
            pass

    def _set_state(self, state):
        """状態遷移の単一チョークポイント: self.state・LED・状態ファイルを一括更新する。

        従来の `self.state = X; self.led.set_state(X)` の全呼出点をこれに集約し、
        遷移のたびに voice_state ファイル（ゲートウェイの可視化用）を同期する。
        """
        self.state = state
        self.led.set_state(state)
        self._write_voice_state(state)

    def _consume_trigger(self, path):
        """トリガーファイルがあれば削除して True（=要求を消費）。無ければ False。

        鮮度が TRIGGER_TTL_SEC を超えた残留トリガーは、削除だけして False（=消費しない）。
        """
        try:
            age = time.time() - os.path.getmtime(path)
        except OSError:
            return False
        try:
            os.remove(path)
        except OSError:
            return False
        return age <= TRIGGER_TTL_SEC

    def _enter_active_from_wake(self):
        """ウェイク（ワード検知 / スマホ注入）共通の遷移: 返事 + new_session + listening。"""
        self._idle_start = None
        speak("はい、なんでしょう", self.tts_engine)
        self.brain.new_session()
        self._set_state("listening")
        self._consecutive_failures = 0

    def _collapse_to_idle(self, farewell):
        """会話終了共通の畳み方: end_session + 別れの一言 + idle + 首を正面へ。

        無音タイムアウト・スリープワード・スマホからのスリープ注入で共用する。
        """
        self.brain.end_session()
        speak(farewell, self.tts_engine)
        self._set_state("idle")
        if self._gesture:
            self._gesture.go_center()

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
            # 50%: ランダムな方向を見て感想を呟く
            try:
                direction = random.choice(["left", "right", "up", "front"])
                subprocess.run(
                    ["/home/tukapontas/gakukoma/tools/look_direction.sh", direction],
                    capture_output=True
                )
                result = subprocess.run(
                    ["python3", "/home/tukapontas/gakukoma/camera/see_around.py"],
                    capture_output=True, text=True, timeout=30
                )
                scene_text = result.stdout.strip()
                if not scene_text:
                    return
                resp = self.brain.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=80,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"ロボット「がくこま」が{direction}方向を見て、こんな景色を見た：\n{scene_text[:300]}\n\n"
                            "がくこまとして、見た感想を1文で呟いてください。"
                            "タチコマのように子供っぽい好奇心で。Markdownなし・絵文字なし。"
                        )
                    }]
                )
                comment = resp.content[0].text.strip()
                speak(comment, self.tts_engine)
            except Exception as e:
                print(f"idle action error: {e}")
                return

        elif roll < 0.60:
            # 10%: 少し前進してすぐ止まる
            try:
                subprocess.run(
                    ["/home/tukapontas/gakukoma/tools/move_robot.sh", "forward", "0.4"],
                    capture_output=True
                )
                time.sleep(0.5)
                subprocess.run(
                    ["/home/tukapontas/gakukoma/tools/move_robot.sh", "stop", "0"],
                    capture_output=True
                )
            except Exception as e:
                print(f"idle action error: {e}")
                return

        elif roll < 0.75:
            # 15%: dreams.md の最新エントリを呟く
            try:
                dreams_path = Path("/home/tukapontas/gakukoma/memory/wiki/dreams.md")
                if not dreams_path.exists():
                    return
                content = dreams_path.read_text(encoding="utf-8")
                sections = []
                current = []
                for line in content.split("\n"):
                    if line.startswith("## ") and len(line) == 13:
                        if current:
                            sections.append("\n".join(current))
                        current = [line]
                    elif current and not line.startswith("<!--"):
                        current.append(line)
                if current:
                    sections.append("\n".join(current))
                if not sections:
                    return
                latest = sections[-1].strip()
                lines = [l for l in latest.split("\n") if l and not l.startswith("##")]
                dream_text = " ".join(lines).strip()
                if not dream_text:
                    return
                speak(f"昨日ふと思ったんだけど。{dream_text}", self.tts_engine)
            except Exception as e:
                print(f"idle action error: {e}")
                return

        elif roll < 0.90:
            # 15%: 直近の記憶をもとに呟く
            try:
                wiki_dir = Path("/home/tukapontas/gakukoma/memory/wiki")
                memory_text = ""
                index_path = wiki_dir / "index.md"
                core_path = wiki_dir / "core_memories.md"
                if index_path.exists():
                    memory_text = index_path.read_text(encoding="utf-8")[:600]
                elif core_path.exists():
                    memory_text = core_path.read_text(encoding="utf-8")[:600]
                if not memory_text.strip():
                    return
                resp = self.brain.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=80,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"ロボット「がくこま」の最近の記憶：\n{memory_text}\n\n"
                            "がくこまとして、この記憶をもとに独り言を1文で呟いてください。"
                            "「〇〇のこと、なんか気になるな」「〇〇って面白いよね」のような子供っぽい感想。"
                            "Markdownなし・絵文字なし。"
                        )
                    }]
                )
                mutter = resp.content[0].text.strip()
                speak(mutter, self.tts_engine)
            except Exception as e:
                print(f"idle action error: {e}")
                return

        # 残り10%: 何もしない

    def is_wakeword(self, text: str) -> bool:
        return "おはよう" in text or "お早う" in text

    def is_sleepword(self, text: str) -> bool:
        return "おやすみ" in text or "お休み" in text

    def save_wav(self, frames, filename):
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(frames))

    def record_wakeword_candidate(self, timeout_sec=None):
        """音量閾値を超えたら2秒間録音してフレーム列を返す。

        timeout_sec 秒(config wakeword.monitor_timeout_sec, デフォルト5)以内に
        音量トリガーが来なければ None を返す。これにより静かな部屋でも
        run() が退屈行動の判定に入れる（トリガー後の録音ロジック・戻り値は従来互換）。
        """
        duration = self.config["wakeword"]["chunk_duration"]
        threshold = self.config["wakeword"]["volume_threshold"]
        if timeout_sec is None:
            timeout_sec = self.config["wakeword"].get("monitor_timeout_sec", 5)
        max_monitor_frames = int(timeout_sec * 1000 / self.frame_duration_ms)

        # モニタリング
        with sd.InputStream(device=self.device, channels=1, samplerate=self.sample_rate, dtype='int16') as stream:
            # ストリーム初期化ノイズを捨てる（最初の15フレーム≈450ms）
            for _ in range(15):
                stream.read(self.frame_size)
            triggered = False
            for _ in range(max_monitor_frames):
                data, _ = stream.read(self.frame_size)
                # 音量の実効値を簡易計算
                data_zero_mean = data.astype(np.float32) - np.mean(data)
                volume = np.mean(np.abs(data_zero_mean))
                if volume > threshold:
                    print(f"Triggered (vol: {volume})")
                    triggered = True
                    break
            if not triggered:
                # タイムアウト（無音のまま）: 退屈行動の機会を run() に返す
                return None

            # 閾値を超えたら指定秒数録音
            print(f"Recording wakeword candidate for {duration}s...")
            frames = [data.tobytes()]
            for _ in range(int(duration * 1000 / self.frame_duration_ms) - 1):
                data, _ = stream.read(self.frame_size)
                frames.append(data.tobytes())

            return frames

    def flush_stream(self, stream, duration_sec):
        """ストリームのバッファをduration_sec秒分読み捨てる"""
        frames_to_discard = int(duration_sec * 1000 / self.frame_duration_ms)
        for _ in range(frames_to_discard):
            stream.read(self.frame_size)

    def record_vad_from_stream(self, stream):
        """開いているストリームからVADで発話を録音する。

        発話が一度も始まらないまま no_speech_timeout_sec
        (config vad.no_speech_timeout_sec, デフォルト90秒) 経過したら
        センチネル NO_SPEECH_TIMEOUT を返す（ユーザーが立ち去った判定用）。
        発話が始まった後の無音打ち切り(silence_threshold)は従来どおり。
        """
        silence_threshold = self.config["vad"]["silence_threshold"]
        min_speech_duration = self.config["vad"]["min_speech_duration"]
        no_speech_timeout = self.config["vad"].get("no_speech_timeout_sec", 90)

        silence_frames_max = int(silence_threshold * 1000 / self.frame_duration_ms)
        min_speech_frames = int(min_speech_duration * 1000 / self.frame_duration_ms)
        no_speech_frames_max = int(no_speech_timeout * 1000 / self.frame_duration_ms)

        frames = []
        ring_buffer = collections.deque(maxlen=int(500 / self.frame_duration_ms)) # 500ms pre-roll

        triggered = False
        silence_count = 0
        speech_count = 0
        no_speech_count = 0  # 発話開始前に経過したフレーム数（無音タイムアウト用）

        while True:
            data, _ = stream.read(self.frame_size)
            is_speech = self.vad.is_speech(data.tobytes(), self.sample_rate)

            if not triggered:
                ring_buffer.append(data.tobytes())
                if is_speech:
                    speech_count += 1
                    if speech_count >= 2: # 2 consecutive frames
                        print("Recording started")
                        triggered = True
                        frames.extend(list(ring_buffer))
                        ring_buffer.clear()
                else:
                    speech_count = 0
                if not triggered:
                    no_speech_count += 1
                    if no_speech_count > no_speech_frames_max:
                        print("Recording aborted (no speech timeout)")
                        return NO_SPEECH_TIMEOUT
            else:
                frames.append(data.tobytes())
                if is_speech:
                    silence_count = 0
                    speech_count += 1
                else:
                    silence_count += 1
                    if silence_count > silence_frames_max:
                        print("Recording stopped (silence)")
                        break
            
        # 録音時間が短すぎる場合は無視
        if len(frames) < min_speech_frames:
            print("Ignoring short sound")
            return None
            
        return frames

    def transcribe(self, filename, model_type="small"):
        model = self.stt_model if model_type == "small" else self.wakeword_model
        # wakewordモードは initial_prompt なし（ガクコマを含めるとハルシネーション誤検知のリスク）
        # activeモードは語彙ヒント付き
        prompt = None if model_type == "tiny" else \
            "がくこま、ガクコマ、学コマ、ロボット、カメラ、右、左、上、下、正面、向いて、見て、ありがとう、おやすみ"
        segments, _ = model.transcribe(
            filename,
            beam_size=5,
            language="ja",
            initial_prompt=prompt,
            condition_on_previous_text=False,
        )
        result = []
        for seg in segments:
            # ハルシネーション除去: 無音/ノイズ判定スコアが高いセグメントを除外
            if seg.no_speech_prob > 0.8:
                continue
            # ハルシネーション除去: 認識信頼度が低いセグメントを除外
            if seg.avg_logprob < -2.0:
                continue
            result.append(seg.text)
        return "".join(result).strip()

    def call_brain(self, text: str) -> str:
        print("考え中...")
        try:
            return self.brain.invoke(text)
        except Exception as e:
            print(f"Error calling brain: {e}")
            return "すみません、エラーが発生しました。"

    def run(self):
        speak("がくこまが起動しました。", self.tts_engine)
        
        # 従来のEnterキー方式
        if not self.config["wakeword"]["enabled"] and not self.config["vad"]["enabled"]:
            self.run_manual()
            return

        try:
            while True:
                if self.state == "idle":
                    print("\n[IDLE] ウェイクワード待機中...")
                    frames = self.record_wakeword_candidate()
                    # スマホからのウェイク注入を確認（record から戻るたび）。
                    # ウェイクワード検知と同一遷移。gakukoma 起動直後の残留も IDLE 到達時に発火。
                    if self._consume_trigger(WAKE_TRIGGER_FILE):
                        self._enter_active_from_wake()
                        continue
                    if frames:
                        self.save_wav(frames, self.audio_file)
                        text = self.transcribe(self.audio_file, model_type="tiny")
                        print(f"WAKEVOICE: {text}")
                        if self.is_wakeword(text):
                            self._enter_active_from_wake()
                        else:
                            self._maybe_do_idle_action()
                    else:
                        # 音量トリガーがないままモニタリングがタイムアウト
                        # → 静かな部屋でも退屈行動の判定に入る
                        self._maybe_do_idle_action()
                
                elif self.state in ("listening", "thinking", "speaking"):
                    # ACTIVEモード: listenサイクルごとにストリームを開き直す
                    # （思考・発話中の長時間バッファ未読によるALSA XRUN/ハングを防止）
                    while self.state != "idle":
                        # 各周回頭でスマホからのモード注入を確認する。
                        # 残留ウェイクは消費して無視。スリープ注入は無音タイムアウトと
                        # 同一の畳み方で idle へ（反映は次のリッスンサイクル=最大で
                        # 無音タイムアウト分遅れる。仕様として許容）。
                        self._consume_trigger(WAKE_TRIGGER_FILE)
                        if self._consume_trigger(SLEEP_TRIGGER_FILE):
                            print("スリープ注入 → IDLEに戻ります")
                            self._collapse_to_idle("じゃあまたね")
                            continue

                        print("\n[LISTENING] 発話待機中...")
                        self._set_state("listening")
                        with sd.InputStream(device=self.device, channels=1,
                                            samplerate=self.sample_rate, dtype='int16') as active_stream:
                            frames = self.record_vad_from_stream(active_stream)
                        # ストリームはここで閉じる。以降の思考・発話中はバッファを持たない。

                        if frames is NO_SPEECH_TIMEOUT:
                            # ユーザーが立ち去った等で発話がないまま無音タイムアウト。
                            # sleepword と同等にセッションを畳んで idle へ戻す。
                            print("無音タイムアウト → IDLEに戻ります")
                            self._collapse_to_idle("じゃあまたね")
                            continue

                        if not frames:
                            continue

                        self.save_wav(frames, self.audio_file)
                        self._set_state("thinking")
                        if self._gesture:
                            self._gesture.start_thinking()
                        print("[THINKING] 認識中...")
                        text = self.transcribe(self.audio_file, model_type="small")

                        if not text:
                            print("（認識不能な音声）")
                            # listening に戻るときは必ずジェスチャーを停止する
                            if self._gesture:
                                self._gesture.stop()
                            self._consecutive_failures = getattr(self, '_consecutive_failures', 0) + 1
                            if self._consecutive_failures >= 3:
                                print("連続認識失敗3回 → IDLEに戻ります")
                                self._consecutive_failures = 0
                                self._set_state("idle")
                            else:
                                self._set_state("listening")
                            continue

                        self._consecutive_failures = 0
                        print(f"YOU: {text}")

                        if self.is_sleepword(text):
                            self._collapse_to_idle("おやすみなさい")
                            continue

                        response = self.call_brain(text)
                        self._set_state("speaking")
                        # スピーキングジェスチャー開始（speak() は同期なのでバックグラウンドで実行）
                        if self._gesture:
                            self._gesture.start_speaking()
                        speak(response, self.tts_engine)
                        # 発話終了後: ジェスチャー停止 → 正面に戻る
                        if self._gesture:
                            self._gesture.go_center()
                        # flush_stream不要: 次ループ先頭でストリームを新規オープンするため
                        self._set_state("listening")

        except KeyboardInterrupt:
            print("\nシャットダウン中...")
            self.brain.end_session()
            speak("がくこまをシャットダウンします。", self.tts_engine)
            self.led.close()
            sys.exit(0)

    def run_manual(self):
        """従来のEnterキー方式"""
        print("\n[MANUAL] Enterキーで録音開始...")
        try:
            while True:
                input("\nEnterキーで録音開始...")
                print("録音中... Enterで終了")
                
                audio_file = self.config["temp"]["audio_file"]
                record_device = self.config["audio"]["record_device"]
                record_cmd = [
                    "arecord", "-D", record_device,
                    "-f", self.config["audio"]["format"],
                    "-r", str(self.config["audio"]["sample_rate"]),
                    "-c", str(self.config["audio"]["channels"]),
                    audio_file
                ]
                
                p = subprocess.Popen(record_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                input()
                p.terminate()
                p.wait()
                
                print("認識中...")
                stt_result = self.transcribe(audio_file)
                
                if not stt_result:
                    print("認識できませんでした。")
                    continue
                    
                print(f"YOU: {stt_result}")
                response = self.call_brain(stt_result)
                speak(response, self.tts_engine)
                
        except KeyboardInterrupt:
            print("\nシャットダウン中...")
            self.brain.end_session()
            speak("がくこまをシャットダウンします。", self.tts_engine)
            if hasattr(self, 'led'): # Just in case it wasn't initialized
                self.led.close()
            sys.exit(0)

def main():
    _install_sigterm_handler()   # SIGTERM を KeyboardInterrupt に変換
    config = load_config()
    loop = VoiceLoop(config)
    loop.run()

if __name__ == "__main__":
    main()
