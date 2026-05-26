/**
 * prefs авто-TTS: canonical localStorage key.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { installFakeStorage } from '../../helpers/fake-storage.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';

let storage;
let prevWindow;

beforeEach(() => {
    storage = installFakeStorage();
    prevWindow = globalThis.window;
    globalThis.window = {
        localStorage: storage.localStorage,
        dispatchEvent: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
    };
});

afterEach(() => {
    storage.uninstall();
    globalThis.window = prevWindow;
});

describe('tts-output-pref', () => {
    it('по умолчанию true при пустом storage', async () => {
        const m = await import('@platform/lib/voice/tts-output-pref.js');
        expect(m.readTtsOutputEnabled()).toBe(true);
    });

    it('write/read через canonical key', async () => {
        const m = await import('@platform/lib/voice/tts-output-pref.js');
        const canonical = platformStorageKey('voice', 'tts_output_enabled');
        expect(m.TTS_OUTPUT_STORAGE_KEY).toBe(canonical);
        m.writeTtsOutputEnabled(false);
        expect(storage.localStorage.getItem(canonical)).toBe('0');
        expect(m.readTtsOutputEnabled()).toBe(false);
        m.writeTtsOutputEnabled(true);
        expect(storage.localStorage.getItem(canonical)).toBe('1');
        expect(m.readTtsOutputEnabled()).toBe(true);
        expect(globalThis.window.dispatchEvent).toHaveBeenCalled();
    });

    it('toggleTtsOutputEnabled переключает значение', async () => {
        const m = await import('@platform/lib/voice/tts-output-pref.js');
        expect(m.toggleTtsOutputEnabled()).toBe(false);
        expect(m.readTtsOutputEnabled()).toBe(false);
        expect(m.toggleTtsOutputEnabled()).toBe(true);
        expect(m.readTtsOutputEnabled()).toBe(true);
    });
});
