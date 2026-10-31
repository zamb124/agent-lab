/**
 * flows-code-editor — размеры и скролл CodeMirror для длинного JSON.
 */

import { fixture, fixtureCleanup, html, expect, waitUntil, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories, registerFactory, getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import '@platform/lib/components/platform-modal-stack.js';
import { codeLspSessionOp } from '../../../../apps/flows/ui/events/resources/code.resource.js';
import '../../../../apps/flows/ui/components/editors/flows-code-editor.js';
import '../../../../apps/flows/ui/modals/flows-raw-json-modal.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

function bootstrap() {
    registerFactory(codeLspSessionOp);
    const collected = collectFactories([codeLspSessionOp]);
    bootstrapTestBus({ slices: collected.slices });
}

describe('flows-code-editor scroll sizing', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrap();
    });
    afterEach(() => {
        for (const el of qsa(document!, 'flows-raw-json-modal')) {
            el.remove();
        }
        fixtureCleanup();
    });

    it('codemirror lazy chunk exposes all isolated runner language modes', async () => {
        const cm = await import('@platform/lib/codemirror/codemirror-lazy.js');
        expect(cm.python).to.be.a('function');
        expect(cm.javascript).to.be.a('function');
        expect(cm.go).to.be.a('function');
        expect(cm.csharp).to.be.a('function');
        expect(cm.json).to.be.a('function');
        expect(cm.LSPClient).to.be.a('function');
        expect(cm.languageServerExtensions).to.be.a('function');
        expect(cm.startCompletion).to.be.a('function');
    });

    it('не раздувает ширину контейнера на длинной JSON-строке и даёт вертикальный скролл', async () => {
        const longText = 'x'.repeat(6000);
        const json = JSON.stringify({ attributes: { 'platform.llm.request': longText } }, null, 2);
        const host = await fixture<TestEl>(html`
            <div style="width: 360px; height: 220px; display: flex; min-width: 0;">
                <flows-code-editor
                    language="json"
                    readonly
                    fill-parent
                    .value=${json}
                ></flows-code-editor>
            </div>
        `);
        const editor = qs(host!, 'flows-code-editor');

        await waitUntil(() => q(shadow(editor), '.cm-editor'), 'CodeMirror mounted');
        await elementUpdated(editor);

        const cmEditor = qs(shadow(editor), '.cm-editor');
        const scroller = qs(shadow(editor), '.cm-scroller');
        const content = qs(shadow(editor), '.cm-content');

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
        const stack = await fixture<TestEl>(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, {
            kind: 'flows.raw_json',
            props: { value: longPayload },
        });
        await elementUpdated(stack);

        await waitUntil(
            () => q(document!, 'flows-raw-json-modal'),
            'raw JSON modal mounted',
        );
        const modal = qs(document!, 'flows-raw-json-modal');
        await waitUntil(
            () => q(shadow(modal), 'flows-code-editor'),
            'raw JSON editor mounted',
        );
        const editor = qs(shadow(modal), 'flows-code-editor');
        await waitUntil(
            () => q(shadow(editor), '.cm-editor'),
            'CodeMirror mounted in raw JSON modal',
        );

        const scroller = qs(shadow(editor), '.cm-scroller');
        expect(editor.fillParent).to.equal(true);
        expect(editor.hasAttribute('fill-parent')).to.equal(true);
        expect(editor.hasAttribute('fillparent')).to.equal(false);
        expect(editor.showToolbar).to.equal(false);
        expect(q(shadow(editor), '.editor-header')).to.equal(null);
        expect(scroller.scrollHeight).to.be.greaterThan(scroller.clientHeight);
    });
});
