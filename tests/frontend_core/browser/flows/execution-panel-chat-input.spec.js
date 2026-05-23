import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { TTS_OUTPUT_STORAGE_KEY } from '@platform/lib/voice/tts-output-pref.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { chatResource, chatSendOp, chatCancelOp } from '../../../../apps/flows/ui/events/resources/chat.resource.js';
import { fileUploadOp } from '../../../../apps/flows/ui/events/resources/files.resource.js';
import { executionUiSlice } from '../../../../apps/flows/ui/events/resources/execution-ui.resource.js';
import '../../../../apps/flows/ui/components/editor/flows-execution-panel.js';
import '../../../../apps/flows/ui/components/chat/chat-input.js';
import '../../../../core/frontend/static/lib/embed-chat/embed-chat-input.js';

const FACTORIES = [
    editorResource,
    chatResource,
    chatSendOp,
    chatCancelOp,
    fileUploadOp,
    executionUiSlice,
];

function bootstrapExecutionPanelBus() {
    for (const factory of FACTORIES) {
        registerFactory(factory);
    }
    const collected = collectFactories(FACTORIES);
    const bus = bootstrapTestBus({ slices: collected.slices, effects: [] });
    bus.dispatch('flows/editor/execution_panel_set', { open: true });
    return bus;
}

describe('flows-execution-panel unified chat input', () => {
    beforeEach(() => {
        resetPlatformState();
        window.localStorage.setItem(TTS_OUTPUT_STORAGE_KEY, '0');
    });

    afterEach(() => {
        fixtureCleanup();
        window.localStorage.removeItem(TTS_OUTPUT_STORAGE_KEY);
    });

    it('рендерит общий chat-input вместо локального textarea/file chips', async () => {
        bootstrapExecutionPanelBus();
        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'branch-1'}></flows-execution-panel>
        `);
        await elementUpdated(el);

        const input = el.shadowRoot.querySelector('chat-input.execution-chat-input');
        expect(input).to.not.equal(null);
        expect(input.accept).to.equal('*/*');
        expect(input.shadowRoot.querySelector('flows-chat-input')).to.not.equal(null);
        expect(el.shadowRoot.querySelector('#flows-exec-compose-textarea')).to.equal(null);
        expect(el.shadowRoot.querySelector('#flows-exec-file-input')).to.equal(null);
        expect(el.shadowRoot.querySelector('.file-chip')).to.equal(null);
    });

    it('chat-input adapter forwards the core send event exactly once', async () => {
        bootstrapExecutionPanelBus();
        const el = await fixture(html`<chat-input></chat-input>`);
        await elementUpdated(el);

        const core = el.shadowRoot.querySelector('flows-chat-input');
        const received = [];
        el.addEventListener('send', (event) => received.push(event.detail));
        core.setDraft(' hello ');
        await core.updateComplete;
        core.shadowRoot.querySelector('.send-btn').click();

        expect(received).to.deep.equal([{ message: 'hello', files: [] }]);
    });

    it('embed-chat-input adapter forwards the core send event as embed-send exactly once', async () => {
        const el = await fixture(html`<embed-chat-input></embed-chat-input>`);
        await elementUpdated(el);

        const core = el.shadowRoot.querySelector('flows-chat-input');
        const received = [];
        const leaked = [];
        el.addEventListener('embed-send', (event) => received.push(event.detail));
        el.addEventListener('send', (event) => leaked.push(event.detail));
        core.setDraft(' hello ');
        await core.updateComplete;
        core.shadowRoot.querySelector('.send-btn').click();

        expect(received).to.deep.equal([{ message: 'hello', files: [] }]);
        expect(leaked).to.deep.equal([]);
    });
});
