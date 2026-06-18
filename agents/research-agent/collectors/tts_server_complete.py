from flask import Flask, request, send_file, jsonify
from silero_tts.silero_tts import SileroTTS
import tempfile
import os
import re
import subprocess

app = Flask(__name__)

# Initialize TTS once at startup
print("🔄 Loading Silero TTS model...")
tts = SileroTTS(
    model_id='v3_en',
    language='en',
    speaker='en_2',  # Female voice. Try en_0 (male), en_1, en_2, en_3, en_4
    sample_rate=48000,
    device='cpu'
)
print("✅ TTS model ready!")

@app.route('/synthesize', methods=['POST'])
def synthesize():
    """Convert text to speech and return audio"""
    data = request.json
    text = data.get('text', '')
    speaker = data.get('speaker', 'en_2')
    
    if not text:
        return jsonify({"error": "No text provided"}), 400
    
    print(f"🎤 Synthesizing: {text[:100]}...")
    
    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    temp_path = temp_file.name
    temp_file.close()
    
    # Generate speech
    tts.change_speaker(speaker)
    tts.tts(text, temp_path)
    
    # Return audio file
    return send_file(
        temp_path,
        mimetype='audio/wav',
        as_attachment=False,
        download_name='speech.wav'
    )

@app.route('/voices', methods=['GET'])
def list_voices():
    """List available voices"""
    voices = {
        "en_0": "Male voice 1",
        "en_1": "Male voice 2", 
        "en_2": "Female voice 1",
        "en_3": "Female voice 2",
        "en_4": "Female voice 3",
        "en_5": "Male voice 3",
        "en_6": "Male voice 4",
        "en_7": "Female voice 4",
        "en_8": "Neural voice 1",
        "en_9": "Neural voice 2"
    }
    return jsonify({
        "speakers": voices,
        "current_speaker": "en_2",
        "sample_rate": 48000
    })

@app.route('/change_voice', methods=['POST'])
def change_voice():
    """Change the default voice"""
    data = request.json
    speaker = data.get('speaker', 'en_2')
    try:
        tts.change_speaker(speaker)
        return jsonify({"status": "success", "current_speaker": speaker})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running", "model": "silero_tts_v3_en"})

@app.route('/test', methods=['GET'])
def test():
    """Generate a test audio"""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    temp_path = temp_file.name
    temp_file.close()
    
    tts.tts("Hello! This is a test of the text to speech server.", temp_path)
    return send_file(temp_path, mimetype='audio/wav')

if __name__ == '__main__':
    print("="*50)
    print("📱 Silero TTS Server Running on Termux")
    print("="*50)
    print("Local access: http://localhost:5000")
    
    # Get network IP
    result = subprocess.run(['ifconfig'], capture_output=True, text=True)
    ips = re.findall(r'inet addr:(\d+\.\d+\.\d+\.\d+)', result.stdout)
    for ip in ips:
        if ip.startswith('192.168') or ip.startswith('10.'):
            print(f"Network access: http://{ip}:5000")
    print("="*50)
    print("Endpoints:")
    print("  POST /synthesize - Send JSON: {'text': 'your text'}")
    print("  GET  /voices     - List available voices")
    print("  GET  /health     - Check server status")
    print("  GET  /test       - Generate test audio")
    print("="*50)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
