import { describe, it, expect } from 'vitest';
import {
    isSpeechOriginText,
    messageHasSpeechOriginText,
} from '../../../apps/sync/ui/_helpers/sync-speech-origin.js';

describe('sync-speech-origin', () => {
    it('isSpeechOriginText: origin=speech', () => {
        expect(isSpeechOriginText({
            type: 'text/plain',
            data: { body: 'привет', origin: 'speech' },
        })).toBe(true);
        expect(isSpeechOriginText({
            type: 'text/plain',
            data: { body: 'привет', origin: 'typed' },
        })).toBe(false);
        expect(isSpeechOriginText({
            type: 'file/audio',
            data: { file_id: 'f1' },
        })).toBe(false);
    });

    it('messageHasSpeechOriginText: непустой speech-блок', () => {
        expect(messageHasSpeechOriginText([
            { type: 'text/plain', data: { body: 'из аудио', origin: 'speech' } },
            { type: 'file/audio', data: { transcription_text: 'из аудио' } },
        ])).toBe(true);
        expect(messageHasSpeechOriginText([
            { type: 'file/audio', data: { transcription_text: 'из аудио' } },
        ])).toBe(false);
        expect(messageHasSpeechOriginText([
            { type: 'text/plain', data: { body: '   ', origin: 'speech' } },
        ])).toBe(false);
        expect(() => messageHasSpeechOriginText([
            { type: 'text/plain', data: { origin: 'speech' } },
        ])).toThrow();
    });

    it('невалидный contents — throw', () => {
        expect(() => messageHasSpeechOriginText(null)).toThrow();
        expect(() => isSpeechOriginText(null)).toThrow();
    });
});
