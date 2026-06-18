import torch
from silero import silero_tts
import torchaudio

# Load the TTS model
tts_model, example_text = silero_tts(
    language='en', 
    speaker='v3_en',  # or 'en_0', 'en_1', etc.
    device='cpu'
)

# Generate audio
text = "Hello from Termux using the original Silero package."
audio = tts_model.apply_tts(
    text=text, 
    speaker='en_0', 
    sample_rate=24000
)

# Save audio
audio_tensor = torch.from_numpy(audio).float()
torchaudio.save("output_original.wav", audio_tensor.unsqueeze(0), 24000)

print("✅ Audio saved to output_original.wav")
