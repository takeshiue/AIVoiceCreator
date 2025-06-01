import os
import json
import logging
import time
import base64
import struct
import wave
import io
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

def save_wave_file(filename, pcm_data, channels=1, rate=24000, sample_width=2):
    """Save PCM data as WAV file using the wave library"""
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm_data)

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
            
            # Generate audio using multi-speaker configuration
            logger.info(f"Generating audio with voices: Speaker1={voice1}, Speaker2={voice2}")
            
            # Import types from genai for proper configuration
            from google.genai import types
            
            # Generate audio with multi-speaker configuration
            response = tts_client.models.generate_content(
                model='models/gemini-2.5-flash-preview-tts',
                contents=script,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                            speaker_voice_configs=[
                                types.SpeakerVoiceConfig(
                                    speaker='Speaker1',
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=voice1
                                        )
                                    )
                                ),
                                types.SpeakerVoiceConfig(
                                    speaker='Speaker2',
                                    voice_config=types.VoiceConfig(
                                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                            voice_name=voice2
                                        )
                                    )
                                ),
                            ]
                        )
                    )
                )
            )
            
            logger.info("Multi-speaker TTS generation completed")
            
            # Extract audio data from response
            audio_data = None
            if hasattr(response, 'candidates') and response.candidates:
                logger.info(f"Found {len(response.candidates)} candidates")
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            logger.info(f"Found {len(candidate.content.parts)} parts")
                            for part in candidate.content.parts:
                                if hasattr(part, 'inline_data') and part.inline_data:
                                    mime_type = getattr(part.inline_data, 'mime_type', '')
                                    data_size = len(getattr(part.inline_data, 'data', b''))
                                    logger.info(f"MIME type: {mime_type}, Data size: {data_size}")
                                    if 'audio' in mime_type.lower() and data_size > 0:
                                        audio_data = part.inline_data.data
                                        logger.info(f"Raw audio data size: {len(audio_data)} bytes")
                                        break
                            if audio_data:
                                break
                    if audio_data:
                        break
            else:
                logger.warning("No candidates found in response")
            
            if not audio_data:
                logger.error("No audio data found in response")
                return jsonify({'error': '音声データの生成に失敗しました。'}), 500
            
            # Save as WAV file using the wave library
            save_wave_file(filepath, audio_data, channels=1, rate=24000, sample_width=2)
            logger.info(f"Saved WAV file: {filepath}")
                
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
        {'id': 'zephyr', 'name': 'Zephyr (男性・明るい)'},
        {'id': 'puck', 'name': 'Puck (男性・陽気な)'},
        {'id': 'charon', 'name': 'Charon (男性・解説的な)'},
        {'id': 'kore', 'name': 'Kore (女性・しっかりした)'},
        {'id': 'fenrir', 'name': 'Fenrir (男性・熱のこもった)'},
        {'id': 'leda', 'name': 'Leda (女性・若々しい)'},
        {'id': 'orus', 'name': 'Orus (男性・しっかりした)'},
        {'id': 'aoede', 'name': 'Aoede (女性・快活な)'},
        {'id': 'callirhoe', 'name': 'Callirhoe (女性・のんびりした)'},
        {'id': 'autonoe', 'name': 'Autonoe (女性・明るい)'},
        {'id': 'enceladus', 'name': 'Enceladus (男性・息もれ声の)'},
        {'id': 'iapetus', 'name': 'Iapetus (男性・クリアな)'},
        {'id': 'umbriel', 'name': 'Umbriel (男性・のんびりした)'},
        {'id': 'algieba', 'name': 'Algieba (中性/なし・なめらかな)'},
        {'id': 'despina', 'name': 'Despina (女性・なめらかな)'},
        {'id': 'erinome', 'name': 'Erinome (女性・クリアな)'},
        {'id': 'algenib', 'name': 'Algenib (中性/なし・しゃがれ声の)'},
        {'id': 'rasalgethi', 'name': 'Rasalgethi (中性/なし・解説的な)'},
        {'id': 'laomedeia', 'name': 'Laomedeia (女性・陽気な)'},
        {'id': 'achernar', 'name': 'Achernar (中性/なし・ソフトな)'},
        {'id': 'alnilam', 'name': 'Alnilam (中性/なし・しっかりした)'},
        {'id': 'schedar', 'name': 'Schedar (中性/なし・落ち着いた)'},
        {'id': 'gacrux', 'name': 'Gacrux (中性/なし・成熟した)'},
        {'id': 'pulcherrima', 'name': 'Pulcherrima (女性・張りのある)'},
        {'id': 'achird', 'name': 'Achird (中性/なし・親しみやすい)'},
        {'id': 'zubenelgenubi', 'name': 'Zubenelgenubi (中性/なし・くだけた)'},
        {'id': 'vindemiatrix', 'name': 'Vindemiatrix (女性・穏やかな)'},
        {'id': 'sadachbia', 'name': 'Sadachbia (中性/なし・活気のある)'},
        {'id': 'sadaltager', 'name': 'Sadaltager (中性/なし・知的な)'},
        {'id': 'sulafat', 'name': 'Sulafat (中性/なし・温かい)'}
    ]
    return jsonify({'voices': voices})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
