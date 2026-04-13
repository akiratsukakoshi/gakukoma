import sys
import warnings
# Suppress FutureWarnings from huggingface_hub
warnings.filterwarnings("ignore", category=FutureWarning)

from faster_whisper import WhisperModel

def listen_voice(audio_file):
    model_size = "small"
    # Run on CPU with INT8
    model = WhisperModel(model_size, device="cpu", compute_type="int8", local_files_only=True)

    # segments is a generator so the transcription only starts when you iterate over it
    # and each segment is yielded as soon as its transcription is finished.
    segments, info = model.transcribe(audio_file, beam_size=5, language="ja",
                                      initial_prompt="がくこま、ガクコマ、学コマ")

    transcript = ""
    for segment in segments:
        transcript += segment.text

    # Output transcription without newline
    print(transcript, end="")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 listen_voice.py <wav_file_path>")
        sys.exit(1)
    
    audio_file_path = sys.argv[1]
    listen_voice(audio_file_path)
