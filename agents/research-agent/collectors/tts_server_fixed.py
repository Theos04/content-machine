from silero_tts import SileroTTS
from flask import Flask, request, send_file, jsonify
import tempfile
import threading
import os

app = Flask(__name__)

# Initialize TTS globally
print("🔄 Loading Silero TTS model...")
tts = SileroTTS(model_id='v3_en', language='en', speaker='en_0', sample_rate=24000, device='cpu')
print("✅ TTS model ready")

@app.route('/synthesize', methods=['POST'])
def synthesize():
    """Text to speech endpoint"""
    data = request.json
    text = data.get('text', 'Hello')
    
    # Create temp file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    temp_path = temp_file.name
    temp_file.close()
    
    # Generate speech
    tts.tts(text, temp_path)
    
    # Return audio file
    return send_file(temp_path, mimetype='audio/wav')

@app.route('/voices', methods=['GET'])
def voices():
    """List available voices"""
    speakers = tts.get_available_speakers()
    return jsonify({
        "speakers": speakers,
        "current_speaker": tts.speaker,
        "language": tts.language
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running", "model": "silero-tts"})

@app.route('/change_speaker', methods=['POST'])
def change_speaker():
    """Change the voice speaker"""
    data = request.json
    speaker = data.get('speaker', 'en_0')
    tts.change_speaker(speaker)
    return jsonify({"status": "ok", "current_speaker": tts.speaker})

if __name__ == '__main__':
    print("="*50)
    print("📱 TTS Server Running on Termux")
    print("="*50)
    print("Local: http://localhost:5000")
    
    # Get IP address
    import subprocess
    import re
    result = subprocess.run(['ifconfig'], capture_output=True, text=True)
    ips = re.findall(r'inet addr:(\d+\.\d+\.\d+\.\d+)', result.stdout)
    for ip in ips:
        if ip.startswith('192.168') or ip.startswith('10.'):
            print(f"Network: http://{ip}:5000")
    
    print("="*50)
    app.run(host='0.0.0.0', port=5000, debug=False)
