/**
 * flows-code-editor — размеры и скролл CodeMirror для длинного JSON.
 */

import { fixture, fixtureCleanup, html, expect, waitUntil, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-modal-stack.js';
import { codeCompletionsOp } from '../../../../apps/flows/ui/events/resources/code.resource.js';
import '../../../../apps/flows/ui/components/editors/flows-code-editor.js';
import '../../../../apps/flows/ui/modals/flows-raw-json-modal.js';

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
    afterEach(() => {
        for (const el of document.querySelectorAll('flows-raw-json-modal')) {
            el.remove();
        }
        fixtureCleanup();
    });

    it('codemirror bundle exposes all isolated runner language modes', async () => {
        const cm = await import('/static/core/assets/codemirror/codemirror-bundle.js');
        expect(cm.python).to.be.a('function');
        expect(cm.javascript).to.be.a('function');
        expect(cm.go).to.be.a('function');
        expect(cm.csharp).to.be.a('function');
        expect(cm.json).to.be.a('function');
    });

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

    it('raw JSON modal mounts editor as fill-parent without toolbar, so modal scrolling stays inside CodeMirror', async () => {
        const longPayload = {
            rows: Array.from({ length: 220 }, (_, index) => ({
                index,
                text: `row-${index}-${'x'.repeat(120)}`,
            })),
        };
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, {
            kind: 'flows.raw_json',
            props: { value: longPayload },
        });
        await elementUpdated(stack);

        await waitUntil(
            () => document.querySelector('flows-raw-json-modal'),
            'raw JSON modal mounted',
        );
        const modal = document.querySelector('flows-raw-json-modal');
        await waitUntil(
            () => modal.shadowRoot.querySelector('flows-code-editor'),
            'raw JSON editor mounted',
        );
        const editor = modal.shadowRoot.querySelector('flows-code-editor');
        await waitUntil(
            () => editor.shadowRoot.querySelector('.cm-editor'),
            'CodeMirror mounted in raw JSON modal',
        );

        const scroller = editor.shadowRoot.querySelector('.cm-scroller');
        expect(editor.fillParent).to.equal(true);
        expect(editor.hasAttribute('fill-parent')).to.equal(true);
        expect(editor.hasAttribute('fillparent')).to.equal(false);
        expect(editor.showToolbar).to.equal(false);
        expect(editor.shadowRoot.querySelector('.editor-header')).to.equal(null);
        expect(scroller.scrollHeight).to.be.greaterThan(scroller.clientHeight);
    });
});
