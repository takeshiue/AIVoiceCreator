// Main JavaScript for AI Interview Generator
class InterviewGenerator {
    constructor() {
        this.currentAudioFile = null;
        this.availableVoices = [];
        this.init();
    }

    async init() {
        this.bindEvents();
        await this.loadAvailableVoices();
        this.showAlert('アプリケーションが準備完了しました。', 'success');
    }

    bindEvents() {
        // Script generation
        document.getElementById('generate_script_button').addEventListener('click', () => {
            this.generateScript();
        });

        // Audio generation
        document.getElementById('generate_audio_button').addEventListener('click', () => {
            this.generateAudio();
        });

        // Download audio
        document.getElementById('download_audio_button').addEventListener('click', () => {
            this.downloadAudio();
        });

        // Enter key support for constitution input
        document.getElementById('constitution_input').addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                this.generateScript();
            }
        });
    }

    async loadAvailableVoices() {
        try {
            const response = await fetch('/api/voices');
            const data = await response.json();
            
            if (data.voices) {
                this.availableVoices = data.voices;
                this.populateVoiceSelect();
            }
        } catch (error) {
            console.error('Error loading voices:', error);
            this.showAlert('音声モデルの読み込みに失敗しました。', 'error');
        }
    }

    populateVoiceSelect() {
        const voiceSelect = document.getElementById('voice_select');
        voiceSelect.innerHTML = '';
        
        this.availableVoices.forEach(voice => {
            const option = document.createElement('option');
            option.value = voice.id;
            option.textContent = voice.name;
            voiceSelect.appendChild(option);
        });
    }

    async generateScript() {
        const constitutionInput = document.getElementById('constitution_input');
        const constitution = constitutionInput.value.trim();
        
        if (!constitution) {
            this.showAlert('構成案を入力してください。', 'error');
            constitutionInput.focus();
            return;
        }

        const button = document.getElementById('generate_script_button');
        const originalText = button.textContent;
        
        try {
            this.setButtonLoading(button, 'スクリプト生成中...');
            
            const response = await fetch('/api/generate_script', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ constitution })
            });
            
            const data = await response.json();
            
            if (response.ok && data.script) {
                document.getElementById('script_display_edit_area').value = data.script;
                this.showAlert('スクリプトが正常に生成されました！', 'success');
                
                // Scroll to script section
                document.getElementById('script_display_edit_area').scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'start' 
                });
            } else {
                throw new Error(data.error || 'スクリプトの生成に失敗しました。');
            }
        } catch (error) {
            console.error('Script generation error:', error);
            this.showAlert(`エラー: ${error.message}`, 'error');
        } finally {
            this.setButtonLoading(button, originalText, false);
        }
    }

    async generateAudio() {
        const scriptArea = document.getElementById('script_display_edit_area');
        const script = scriptArea.value.trim();
        
        if (!script) {
            this.showAlert('音声生成用のスクリプトを入力してください。', 'error');
            scriptArea.focus();
            return;
        }

        const voice1 = document.getElementById('voice_select_1').value;
        const voice2 = document.getElementById('voice_select_2').value;
        const rate = parseFloat(document.getElementById('speaking_rate_control').value);
        const button = document.getElementById('generate_audio_button');
        const originalText = button.textContent;
        
        try {
            this.setButtonLoading(button, '音声生成中...');
            
            const response = await fetch('/api/generate_audio', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ script, voice1, voice2, rate })
            });
            
            const data = await response.json();
            
            if (response.ok && data.audio_file_name) {
                this.currentAudioFile = data.audio_file_name;
                this.setupAudioPlayer();
                this.showAlert(data.message || '音声が正常に生成されました！', 'success');
                
                // Scroll to audio section
                document.getElementById('audio_player').scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'start' 
                });
            } else {
                throw new Error(data.error || '音声の生成に失敗しました。');
            }
        } catch (error) {
            console.error('Audio generation error:', error);
            this.showAlert(`エラー: ${error.message}`, 'error');
        } finally {
            this.setButtonLoading(button, originalText, false);
        }
    }

    setupAudioPlayer() {
        if (!this.currentAudioFile) return;

        const audioPlayer = document.getElementById('audio_player');
        const downloadButton = document.getElementById('download_audio_button');
        
        // Set audio source
        audioPlayer.src = `/static/audio/${this.currentAudioFile}`;
        audioPlayer.style.display = 'block';
        
        // Enable download button
        downloadButton.classList.remove('hidden');
        downloadButton.disabled = false;

        // Add audio load event listener
        audioPlayer.addEventListener('loadeddata', () => {
            console.log('Audio loaded successfully');
        });

        audioPlayer.addEventListener('error', (e) => {
            console.error('Audio loading error:', e);
            this.showAlert('音声ファイルの読み込みに失敗しました。', 'error');
        });
    }

    downloadAudio() {
        if (!this.currentAudioFile) {
            this.showAlert('ダウンロード可能な音声ファイルがありません。', 'error');
            return;
        }

        const link = document.createElement('a');
        link.href = `/static/audio/${this.currentAudioFile}`;
        link.download = `interview_audio_${new Date().getTime()}.mp3`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        this.showAlert('音声ファイルのダウンロードを開始しました。', 'success');
    }

    setButtonLoading(button, text, isLoading = true) {
        if (isLoading) {
            button.disabled = true;
            button.innerHTML = `<span class="loading"><span class="spinner"></span>${text}</span>`;
        } else {
            button.disabled = false;
            button.textContent = text;
        }
    }

    showAlert(message, type = 'info') {
        // Remove existing alerts
        const existingAlerts = document.querySelectorAll('.alert');
        existingAlerts.forEach(alert => alert.remove());

        // Create new alert
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} fade-in`;
        alert.textContent = message;

        // Insert at the top of the main container
        const mainContainer = document.querySelector('.main-container');
        mainContainer.insertBefore(alert, mainContainer.firstChild);

        // Auto-remove after 5 seconds for success messages
        if (type === 'success') {
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, 5000);
        }

        // Scroll to alert
        alert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    clearAlert() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(alert => alert.remove());
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new InterviewGenerator();
});

// Add some utility functions for better UX
window.addEventListener('beforeunload', (e) => {
    const constitutionInput = document.getElementById('constitution_input');
    const scriptArea = document.getElementById('script_display_edit_area');
    
    if (constitutionInput.value.trim() || scriptArea.value.trim()) {
        e.preventDefault();
        e.returnValue = '作業中のデータが失われる可能性があります。本当にページを離れますか？';
    }
});

// Auto-save to localStorage periodically
setInterval(() => {
    const constitutionInput = document.getElementById('constitution_input');
    const scriptArea = document.getElementById('script_display_edit_area');
    
    if (constitutionInput && scriptArea) {
        localStorage.setItem('ai_interview_constitution', constitutionInput.value);
        localStorage.setItem('ai_interview_script', scriptArea.value);
    }
}, 30000); // Save every 30 seconds

// Restore from localStorage on page load
document.addEventListener('DOMContentLoaded', () => {
    const savedConstitution = localStorage.getItem('ai_interview_constitution');
    const savedScript = localStorage.getItem('ai_interview_script');
    
    if (savedConstitution) {
        document.getElementById('constitution_input').value = savedConstitution;
    }
    
    if (savedScript) {
        document.getElementById('script_display_edit_area').value = savedScript;
    }
});
