/**
 * platform-confirm-modal — L1 contract (T0 backlog): module registration smoke
 * + prompt-режим (platformPrompt).
 */
import { expect } from '../../../../frontend_core/browser/helpers/render.js';
import {
    resetPlatformState,
    bootstrapTestBus,
} from '../../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-confirm-modal.js';
import { platformPrompt } from '@platform/lib/components/platform-confirm-modal.js';
import { shadowQuery, shadowQueryAll } from '../../helpers/shadow-dom.js';
import type { TestEl } from '../../../../frontend_core/browser/helpers/dom.js';

describe('platform-confirm-modal', () => {
    beforeEach(() => bootstrapTestBus());
    afterEach(() => {
        document.querySelector('platform-confirm-modal')?.remove();
        resetPlatformState();
    });

    it('registers custom element', async () => {
        expect(customElements.get('platform-confirm-modal')).to.exist;
    });

    it('prompt mode renders platform-field and resolves input value', async () => {
        const promise = platformPrompt('Введите URL', { inputLabel: 'URL' });
        const modal = document.querySelector('platform-confirm-modal') as TestEl | null;
        expect(modal).to.exist;
        await modal!.updateComplete;
        const field = shadowQuery(modal!, 'platform-field');
        expect(field, 'inputLabel включает platform-field').to.exist;
        modal!.inputValue = 'https://example.com';
        modal!._onConfirm();
        const result = await promise;
        expect(result).to.equal('https://example.com');
        modal!.close();
    });

    it('prompt cancel resolves undefined', async () => {
        const promise = platformPrompt('Введите URL', { inputLabel: 'URL' });
        const modal = document.querySelector('platform-confirm-modal') as TestEl | null;
        modal!._onCancel();
        expect(await promise).to.equal(undefined);
    });
});
