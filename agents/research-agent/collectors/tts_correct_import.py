# Correct import path - SileroTTS is in the submodule
from silero_tts.silero_tts import SileroTTS

# Initialize the TTS object
tts = SileroTTS(
    model_id='v3_en', 
    language='en', 
    speaker='en_2', 
    sample_rate=48000, 
    device='cpu'
)

# Synthesize speech
text = "Hello from Termux on Android! Text to speech is now working."
tts.tts(text, 'output.wav')

print("✅ Audio saved to output.wav")
