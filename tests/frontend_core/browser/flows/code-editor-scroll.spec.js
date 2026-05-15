/**
 * flows-code-editor — размеры и скролл CodeMirror для длинного JSON.
 */

import { fixture, fixtureCleanup, html, expect, waitUntil, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory } from '@platform/lib/events/index.js';
import { codeCompletionsOp } from '../../../../apps/flows/ui/events/resources/code.resource.js';
import '../../../../apps/flows/ui/components/editors/flows-code-editor.js';

function bootstrap() {
    registerFactory(codeCompletionsOp);
    const collected = collectFactories([codeCompletionsOp]);
    bootstrapTestBus({ slices: collected.slices });
}

describe('flows-code-editor scroll sizing', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrap();
    });
    afterEach(() => fixtureCleanup());

    it('не раздувает ширину контейнера на длинной JSON-строке и даёт вертикальный скролл', async () => {
        const longText = 'x'.repeat(6000);
        const json = JSON.stringify({ attributes: { 'platform.llm.request': longText } }, null, 2);
        const host = await fixture(html`
            <div style="width: 360px; height: 220px; display: flex; min-width: 0;">
                <flows-code-editor
                    language="json"
                    readonly
                    fill-parent
                    .value=${json}
                ></flows-code-editor>
            </div>
        `);
        const editor = host.querySelector('flows-code-editor');

        await waitUntil(() => editor.shadowRoot.querySelector('.cm-editor'), 'CodeMirror mounted');
        await elementUpdated(editor);

        const cmEditor = editor.shadowRoot.querySelector('.cm-editor');
        const scroller = editor.shadowRoot.querySelector('.cm-scroller');
        const content = editor.shadowRoot.querySelector('.cm-content');

        expect(cmEditor.clientWidth).to.be.at.most(360);
        expect(scroller.clientWidth).to.be.at.most(360);
        expect(content.classList.contains('cm-lineWrapping')).to.equal(true);
        expect(scroller.scrollHeight).to.be.greaterThan(scroller.clientHeight);
    });
});
