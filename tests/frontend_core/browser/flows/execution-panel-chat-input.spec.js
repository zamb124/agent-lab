import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { TTS_OUTPUT_STORAGE_KEY } from '@platform/lib/voice/tts-output-pref.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { executionUiSlice } from '../../../../apps/flows/ui/events/resources/execution-ui.resource.js';
import '../../../../apps/flows/ui/components/editor/flows-execution-panel.js';

const FACTORIES = [
    editorResource,
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

describe('flows-execution-panel hosts unified platform-chat', () => {
    beforeEach(() => {
        resetPlatformState();
        window.localStorage.setItem(TTS_OUTPUT_STORAGE_KEY, '0');
    });

    afterEach(() => {
        fixtureCleanup();
        window.localStorage.removeItem(TTS_OUTPUT_STORAGE_KEY);
    });

    it('вкладка Chat — это <platform-chat display="panel" profile="editor_test">, без локального composer', async () => {
        bootstrapExecutionPanelBus();
        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'branch-1'}></flows-execution-panel>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        expect(chat).to.not.equal(null);
        expect(chat.getAttribute('display')).to.equal('panel');
        expect(chat.getAttribute('profile')).to.equal('editor_test');
        expect(chat.getAttribute('flow-id')).to.equal('flow-1');
        expect(chat.getAttribute('branch-id')).to.equal('branch-1');
        expect(el.shadowRoot.querySelector('chat-input')).to.equal(null);
        expect(el.shadowRoot.querySelector('#flows-exec-compose-textarea')).to.equal(null);
        expect(el.shadowRoot.querySelector('.file-chip')).to.equal(null);
    });

    it('persistContext=false транслируется в fresh-context-per-turn', async () => {
        const bus = bootstrapExecutionPanelBus();
        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'base'}></flows-execution-panel>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        expect(chat.freshContextPerTurn).to.equal(false);

        bus.dispatch('flows/execution_ui/persist_context_toggled', { value: false });
        await elementUpdated(el);
        await elementUpdated(chat);
        expect(chat.freshContextPerTurn).to.equal(true);
    });

    it('getSendMetadata отдаёт breakpoints превью редактора', async () => {
        const bus = bootstrapExecutionPanelBus();
        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'base'}></flows-execution-panel>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        expect(chat.getSendMetadata()).to.deep.equal({});

        bus.dispatch('flows/editor/preview_state_set', {
            snapshot: { breakpoints: ['node_a', 'node_b'] },
        });
        await elementUpdated(el);
        expect(chat.getSendMetadata()).to.deep.equal({ breakpoints: ['node_a', 'node_b'] });
    });

    it('chat-run-event ретранслируется в bus и двигает agentExecutionRunning', async () => {
        const bus = bootstrapExecutionPanelBus();
        const seen = [];
        bus.subscribeType('flows/run/flow_started', (event) => seen.push(event.type));
        bus.subscribeType('flows/run/flow_done', (event) => seen.push(event.type));

        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'base'}></flows-execution-panel>
        `);
        await elementUpdated(el);
        const chat = el.shadowRoot.querySelector('platform-chat');

        chat.dispatchEvent(new CustomEvent('chat-run-event', {
            detail: { type: 'flows/run/flow_started', payload: {} },
            bubbles: true,
            composed: true,
        }));
        await elementUpdated(el);
        expect(seen).to.deep.equal(['flows/run/flow_started']);

        chat.dispatchEvent(new CustomEvent('chat-run-event', {
            detail: { type: 'flows/run/flow_done', payload: {} },
            bubbles: true,
            composed: true,
        }));
        await elementUpdated(el);
        expect(seen).to.deep.equal(['flows/run/flow_started', 'flows/run/flow_done']);
    });

    it('закрытие панели скрывает host, но не размонтирует platform-chat (история живёт)', async () => {
        const bus = bootstrapExecutionPanelBus();
        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'base'}></flows-execution-panel>
        `);
        await elementUpdated(el);
        const chat = el.shadowRoot.querySelector('platform-chat');
        expect(el.hasAttribute('data-panel-closed')).to.equal(false);

        bus.dispatch('flows/editor/execution_panel_set', { open: false });
        await elementUpdated(el);
        expect(el.hasAttribute('data-panel-closed')).to.equal(true);
        expect(el.shadowRoot.querySelector('platform-chat')).to.equal(chat);
    });
});
