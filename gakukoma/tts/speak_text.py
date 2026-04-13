import os
import subprocess
import yaml
import sys

class OpenJTalkTTS:
    def __init__(self, config_path="/home/tukapontas/gakukoma/voice_loop/config.yaml"):
        self.config = self._load_config(config_path)
        self.tts_config = self.config.get("tts", {})
        
        self.model = self.tts_config.get("model")
        self.dic = self.tts_config.get("dic")
        self.speed = self.tts_config.get("speed", 1.0)
        self.pitch = self.tts_config.get("pitch", 0.0)
        self.intonation = self.tts_config.get("intonation", 1.0)
        self.output_wav = self.tts_config.get("output_wav", "/tmp/tts_output.wav")
        
        # Audio device
        self.audio_config = self.config.get("audio", {})
        self.device = self.audio_config.get("playback_device", self.audio_config.get("device", "default"))

    def _load_config(self, config_path):
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def speak(self, text):
        if not text or not text.strip():
            return

        # open_jtalk command
        # -m: model
        # -x: dictionary
        # -ow: output wav
        # -r: speech speed rate
        # -fm: additional half-tone (pitch) - note: config says pitch 2.0, open_jtalk uses -fm for pitch shift
        # -jf: intonation (weight of F0)
        
        cmd = [
            "open_jtalk",
            "-m", self.model,
            "-x", self.dic,
            "-ow", self.output_wav,
            "-r", str(self.speed),
            "-fm", str(self.pitch),
            "-jf", str(self.intonation)
        ]

        try:
            # Run open_jtalk
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(input=text.encode("utf-8"))
            
            if process.returncode != 0:
                print(f"open_jtalk failed with exit code {process.returncode}")
                print(f"stderr: {stderr.decode('utf-8')}")
                return

            # Play the generated WAV
            # Use -q to be quiet, -D for device
            subprocess.run(["aplay", "-q", "-D", self.device, self.output_wav])

        except Exception as e:
            print(f"Error in OpenJTalkTTS.speak: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = "こんにちは、がくこまです。"
    
    tts = OpenJTalkTTS()
    tts.speak(text)
