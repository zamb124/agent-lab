import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import {
    clampLaraPanelWidth,
    LARA_PANEL_WIDTH_MAX_CAP_PX,
    LARA_PANEL_WIDTH_MIN_PX,
    readLaraPanelWidth,
    writeLaraPanelWidth,
} from '../../../../core/frontend/static/lib/chat/panel-width-preference.js';
import { platformStorageKey } from '../../../../core/frontend/static/lib/utils/storage-keys.js';

describe('panel-width-preference', () => {
    const storage = new Map();

    beforeEach(() => {
        storage.clear();
        vi.stubGlobal('window', {
            localStorage: {
                getItem(key) {
                    return storage.has(key) ? storage.get(key) : null;
                },
                setItem(key, value) {
                    storage.set(key, String(value));
                },
                removeItem(key) {
                    storage.delete(key);
                },
            },
        });
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('clamps to min and viewport-aware max', () => {
        expect(clampLaraPanelWidth(100, 1400)).to.equal(LARA_PANEL_WIDTH_MIN_PX);
        expect(clampLaraPanelWidth(2000, 1400)).to.equal(LARA_PANEL_WIDTH_MAX_CAP_PX);
        expect(clampLaraPanelWidth(500, 400)).to.equal(376);
    });

    it('persists and restores width', () => {
        expect(readLaraPanelWidth('crm', 'crm')).to.equal(null);
        writeLaraPanelWidth('crm', 'crm', 520);
        expect(storage.get(platformStorageKey('crm', 'lara_panel_width.crm'))).to.equal('520');
        expect(readLaraPanelWidth('crm', 'crm')).to.equal(520);
    });

    it('rejects width below min on write', () => {
        expect(() => writeLaraPanelWidth('crm', 'crm', 200)).to.throw(/>= 320/);
    });
});
