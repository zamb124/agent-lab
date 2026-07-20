/**
 * Единая platform dictation factory → POST /voice/api/v1/transcribe
 */

import { createAsyncOp } from './async-op.js';
import { httpRequest } from '../http.js';

const VOICE_TRANSCRIBE_URL = '/voice/api/v1/transcribe';

/**
 * @param {{ name?: string }} [config]
 */
export function createPlatformVoiceDictationOp(config = {}) {
    const name = typeof config.name === 'string' && config.name.length > 0
        ? config.name
        : 'platform/voice_dictation';

    return createAsyncOp({
        name,
        transport: 'http',
        successToastKey: 'platform:toast.voice_dictation.succeeded',
        errorToastKey: 'platform:toast.voice_dictation.failed',
        restMirror: { method: 'POST', path: VOICE_TRANSCRIBE_URL },
        request: async ({ payload }) => {
            if (!payload || typeof payload !== 'object' || !(payload.audio instanceof Blob)) {
                throw new Error(`${name}: payload.audio (Blob) required`);
            }
            const fileName = typeof payload.file_name === 'string' && payload.file_name.length > 0
                ? payload.file_name
                : 'voice-input.webm';
            const formData = new FormData();
            formData.append('file', payload.audio, fileName);
            if (typeof payload.language === 'string' && payload.language.length > 0) {
                formData.append('language', payload.language);
            }
            return httpRequest({
                method: 'POST',
                url: VOICE_TRANSCRIBE_URL,
                body: formData,
            });
        },
    });
}

export const platformVoiceDictationOp = createPlatformVoiceDictationOp();
