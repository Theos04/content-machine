import torch
import silero
import torchaudio

# Load Silero TTS model
print("Loading model...")
model, _, _ = silero.foreign.initialize_tts_model(
    model_name="silero_tts",
    language="en",
    speaker="en_0"
)
print("✅ Model ready")

# Synthesize
text = "Hello from Termux on Android! Text to speech is now working."
audio = model.apply_tts(text=text, speaker="en_0", sample_rate=24000)

# Convert to tensor and save with torchaudio
audio_tensor = torch.from_numpy(audio).float()
torchaudio.save("output.wav", audio_tensor.unsqueeze(0), 24000)

print("✅ Audio saved to output.wav")
print("File size:", os.path.getsize("output.wav"), "bytes")
