import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { TTS_OUTPUT_STORAGE_KEY } from '@platform/lib/voice/tts-output-pref.js';
import { editorResource } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { executionUiSlice } from '../../../../apps/flows/ui/events/resources/execution-ui.resource.js';
import { installChatProfileFetchStub } from '../helpers/chat-profile-stub.js';
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
    let restoreChatFetch;

    beforeEach(() => {
        resetPlatformState();
        restoreChatFetch = installChatProfileFetchStub({ flowId: 'flow-1' });
        window.localStorage.setItem(TTS_OUTPUT_STORAGE_KEY, '0');
    });

    afterEach(() => {
        restoreChatFetch();
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

    it('getSendMetadata отдаёт breakpoints с канвы редактора', async () => {
        const bus = bootstrapExecutionPanelBus();
        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'base'}></flows-execution-panel>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        expect(chat.getSendMetadata()).to.deep.equal({});

        bus.dispatch('flows/editor/breakpoint_toggled', { nodeId: 'node_a' });
        bus.dispatch('flows/editor/breakpoint_toggled', { nodeId: 'node_b' });
        await elementUpdated(el);
        expect(chat.getSendMetadata()).to.deep.equal({
            breakpoints: { node_a: true, node_b: true },
        });
    });

    it('chat-state-changed пробрасывает breakpoint hit на bus', async () => {
        const bus = bootstrapExecutionPanelBus();
        const hits = [];
        bus.subscribeType('flows/breakpoint/hit', (event) => hits.push(event.payload));

        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'base'}></flows-execution-panel>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        const contextId = chat._controller.state.currentContextId;
        chat._controller.applyRuntimeVerb('task_started', {
            task_id: 'task-bp-1',
            context_id: contextId,
        });
        chat._controller.applyRuntimeVerb('breakpoint', {
            task_id: 'task-bp-1',
            context_id: contextId,
            breakpoint: { node_id: 'build_search_query' },
        });
        await elementUpdated(el);

        expect(hits.length).to.equal(1);
        expect(hits[0].node_id).to.equal('build_search_query');
        expect(hits[0].task_id).to.equal('task-bp-1');
    });

    it('resume после breakpoint снимает canvas hit-анимацию', async () => {
        const bus = bootstrapExecutionPanelBus();
        const clears = [];
        bus.subscribeType('flows/breakpoint/clear', () => clears.push(true));

        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'base'}></flows-execution-panel>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        const contextId = chat._controller.state.currentContextId;
        chat._controller.applyRuntimeVerb('task_started', {
            task_id: 'task-bp-resume',
            context_id: contextId,
        });
        chat._controller.applyRuntimeVerb('breakpoint', {
            task_id: 'task-bp-resume',
            context_id: contextId,
            breakpoint: { node_id: 'main' },
        });
        await elementUpdated(el);

        bus.dispatch('flows/breakpoint/hit', { node_id: 'main', task_id: 'task-bp-resume' });
        expect(el._editor.state.breakpointHitNodeId).to.equal('main');

        chat._controller._sending = true;
        el._syncCanvasBreakpointHit();
        expect(clears.length).to.equal(1);
        expect(el._editor.state.breakpointHitNodeId).to.equal(null);
    });

    it('view-breakpoint-state открывает flows.state по sessionId', async () => {
        bootstrapExecutionPanelBus();
        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'base'}></flows-execution-panel>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        const contextId = chat._controller.state.currentContextId;
        let opened = null;
        el.openModal = (kind, props) => {
            opened = { kind, props };
        };

        chat.dispatchEvent(new CustomEvent('view-breakpoint-state', {
            detail: { breakpoint: { node_id: 'node_a', state: { x: 1 } } },
            bubbles: true,
            composed: true,
        }));

        expect(opened).to.not.equal(null);
        expect(opened.kind).to.equal('flows.state');
        expect(opened.props.sessionId).to.equal(`flow-1:${contextId}`);
    });

    it('continue-breakpoint на platform-chat вызывает sendResume', async () => {
        bootstrapExecutionPanelBus();
        const el = await fixture(html`
            <flows-execution-panel .flowId=${'flow-1'} .branchId=${'base'}></flows-execution-panel>
        `);
        await elementUpdated(el);

        const chat = el.shadowRoot.querySelector('platform-chat');
        const contextId = chat._controller.state.currentContextId;
        chat._controller.applyRuntimeVerb('task_started', {
            task_id: 'task-bp-2',
            context_id: contextId,
        });
        chat._controller.applyRuntimeVerb('breakpoint', {
            task_id: 'task-bp-2',
            context_id: contextId,
            breakpoint: { node_id: 'node_a' },
        });

        let resumeCalled = false;
        chat._controller.sendResume = async () => {
            resumeCalled = true;
        };
        chat._streamTtsAllowed = () => false;

        await chat._sendResumeTurn();
        expect(resumeCalled).to.equal(true);
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
