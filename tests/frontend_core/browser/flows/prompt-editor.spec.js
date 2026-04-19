/**
 * Smoke: flows-prompt-editor — рендер textarea + popover автодополнения @var:.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '../../../../apps/flows/ui/components/editors/flows-prompt-editor.js';

describe('flows-prompt-editor', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });
    afterEach(() => fixtureCleanup());

    it('emit change при вводе', async () => {
        const el = await fixture(html`<flows-prompt-editor></flows-prompt-editor>`);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const ta = el.shadowRoot.querySelector('textarea');
        ta.value = 'hello';
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        expect(last).to.deep.equal({ value: 'hello' });
    });

    it('@var: показывает popover из flowVariables', async () => {
        const flowVariables = { user_name: { title: 'User', description: 'name of user' }, chat_id: 1 };
        const el = await fixture(html`
            <flows-prompt-editor .flowVariables=${flowVariables}></flows-prompt-editor>
        `);
        const ta = el.shadowRoot.querySelector('textarea');
        ta.focus();
        ta.value = 'Hello @var:u';
        ta.setSelectionRange(ta.value.length, ta.value.length);
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        await elementUpdated(el);
        const items = el.shadowRoot.querySelectorAll('.popover .item');
        expect(items.length).to.equal(1);
        expect(items[0].textContent).to.contain('user_name');
    });
});
