/**
 * Класс для записи голоса через браузер в формате OGG/Opus
 */

class VoiceRecorder {
    constructor() {
        this.recorder = null;
        this.stream = null;
        this.isRecording = false;
    }

    async startRecording() {
        try {
            console.log('🎤 Запрашиваем доступ к микрофону...');
            this.stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 48000
                } 
            });

            console.log('✅ Доступ к микрофону получен');
            
            this.recorder = new Recorder({
                encoderPath: '/static/js/encoderWorker.min.js',
                encoderSampleRate: 16000,
                encoderApplication: 2048,
                encoderFrameSize: 20,
                encoderComplexity: 10,
                encoderBitRate: 16000,
                streamPages: false,
                numberOfChannels: 1,
                sourceNode: this.stream
            });

            this.recorder.onerror = (error) => {
                console.error('❌ Ошибка Opus Recorder:', error);
            };

            await this.recorder.start();
            this.isRecording = true;
            
            console.log('🎤 Запись началась в формате OGG/Opus');
            return true;
        } catch (error) {
            console.error('❌ Ошибка доступа к микрофону:', error);
            
            let errorMessage = 'Не удалось получить доступ к микрофону. ';
            if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                errorMessage += 'Проверьте разрешения браузера.';
            } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
                errorMessage += 'Микрофон не найден.';
            } else if (error.name === 'NotSupportedError') {
                errorMessage += 'Формат записи не поддерживается.';
            } else {
                errorMessage += error.message;
            }
            
            alert(errorMessage);
            return false;
        }
    }

    async stopRecording() {
        return new Promise((resolve, reject) => {
            if (!this.recorder || !this.isRecording) {
                reject(new Error('Запись не начата'));
                return;
            }

            this.recorder.ondataavailable = (typedArray) => {
                console.log('🎤 Получены аудио данные:', typedArray.length, 'байт');
                
                const audioBlob = new Blob([typedArray], { type: 'audio/ogg; codecs=opus' });
                
                if (this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                    this.stream = null;
                }

                this.isRecording = false;
                console.log('🎤 Запись завершена, размер Blob:', audioBlob.size, 'байт');
                
                resolve({
                    blob: audioBlob,
                    mimeType: 'audio/ogg; codecs=opus'
                });
            };

            this.recorder.stop();
        });
    }

    cancelRecording() {
        if (this.recorder && this.isRecording) {
            this.recorder.stop();
            
            if (this.stream) {
                this.stream.getTracks().forEach(track => track.stop());
                this.stream = null;
            }
            
            this.isRecording = false;
            console.log('🎤 Запись отменена');
        }
    }
}

export default VoiceRecorder;

