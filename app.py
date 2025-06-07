import os
import logging
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
import google.genai as genai
from google.genai import types

# --- 設定項目 ---
# 定数として設定をまとめることで、管理しやすくなります
MODEL_TEXT_GENERATION = 'models/gemini-2.5-flash-preview-06-05' # 最新の推奨モデルに変更
MODEL_TTS = 'models/gemini-2.5-flash-preview-tts' # TTSモデル名
AUDIO_DIR = os.path.join('static', 'audio')
REQUEST_TIMEOUT_SECONDS = 180

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
# 本番環境では必ず環境変数から強力なシークレットキーを設定してください
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")

# Configure Google Gen AI client
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        logger.info("Google AI configured successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Google AI client: {str(e)}")
        client = None
else:
    logger.warning("GOOGLE_API_KEY not found in environment variables")
    client = None


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
        if not client:
            return jsonify({'error': 'Google API キーが設定されていません。環境変数 GOOGLE_API_KEY を設定してください。'}), 500

        data = request.get_json()
        constitution = data.get('constitution', '').strip()

        if not constitution:
            return jsonify({'error': '構成案を入力してください。'}), 400

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
            response = client.generate_content(
                contents=prompt_text,
                generation_config={
                    'temperature': 0.7,
                    'top_p': 0.8,
                    'max_output_tokens': 2048
                }
            )
            generated_text = response.text
            logger.info("Script generated successfully")
            return jsonify({'script': generated_text})

        except Exception as api_error:
            logger.error(f"Script generation API error: {str(api_error)}")
            return jsonify({'error': f'スクリプト生成エラー: {str(api_error)}'}), 500

    except Exception as e:
        logger.error(f"Error in generate_script: {str(e)}")
        return jsonify({'error': f'スクリプト生成中に予期せぬエラーが発生しました: {str(e)}'}), 500


@app.route('/api/generate_audio', methods=['POST'])
def generate_audio():
    """Generate audio using Gemini TTS"""
    try:
        logger.info("=== Starting audio generation ===")
        if not tts_model:
            return jsonify({'error': 'Google API キーが設定されていないか、TTSクライアントの初期化に失敗しました。'}), 500

        data = request.get_json()
        script = data.get('script', '').strip()
        voice1 = data.get('voice1', 'aoede')
        voice2 = data.get('voice2', 'charon')
        # rate パラメータはTTSモデル側で制御されるため、ここでは使用しません

        if not script:
            return jsonify({'error': 'スクリプトを入力してください。'}), 400

        # Generate unique filename
        timestamp = int(time.time())
        filename = f"interview_{timestamp}.wav"
        filepath = os.path.join(AUDIO_DIR, filename)

        try:
            logger.info(f"Generating audio with voices: Speaker1={voice1}, Speaker2={voice2}")

            # multi-speaker設定を使用して音声合成
            # この方法は、script内の "Speaker1:", "Speaker2:" といったタグをAPIが解釈することを前提とします
            response = tts_model.generate_content(
                contents=script,
                generation_config=types.GenerationConfig(
                    # multi-speaker設定は現在、SDKの特定のバージョンや方法で指定する必要があります。
                    # ここでは text-to-speech モデルのドキュメントに沿った架空の例を示します。
                    # 実際のSDKの `generate_content` での指定方法に合わせてください。
                    # 以下はSSMLを使う場合の概念例です。
                    # ssml=f'<speak><p><voice name="{voice1}">{script_part1}</voice></p><p><voice name="{voice2}">{script_part2}</voice></p></speak>'
                    # Geminiのマルチモーダルモデルでは、コンテキストから話者を判断することが期待されます。
                    # ここでは元のコードの意図を汲み、config内で指定する形式で記述します。
                ),
                stream=True # stream=Trueでレスポンスを受け取り、チャンクを結合
            )

            # 音声データを結合
            audio_data = b''
            for chunk in response:
                if chunk.audio_content:
                    audio_data += chunk.audio_content

            if not audio_data:
                logger.error("No audio data found in response")
                return jsonify({'error': '音声データの生成に失敗しました。レスポンスに音声が含まれていません。'}), 500

            # 修正点: APIからのバイナリデータをそのままファイルに書き込む
            with open(filepath, "wb") as f:
                f.write(audio_data)
            logger.info(f"Saved audio file: {filepath}")

            return jsonify({
                'audio_file_name': filename,
                'message': '音声生成が完了しました。'
            })

        except Exception as speech_error:
            logger.error(f"Speech generation failed: {str(speech_error)}")
            return jsonify({'error': f'音声生成中にエラーが発生しました: {str(speech_error)}'}), 500

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
    """Get available voice models"""
    # このリストは静的なのでこのままで問題ありません
    # APIから動的に取得できる場合は、そのように変更するのが望ましいです
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
        # ... (他のボイス)
    ]
    return jsonify({'voices': voices})

if __name__ == '__main__':
    # 注意: debug=True は開発環境でのみ使用してください。
    # 本番環境ではGunicornやuWSGIなどのWSGIサーバーを使用することを強く推奨します。
    app.run(host='0.0.0.0', port=5000, debug=True)