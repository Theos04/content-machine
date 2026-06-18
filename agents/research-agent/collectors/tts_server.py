import torch
import silero
import numpy as np
import wave
import tempfile
import os
from flask import Flask, request, send_file, jsonify
import io

app = Flask(__name__)

# Initialize model
print("🔄 Loading Silero TTS model...")
model, _, _ = silero.foreign.initialize_tts_model(
    model_name="silero_tts",
    language="en",
    speaker="en_0"
)
print("✅ TTS model ready")

def save_wav_to_bytes(audio_data, sample_rate=24000):
    """Convert audio numpy array to WAV bytes"""
    audio_int16 = (audio_data * 32767).astype(np.int16)
    
    with io.BytesIO() as wav_io:
        with wave.open(wav_io, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(audio_int16.tobytes())
        return wav_io.getvalue()

@app.route('/synthesize', methods=['POST'])
def synthesize():
    """Text to speech endpoint"""
    data = request.json
    text = data.get('text', 'Hello')
    voice = data.get('voice', 'en_0')
    sample_rate = data.get('sample_rate', 24000)
    
    print(f"🎤 Synthesizing: {text[:50]}...")
    
    # Generate speech
    audio = model.apply_tts(text=text, speaker=voice, sample_rate=sample_rate)
    
    # Convert to WAV
    wav_bytes = save_wav_to_bytes(audio, sample_rate)
    
    # Return audio file
    return send_file(
        io.BytesIO(wav_bytes),
        mimetype='audio/wav',
        as_attachment=False,
        download_name='speech.wav'
    )

@app.route('/voices', methods=['GET'])
def list_voices():
    """List available voices"""
    return jsonify({
        "voices": ["en_0", "en_1", "en_2", "en_3"],
        "languages": ["en", "ru", "es", "de", "fr"],
        "current": "en_0"
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "model": "silero_tts"})

@app.route('/test', methods=['GET'])
def test():
    """Generate a test audio"""
    audio = model.apply_tts(text="Test message", speaker="en_0", sample_rate=24000)
    wav_bytes = save_wav_to_bytes(audio, 24000)
    return send_file(io.BytesIO(wav_bytes), mimetype='audio/wav')

if __name__ == '__main__':
    # Get IP address
    import subprocess
    try:
        result = subprocess.run(['ifconfig'], capture_output=True, text=True)
        print("\n" + "="*50)
        print("📱 TTS Server Running on Termux")
        print("="*50)
        print("Local access: http://localhost:5000")
        
        # Try to find IP
        import re
        ips = re.findall(r'inet addr:(\d+\.\d+\.\d+\.\d+)', result.stdout)
        if ips:
            for ip in ips:
                if ip.startswith('192.168') or ip.startswith('10.'):
                    print(f"Network access: http://{ip}:5000")
        print("="*50 + "\n")
    except:
        print("Server running on port 5000")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
