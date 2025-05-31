import os
import json
import logging
import time
import base64
from flask import Flask, render_template, request, jsonify, send_from_directory
import google.genai as genai
# Remove old import since we're using google.genai now

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Configure Google Gen AI client
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    client = genai.Client(api_key=GOOGLE_API_KEY)
    logger.info("Google AI configured successfully")
else:
    logger.warning("GOOGLE_API_KEY not found in environment variables")
    client = None

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
        
        if not client:
            return jsonify({'error': 'Google API キーが設定されていません。環境変数 GOOGLE_API_KEY を設定してください。'}), 500
        
        # Create effective prompt for interview script generation
        prompt_text = f"""あなたはプロの放送作家です。以下の構成案に基づいて、自然で魅力的なインタビューのトークスクリプトを Speaker1 と Speaker2 の対話形式で作成してください。

重要な指示：
- 必ず「Speaker1:」「Speaker2:」の形式で話者を明記してください
- 自然で親しみやすい日本語の会話にしてください
- 各話者の発言は1-3文程度にまとめてください
- 対話が自然に流れるようにしてください
- 合計で10-15回程度の発言交換を目安にしてください

構成案:
{constitution}

トークスクリプト:"""

        # Generate content using Google Gen AI
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash-preview-05-20',
                contents=prompt_text,
                config={
                    'temperature': 0.7,
                    'top_p': 0.8,
                    'max_output_tokens': 2048
                }
            )
            logger.info(f"Script generation API response: {type(response)}")
        except Exception as api_error:
            logger.error(f"Script generation API error: {str(api_error)}")
            return jsonify({'error': f'スクリプト生成エラー: {str(api_error)}'}), 500
        
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
        logger.info("=== Starting audio generation ===")
        data = request.get_json()
        logger.info(f"Request data: {data}")
        script = data.get('script', '').strip()
        voice1 = data.get('voice1', 'aoede')
        voice2 = data.get('voice2', 'charon')
        rate = float(data.get('rate', 1.0))
        logger.info(f"Script length: {len(script)}, Voice1: {voice1}, Voice2: {voice2}")
        
        if not script:
            return jsonify({'error': 'スクリプトを入力してください。'}), 400
        
        if not GOOGLE_API_KEY:
            return jsonify({'error': 'Google API キーが設定されていません。'}), 500
        
        # Initialize client for this request
        try:
            tts_client = genai.Client(api_key=GOOGLE_API_KEY)
            logger.info("TTS client initialized successfully")
        except Exception as client_error:
            logger.error(f"Failed to initialize TTS client: {str(client_error)}")
            return jsonify({'error': f'TTSクライアントの初期化に失敗しました: {str(client_error)}'}), 500
        
        # Generate unique filename - using WAV format
        timestamp = int(time.time())
        filename = f"interview_{timestamp}.wav"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        try:
            # Generate audio using Google Gen AI TTS
            
            # Multi-speaker audio generation using Google Gen AI TTS
            # Parse script to identify speakers and their lines
            script_parts = []
            lines = script.strip().split('\n')
            
            for line in lines:
                if line.strip() and ':' in line:
                    speaker, text = line.split(':', 1)
                    speaker_name = speaker.strip()
                    speech_text = text.strip()
                    
                    # Assign voice based on speaker
                    if 'Speaker1' in speaker_name or '1' in speaker_name:
                        voice_name = voice1
                    elif 'Speaker2' in speaker_name or '2' in speaker_name:
                        voice_name = voice2
                    else:
                        voice_name = voice1  # Default to voice1
                    
                    script_parts.append({
                        "text": speech_text,
                        "voice": voice_name
                    })
            
            # Split script into smaller chunks for TTS
            lines = script.strip().split('\n')
            audio_chunks = []
            
            for line in lines:
                if line.strip() and ':' in line:
                    speaker, text = line.split(':', 1)
                    text = text.strip()
                    
                    # Skip empty text
                    if not text:
                        continue
                    
                    # Limit text length to prevent timeout
                    if len(text) > 200:
                        text = text[:200] + "..."
                    
                    logger.info(f"Processing line: {speaker}: {text[:50]}...")
                    
                    try:
                        # Generate audio for each line separately
                        response = tts_client.models.generate_content(
                            model='models/gemini-2.5-flash-preview-tts',
                            contents=text,
                            config={
                                "response_modalities": ["AUDIO"]
                            }
                        )
                        
                        # Extract audio data from this chunk
                        if hasattr(response, 'candidates') and response.candidates:
                            for candidate in response.candidates:
                                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                                    for part in candidate.content.parts:
                                        if hasattr(part, 'inline_data') and part.inline_data:
                                            mime_type = getattr(part.inline_data, 'mime_type', '')
                                            if 'audio' in mime_type.lower():
                                                audio_chunks.append(base64.b64decode(part.inline_data.data))
                                                break
                                if audio_chunks:
                                    break
                    except Exception as chunk_error:
                        logger.warning(f"Failed to generate audio for chunk: {str(chunk_error)}")
                        continue
            
            if not audio_chunks:
                logger.error("No audio chunks generated")
                return jsonify({'error': '音声データの生成に失敗しました。'}), 500
            
            # Combine all audio chunks
            audio_data = b''.join(audio_chunks)
            logger.info(f"Generated {len(audio_chunks)} audio chunks, total size: {len(audio_data)} bytes")
            
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
