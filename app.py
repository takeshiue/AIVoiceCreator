import os
import logging
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
import google.genai as genai
from google.genai import types
from google.genai.types import HttpOptions
import wave
from dotenv import load_dotenv

load_dotenv()

# --- 設定項目 (ご指定のプレビュー版モデルに設定) ---
MODEL_TEXT_GENERATION = 'models/gemini-2.5-flash-preview-05-20'
MODEL_TTS = 'models/gemini-2.5-flash-preview-tts'
AUDIO_DIR = os.path.join('static', 'audio')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Configure Google Gen AI client
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    try:
        # タイムアウトをミリ秒で指定
        http_opts = HttpOptions(timeout=600000) # 10分
        
        client = genai.Client(api_key=GOOGLE_API_KEY, http_options=http_opts)
        
        logger.info("Google AI configured successfully with a 600,000-millisecond (10 minute) timeout.")
    except Exception as e:
        logger.error(f"Failed to initialize Google AI client: {str(e)}")
        client = None
        GOOGLE_API_KEY = None
else:
    logger.warning("GOOGLE_API_KEY not found in environment variables")
    client = None
    GOOGLE_API_KEY = None


# Ensure audio directory exists
os.makedirs(AUDIO_DIR, exist_ok=True)

@app.route('/')
def index():
    """Main application page"""
    return render_template('index.html')

@app.route('/api/generate_script', methods=['POST'])
def generate_script():
    """Generate interview script using Gemini"""
    try:
        if client is None:
            return jsonify({'error': 'Google API キーが設定されていないか、クライアントの初期化に失敗しました。'}), 500

        data = request.get_json()
        constitution = data.get('constitution', '').strip()

        if not constitution:
            return jsonify({'error': '構成案を入力してください。'}), 400

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

        try:
            response = client.models.generate_content(
                model=MODEL_TEXT_GENERATION,
                contents=prompt_text,
                config={
                    'temperature': 0.7,
                    'top_p': 0.8,
                    'max_output_tokens': 2048
                }
            )
            generated_text = response.text
            logger.info("Script generated successfully with preview TEXT model")
            return jsonify({'script': generated_text})

        except Exception as api_error:
            logger.error(f"Script generation API error: {api_error!r}")
            return jsonify({'error': f'スクリプト生成エラー: {str(api_error)}'}), 500

    except Exception as e:
        logger.error(f"Error in generate_script: {str(e)}")
        return jsonify({'error': f'スクリプト生成中に予期せぬエラーが発生しました: {str(e)}'}), 500


@app.route('/api/generate_audio', methods=['POST'])
def generate_audio():
    """
    Generate multi-speaker audio using 'gemini-2.5-flash-preview-tts'
    with a correctly configured client-level timeout.
    """
    try:
        logger.info("=== Starting audio generation with PREVIEW TTS model (Multi-speaker config) ===")
        if client is None:
            return jsonify({'error': 'Google API キーが設定されていないか、クライアントの初期化に失敗しました。'}), 500

        data = request.get_json()
        script = data.get('script', '').strip()
        voice1_name = data.get('voice1', 'kore')
        voice2_name = data.get('voice2', 'charon')

        if not script:
            return jsonify({'error': 'スクリプトを入力してください。'}), 400

        timestamp = int(time.time())
        filename = f"interview_{timestamp}.wav"
        filepath = os.path.join(AUDIO_DIR, filename)

        try:
            # --- 1. Parse script and build prompt with speaker tags ---
            script_lines = script.strip().split('\n')
            prompt_parts = []
            for line in script_lines:
                line = line.strip()
                if line.startswith('Speaker1:'):
                    text = line.replace('Speaker1:', '', 1).strip()
                    prompt_parts.append(f"<speaker:Speaker1>{text}</speaker:Speaker1>")
                elif line.startswith('Speaker2:'):
                    text = line.replace('Speaker2:', '', 1).strip()
                    prompt_parts.append(f"<speaker:Speaker2>{text}</speaker:Speaker2>")
            
            final_prompt = "\n".join(prompt_parts)
            logger.info(f"Generated multi-speaker prompt: {final_prompt}")

            # --- 2. Build the configuration object ---
            config_object = types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                        speaker_voice_configs=[
                            types.SpeakerVoiceConfig(
                                speaker='Speaker1',
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                        voice_name=voice1_name,
                                    )
                                )
                            ),
                            types.SpeakerVoiceConfig(
                                speaker='Speaker2',
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                        voice_name=voice2_name,
                                    )
                                )
                            ),
                        ]
                    )
                )
            )

            # --- 3. Call the API ---
            logger.info("Sending request to API (client timeout is 600,000 milliseconds)...")
            response = client.models.generate_content(
                model=MODEL_TTS,
                contents=final_prompt,
                config=config_object
            )
            logger.info("API response received.")
            
            # ★★★ ここがご指示のあった修正箇所です ★★★
            # 'audio'属性が存在しないエラーに基づき、'content'属性から音声データを取得します。
            audio_data = data = response.candidates[0].content.parts[0].inline_data.data
            
            if audio_data:
                with wave.open(filepath, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(24000)
                    wav_file.writeframes(audio_data)

                logger.info(f"Successfully generated multi-speaker audio file: {filepath}")
                return jsonify({
                    'audio_file_name': filename,
                    'message': 'マルチスピーカー音声の生成が完了しました。'
                })
            else:
                logger.warning("No audio data received from multi-speaker API.")
                return jsonify({'error': '音声データの生成に失敗しました。APIからのデータがありません。'}), 500

        except Exception as speech_error:
            logger.error(f"Multi-speaker speech generation failed: {str(speech_error)}")
            return jsonify({'error': f'マルチスピーカー音声の生成中にエラーが発生しました: {str(speech_error)}'}), 500

    except Exception as e:
        logger.error(f"Error in generate_audio: {str(e)}")
        return jsonify({'error': f'音声生成中に予期せぬエラーが発生しました: {str(e)}'}), 500

@app.route('/static/audio/<filename>')
def serve_audio(filename):
    """Serve audio files"""
    try:
        return send_from_directory(AUDIO_DIR, filename, as_attachment=False)
    except FileNotFoundError:
        logger.warning(f"Audio file not found: {filename}")
        return jsonify({'error': 'ファイルが見つかりません。'}), 404
    except Exception as e:
        logger.error(f"Error serving audio file {filename}: {str(e)}")
        return jsonify({'error': 'ファイルの提供中にエラーが発生しました。'}), 500

@app.route('/api/voices')
def get_available_voices():
    """Get available voice models for the preview model"""
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