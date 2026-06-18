from silero_tts import SileroTTS
import torchaudio

# Initialize TTS with English model
tts = SileroTTS(model_id='v3_en', language='en', speaker='en_0', sample_rate=24000, device='cpu')

# Synthesize speech
text = "Hello from Termux on Android! Text to speech is now working."
tts.tts(text, 'output.wav')

print("✅ Audio saved to output.wav")
print("File saved successfully!")
