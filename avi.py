from TTS.api import TTS
import sounddevice as sd
import soundfile as sf

# Load XTTS v2
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

text = "hi robin what are you doing , you need to go to class properly"

output_file = "output.wav"

# Generate speech using a built-in male voice
tts.tts_to_file(
    text=text,
    file_path=output_file,
    language="en",
    speaker_wav="bass_sample.wav"  # 🔥 You MUST provide this!
)

# Play output
data, samplerate = sf.read(output_file)
sd.play(data, samplerate)
sd.wait()

print("✔️ Audio generated and played successfully!")
