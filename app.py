import os
import json
import logging
import time
import base64
from flask import Flask, render_template, request, jsonify, send_from_directory
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Configure Google API
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    logger.info("Google AI configured successfully")
else:
    logger.warning("GOOGLE_API_KEY not found in environment variables")

# Ensure audio directory exists
AUDIO_DIR = os.path.join('static', 'audio')
os.makedirs(AUDIO_DIR, exist_ok=True)

@app.route('/')
def index():
    """Main application page"""
    return render_template('index.html')

@app.route('/api/generate_script', methods=['POST'])
def generate_script():
    """Generate interview script using Gemini 2.5 Pro"""
    try:
        data = request.get_json()
        constitution = data.get('constitution', '').strip()
        
        if not constitution:
            return jsonify({'error': '構成案を入力してください。'}), 400
        
        if not GOOGLE_API_KEY:
            return jsonify({'error': 'Google API キーが設定されていません。環境変数 GOOGLE_API_KEY を設定してください。'}), 500
        
        # Initialize Gemini model - using Gemini 2.5 Flash Preview
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        
        # Create effective prompt for interview script generation
        prompt = f"""あなたはプロの放送作家です。以下の構成案に基づいて、自然で魅力的なインタビューのトークスクリプトを Speaker1 と Speaker2 の対話形式で作成してください。

重要な指示：
- 必ず「Speaker1:」「Speaker2:」の形式で話者を明記してください
- 自然で親しみやすい日本語の会話にしてください
- 各話者の発言は1-3文程度にまとめてください
- 対話が自然に流れるようにしてください
- 合計で10-15回程度の発言交換を目安にしてください

構成案:
{constitution}

トークスクリプト:"""

        # Generate content
        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=0.7,
                top_p=0.8,
                top_k=40,
                max_output_tokens=2048
            )
        )
        
        if response.text:
            logger.info("Script generated successfully")
            return jsonify({'script': response.text})
        else:
            logger.error("No text generated from Gemini")
            return jsonify({'error': 'スクリプトの生成に失敗しました。'}), 500
            
    except Exception as e:
        logger.error(f"Error generating script: {str(e)}")
        return jsonify({'error': f'スクリプト生成中にエラーが発生しました: {str(e)}'}), 500

@app.route('/api/generate_audio', methods=['POST'])
def generate_audio():
    """Generate audio using Gemini TTS"""
    try:
        data = request.get_json()
        script = data.get('script', '').strip()
        voice1 = data.get('voice1', 'aoede')
        voice2 = data.get('voice2', 'charon')
        rate = float(data.get('rate', 1.0))
        
        if not script:
            return jsonify({'error': 'スクリプトを入力してください。'}), 400
        
        if not GOOGLE_API_KEY:
            return jsonify({'error': 'Google API キーが設定されていません。'}), 500
        
        # Generate unique filename - using WAV format
        timestamp = int(time.time())
        filename = f"interview_{timestamp}.wav"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        try:
            # Gemini 2.5 Pro Preview TTS for speech generation
            model = genai.GenerativeModel('gemini-2.5-pro-preview-tts')
            
            # Try WAV format audio generation using correct syntax
            response = model.generate_content(
                script,
                generation_config={
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": voice1
                            }
                        }
                    }
                }
            )
            
            # Extract audio data from response
            audio_data = None
            if hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'inline_data') and part.inline_data:
                                mime_type = getattr(part.inline_data, 'mime_type', '')
                                if 'audio' in mime_type.lower():
                                    audio_data = base64.b64decode(part.inline_data.data)
                                    break
                    if audio_data:
                        break
            
            if not audio_data:
                logger.error("No audio data found in response")
                return jsonify({'error': '音声データの生成に失敗しました。Gemini APIの音声生成機能が現在利用できない可能性があります。'}), 500
            
            # Save audio file as WAV
            with open(filepath, 'wb') as f:
                f.write(audio_data)
                
        except Exception as speech_error:
            logger.error(f"Speech generation failed: {str(speech_error)}")
            return jsonify({'error': f'音声生成中にエラーが発生しました: {str(speech_error)}'}), 500
        
        logger.info(f"Audio generated successfully: {filename}")
        return jsonify({
            'audio_file_name': filename,
            'message': '音声生成が完了しました。'
        })
        
    except Exception as e:
        logger.error(f"Error generating audio: {str(e)}")
        return jsonify({'error': f'音声生成中にエラーが発生しました: {str(e)}'}), 500

@app.route('/static/audio/<filename>')
def serve_audio(filename):
    """Serve audio files"""
    try:
        return send_from_directory(AUDIO_DIR, filename)
    except Exception as e:
        logger.error(f"Error serving audio file {filename}: {str(e)}")
        return jsonify({'error': 'ファイルが見つかりません。'}), 404

@app.route('/api/voices')
def get_available_voices():
    """Get available voice models"""
    # Available voices for Gemini TTS
    voices = [
        {'id': 'aoede', 'name': 'Aoede (英語・女性)', 'language': 'en'},
        {'id': 'charon', 'name': 'Charon (英語・男性)', 'language': 'en'},
        {'id': 'fenrir', 'name': 'Fenrir (英語・男性)', 'language': 'en'},
        {'id': 'kore', 'name': 'Kore (英語・女性)', 'language': 'en'}
    ]
    return jsonify({'voices': voices})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
