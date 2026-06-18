import torch
import silero
import numpy as np
import wave
import struct

# Load Silero TTS model
print("Loading Silero TTS model...")
device = torch.device('cpu')
model, example_text, example_audio = silero.foreign.initialize_tts_model(
    model_name="silero_tts",
    language="en",
    speaker="en_0"
)
print("✅ Model loaded")

# Test synthesis
text = "Hello! This is a test of the Silero TTS system on my Android phone."
print(f"🎤 Synthesizing: {text}")
output_path = "test_output.wav"

# Generate speech (returns numpy array)
audio = model.apply_tts(text=text, speaker="en_0", sample_rate=24000)

# Manual WAV saving without soundfile
def save_wav(filename, audio_data, sample_rate):
    """Save numpy array as WAV file"""
    # Convert to int16
    audio_int16 = (audio_data * 32767).astype(np.int16)
    
    with wave.open(filename, 'wb') as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 2 bytes for int16
        wav.setframerate(sample_rate)
        wav.writeframes(audio_int16.tobytes())
    
    print(f"✅ Audio saved to {filename}")

save_wav(output_path, audio, 24000)
print("You can play this file with any media player")
