/**
 * HTTP-оригин voice для embed: тот же хост, что и flows A2A.
 */
import { describe, it, expect } from 'vitest';
import { resolveVoiceHttpOriginFromFlowsBaseUrl } from '@platform/lib/voice/voice-http-origin.js';

describe('resolveVoiceHttpOriginFromFlowsBaseUrl', () => {
    it('maps …/flows to …/voice', () => {
        expect(resolveVoiceHttpOriginFromFlowsBaseUrl('https://tenant.example.com/flows')).toBe(
            'https://tenant.example.com/voice',
        );
        expect(resolveVoiceHttpOriginFromFlowsBaseUrl('https://tenant.example.com/flows/')).toBe(
            'https://tenant.example.com/voice',
        );
    });

    it('uses URL origin when path does not end with /flows', () => {
        expect(resolveVoiceHttpOriginFromFlowsBaseUrl('https://api.example.com')).toBe('https://api.example.com/voice');
    });

    it('rejects empty string', () => {
        expect(() => resolveVoiceHttpOriginFromFlowsBaseUrl('')).toThrow(
            'resolveVoiceHttpOriginFromFlowsBaseUrl: flowsBaseUrl is empty',
        );
    });

    it('rejects non-string', () => {
        expect(() => resolveVoiceHttpOriginFromFlowsBaseUrl(null)).toThrow(
            'resolveVoiceHttpOriginFromFlowsBaseUrl: string required',
        );
    });
});
