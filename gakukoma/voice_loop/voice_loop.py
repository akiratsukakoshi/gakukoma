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
import sounddevice as sd
import webrtcvad
from datetime import datetime

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
        self.led.set_state("idle")
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

    def record_wakeword_candidate(self):
        """音量閾値を超えたら2秒間録音する"""
        duration = self.config["wakeword"]["chunk_duration"]
        threshold = self.config["wakeword"]["volume_threshold"]
        
        # モニタリング
        with sd.InputStream(device=self.device, channels=1, samplerate=self.sample_rate, dtype='int16') as stream:
            # ストリーム初期化ノイズを捨てる（最初の15フレーム≈450ms）
            for _ in range(15):
                stream.read(self.frame_size)
            while True:
                data, _ = stream.read(self.frame_size)
                # 音量の実効値を簡易計算
                data_zero_mean = data.astype(np.float32) - np.mean(data)
                volume = np.mean(np.abs(data_zero_mean))
                if volume > threshold:
                    print(f"Triggered (vol: {volume})")
                    break
            
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
        """開いているストリームからVADで発話を録音する"""
        silence_threshold = self.config["vad"]["silence_threshold"]
        min_speech_duration = self.config["vad"]["min_speech_duration"]
        
        silence_frames_max = int(silence_threshold * 1000 / self.frame_duration_ms)
        min_speech_frames = int(min_speech_duration * 1000 / self.frame_duration_ms)
        
        frames = []
        ring_buffer = collections.deque(maxlen=int(500 / self.frame_duration_ms)) # 500ms pre-roll
        
        triggered = False
        silence_count = 0
        speech_count = 0
        
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
                    if frames:
                        self.save_wav(frames, self.audio_file)
                        text = self.transcribe(self.audio_file, model_type="tiny")
                        print(f"WAKEVOICE: {text}")
                        if self.is_wakeword(text):
                            self._idle_start = None
                            speak("はい、なんでしょう", self.tts_engine)
                            self.brain.new_session()
                            self.state = "listening"
                            self.led.set_state("listening")
                            self._consecutive_failures = 0
                        else:
                            self._maybe_do_idle_action()
                
                elif self.state in ("listening", "thinking", "speaking"):
                    # ACTIVEモード: listenサイクルごとにストリームを開き直す
                    # （思考・発話中の長時間バッファ未読によるALSA XRUN/ハングを防止）
                    while self.state != "idle":
                        print("\n[LISTENING] 発話待機中...")
                        self.state = "listening"
                        self.led.set_state("listening")
                        with sd.InputStream(device=self.device, channels=1,
                                            samplerate=self.sample_rate, dtype='int16') as active_stream:
                            frames = self.record_vad_from_stream(active_stream)
                        # ストリームはここで閉じる。以降の思考・発話中はバッファを持たない。

                        if not frames:
                            continue

                        self.save_wav(frames, self.audio_file)
                        self.state = "thinking"
                        self.led.set_state("thinking")
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
                                self.state = "idle"
                                self.led.set_state("idle")
                            else:
                                self.state = "listening"
                                self.led.set_state("listening")
                            continue

                        self._consecutive_failures = 0
                        print(f"YOU: {text}")

                        if self.is_sleepword(text):
                            self.brain.end_session()
                            speak("おやすみなさい", self.tts_engine)
                            self.state = "idle"
                            self.led.set_state("idle")
                            # 首をニュートラルポジション（正面）へ戻す
                            if self._gesture:
                                self._gesture.go_center()
                            continue

                        response = self.call_brain(text)
                        self.state = "speaking"
                        self.led.set_state("speaking")
                        # スピーキングジェスチャー開始（speak() は同期なのでバックグラウンドで実行）
                        if self._gesture:
                            self._gesture.start_speaking()
                        speak(response, self.tts_engine)
                        # 発話終了後: ジェスチャー停止 → 正面に戻る
                        if self._gesture:
                            self._gesture.go_center()
                        # flush_stream不要: 次ループ先頭でストリームを新規オープンするため
                        self.state = "listening"
                        self.led.set_state("listening")

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
    config = load_config()
    loop = VoiceLoop(config)
    loop.run()

if __name__ == "__main__":
    main()
