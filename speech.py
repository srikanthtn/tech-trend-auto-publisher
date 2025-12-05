from elevenlabs import ElevenLabs, save
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
# Load API Key

client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

OUTPUT_DIR = "voices"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_voice(text, voice="Adam", filename_prefix="tech_voice"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.mp3"
    filepath = os.path.join(OUTPUT_DIR, filename)

    # Generate the audio
    audio = client.text_to_speech.convert(
        voice_id=voice,
        model_id="eleven_multilingual_v2",
        text=text
    )

    # Save the audio file
    save(audio, filepath)

    print(f"🎤 Voice generated → {filepath}")
    return filepath


if __name__ == "__main__":
    sample_text = """
European users can soon connect with people on other messaging apps through WhatsApp, sharing messages and files with those who choose to enable this feature.
"""
    generate_voice(sample_text)
