/**
 * Smoke-набор для всех 9 node-editors (llm/code/channel/hitl/external_api/
 * mcp/flow/remote_flow/base) + базовых полей идентификации (rename/delete).
 *
 * Цель: проверить рендер top-level полей `NodeConfig` и эмит правильных
 * патчей по верному backend-контракту.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, aTimeout, waitUntil, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { installFetchMock } from '../helpers/fake-fetch.js';
import { registerFactory, collectFactories } from '@platform/lib/events/index.js';

import { editorResource, editorBulkDeleteOp } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { resourcesBundleResource, resourceUpdateOp } from '../../../../apps/flows/ui/events/resources/resources-bundle.resource.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
import { platformVoiceDictationOp } from '@platform/lib/events/factories/platform-voice-dictation.js';
import { flowValidateOp, flowsResource } from '../../../../apps/flows/ui/events/resources/flows.resource.js';
import { modelsListOp } from '../../../../apps/flows/ui/events/resources/models.resource.js';
import { providersListOp } from '../../../../apps/flows/ui/events/resources/providers.resource.js';
import {
    codeCompletionsOp, codeDocumentationOp, codeTemplatesOp,
    codeEditorStateOp, codeSourceOp, codeFlowFunctionsOp,
    codeToolSourceOp, codeParseSignatureOp, codeValidateOp, codeExecuteOp,
} from '../../../../apps/flows/ui/events/resources/code.resource.js';
import { mcpServersResource, mcpServerSyncOp, mcpServerUpdateOp, mcpServerTestOp } from '../../../../apps/flows/ui/events/resources/mcp.resource.js';
import { promptRenderOp } from '../../../../apps/flows/ui/events/resources/prompts.resource.js';
import { secretsVariablesResource } from '@platform/lib/events/resources/secrets-variables.resource.js';
import { toolsResource } from '../../../../apps/flows/ui/events/resources/tools.resource.js';
import {
    agentSkillsResource,
} from '../../../../apps/flows/ui/events/resources/agent-skills.resource.js';
import { llmContextResolveParentOp } from '../../../../apps/flows/ui/events/resources/llm-context.resource.js';
import { exceptionAbsorbAllowNamesOp, executionLimitsOp } from '../../../../apps/flows/ui/events/resources/metadata.resource.js';
import { workQueuesResource } from '../../../../apps/flows/ui/events/resources/work-queues.resource.js';

import '../../../../apps/flows/ui/components/nodes/flows-base-node-editor.js';
import '../../../../apps/flows/ui/components/nodes/flows-llm-node-editor.js';
import '../../../../apps/flows/ui/components/nodes/flows-code-node-editor.js';
import '../../../../apps/flows/ui/components/nodes/flows-channel-node-editor.js';
import '../../../../apps/flows/ui/components/nodes/flows-hitl-node-editor.js';
import '../../../../apps/flows/ui/components/nodes/flows-external-api-editor.js';
import '../../../../apps/flows/ui/components/nodes/flows-mcp-node-editor.js';
import '../../../../apps/flows/ui/components/nodes/flows-flow-node-editor.js';
import '../../../../apps/flows/ui/components/nodes/flows-remote-flow-editor.js';

const FACTORIES = [
    editorResource, editorBulkDeleteOp,
    resourcesBundleResource, resourceUpdateOp,
    platformFileCreateOp,
    platformVoiceDictationOp,
    flowValidateOp, flowsResource,
    modelsListOp,
    providersListOp,
    codeCompletionsOp, codeDocumentationOp, codeTemplatesOp, codeEditorStateOp,
    codeSourceOp, codeFlowFunctionsOp, codeToolSourceOp, codeParseSignatureOp,
    codeValidateOp, codeExecuteOp,
    mcpServersResource, mcpServerSyncOp, mcpServerUpdateOp, mcpServerTestOp,
    promptRenderOp,
    secretsVariablesResource,
    toolsResource,
    agentSkillsResource,
    llmContextResolveParentOp,
    exceptionAbsorbAllowNamesOp,
    executionLimitsOp,
    workQueuesResource,
];

function bootstrap() {
    for (const f of FACTORIES) registerFactory(f);
    const collected = collectFactories(FACTORIES);
    const effects = collected.effects.filter((effect) => (
        effect.__factoryName === 'flows/code_validate'
        || effect.__factoryName === 'flows/code_editor_state'
        || effect.__factoryName === 'flows/work_queues'
    ));
    return bootstrapTestBus({ slices: collected.slices, effects });
}

function segmentedSegments(control) {
    return [...control.shadowRoot.querySelectorAll('.segment')];
}

function settingsSegmentedControl(baseEditor, selector = 'platform-segmented-control') {
    return settingsQuery(baseEditor, selector);
}

function settingsQuery(baseEditor, selector) {
    const settingsSlot = baseEditor.shadowRoot.querySelector('slot[name="settings"]');
    const assigned = settingsSlot.assignedElements({ flatten: true });
    for (const root of assigned) {
        if (root.matches && root.matches(selector)) {
            return root;
        }
        const nested = root.querySelector ? root.querySelector(selector) : null;
        if (nested) {
            return nested;
        }
    }
    return null;
}

function codeEditorToolbarControls(workbench) {
    const codeEditor = workbench.shadowRoot.querySelector('flows-code-editor');
    return codeEditor ? [...codeEditor.querySelectorAll('platform-segmented-control')] : [];
}

describe('node editors — top-level NodeConfig contract', () => {
    let fetchMock;
    beforeEach(() => {
        resetPlatformState();
        bootstrap();
        fetchMock = installFetchMock();
        fetchMock.respondJson('POST', (url) => url.endsWith('/flows/api/v1/code/validate'), { valid: true, warnings: [] });
        fetchMock.respondJson('GET', (url) => url.includes('/flows/api/v1/code/editor-state'), { variables: {} });
        fetchMock.respondJson('GET', (url) => /\/flows\/api\/v1\/agent-skills(\?|$)/.test(url), {
            items: [],
            total: 0,
            limit: 200,
            offset: 0,
        });
        fetchMock.respondJson('GET', (url) => /\/flows\/api\/v1\/work-queues(\?|$)/.test(url), {
            items: [
                {
                    work_queue_id: 'wq_support',
                    work_queue_slug: 'support',
                    name: 'Support',
                    description: null,
                },
            ],
            total: 1,
            limit: 200,
            offset: 0,
        });
    });
    afterEach(() => {
        fetchMock.uninstall();
        fixtureCleanup();
    });

    it('flows-llm-node-editor рендерит секции', async () => {
        const node = { node_id: 'a', type: 'llm_node', name: 'A', prompt: 'hi', tools: [] };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        expect(base).to.not.be.null;
        const blocks = base.querySelectorAll('section.block');
        expect(blocks.length).to.be.greaterThanOrEqual(6);
        expect(base.querySelector('platform-llm-context-editor')).to.not.be.null;
        const detailsLeftover = base.querySelectorAll('details');
        expect(detailsLeftover.length).to.equal(0);
    });

    it('flows-llm-node-editor structured_output скрывает react секцию', async () => {
        const node = { node_id: 'a', type: 'llm_node', name: 'A', structured_output: true };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const titles = Array.from(base.querySelectorAll('section.block .block-title')).map((s) => s.textContent);
        expect(titles.length).to.be.lessThanOrEqual(7);
        expect(titles.some((title) => title.includes('section_react') || title.includes('ReAct'))).to.equal(false);
        expect(base.querySelector('platform-llm-context-editor')).to.not.be.null;
    });

    it('flows-llm-node-editor structured_output скрывает Skills секцию', async () => {
        const node = {
            node_id: 'a',
            type: 'llm_node',
            name: 'A',
            structured_output: true,
            agent_skills: ['networkle'],
        };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const titles = Array.from(base.querySelectorAll('section.block .block-title')).map((s) => s.textContent);
        expect(titles.some((title) => title.includes('Skills') || title.includes('section_agent_skills'))).to.equal(false);
        expect(base.querySelector('.chip')).to.be.null;
    });

    it('flows-base-node-editor очищает llm_context_resource_key при удалении context resource', async () => {
        const node = {
            node_id: 'a',
            type: 'llm_node',
            name: 'A',
            resources: { ctx: { resource_id: 'ctx' } },
            llm_context_resource_key: 'ctx',
        };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);

        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        base._onRemoveResource('ctx');

        expect(last.patch.resources).to.deep.equal({});
        expect(last.patch.llm_context_resource_key).to.equal(null);
    });

    it('flows-code-node-editor — вкладки Код / Схема', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A', code: 'print(1)' };
        const el = await fixture(html`
            <flows-code-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'}>
            </flows-code-node-editor>
        `);
        await elementUpdated(el);
        const workbench = el.shadowRoot.querySelector('flows-code-workbench');
        expect(workbench).to.not.be.null;
        await elementUpdated(workbench);
        const [mainTabs] = codeEditorToolbarControls(workbench);
        expect(mainTabs).to.not.be.undefined;
        const tabs = segmentedSegments(mainTabs);
        expect(tabs.length).to.be.greaterThanOrEqual(2);
        tabs[1].click();
        await elementUpdated(workbench);
        await elementUpdated(el);
        const schemaEditor = workbench.shadowRoot.querySelector('platform-schema-editor');
        expect(schemaEditor).to.not.be.null;
    });

    it('flows-code-node-editor — round-trip Код → Схема → Код сохраняет code', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A', code: 'print(1)' };
        const el = await fixture(html`
            <flows-code-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'}>
            </flows-code-node-editor>
        `);
        await elementUpdated(el);
        const workbench = el.shadowRoot.querySelector('flows-code-workbench');
        await elementUpdated(workbench);

        const patches = [];
        el.addEventListener('change', (e) => { patches.push(e.detail); });

        const [mainTabs] = codeEditorToolbarControls(workbench);
        const tabs = segmentedSegments(mainTabs);
        tabs[1].click();
        await elementUpdated(workbench);
        await elementUpdated(el);

        tabs[0].click();
        await elementUpdated(workbench);
        await elementUpdated(el);

        const codePatches = patches
            .map((detail) => detail.patch)
            .filter((patch) => patch && typeof patch.code === 'string');
        for (const patch of codePatches) {
            expect(patch.code).to.not.equal('secondary');
        }

        const pyEditor = workbench.shadowRoot.querySelector('flows-code-editor[language="python"]');
        expect(pyEditor).to.not.be.null;
        await elementUpdated(pyEditor);
        expect(pyEditor.value).to.equal('print(1)');
    });

    it('flows-code-node-editor — переключение языка кода эмитит language patch', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A', code: '' };
        const el = await fixture(html`
            <flows-code-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'}>
            </flows-code-node-editor>
        `);
        await elementUpdated(el);
        const workbench = el.shadowRoot.querySelector('flows-code-workbench');
        await elementUpdated(workbench);
        const langSegment = workbench.shadowRoot.querySelector('flows-code-language-segment');
        expect(langSegment).to.not.be.null;
        await elementUpdated(langSegment);
        const langControl = langSegment.shadowRoot.querySelector('platform-segmented-control');
        expect(langControl).to.not.be.null;
        await elementUpdated(langControl);
        const buttons = segmentedSegments(langControl);
        expect(buttons.length).to.equal(5);
        const tsButton = buttons.find((button) => button.getAttribute('aria-label') === 'TypeScript');
        expect(tsButton).to.not.be.undefined;
        expect(tsButton.querySelector('img.segment-icon-img')).to.not.be.null;
        setTimeout(() => tsButton.click());
        const changeEv = await oneEvent(el, 'change');
        expect(changeEv.detail.patch).to.have.property('language', 'typescript');
        expect(changeEv.detail.patch.code).to.include('async function run');
        expect(changeEv.detail.patch).to.have.property('tool_id', null);
    });

    it('flows-llm-node-editor — выбранный code tool сохраняет language для иконки на ноде', async () => {
        const node = { node_id: 'a', type: 'llm_node', name: 'A', prompt: 'hi', tools: [] };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        el.openModal = (kind, props) => {
            expect(kind).to.equal('flows.tool_picker');
            props.onPick({
                kind: 'tool',
                tool_id: 'ts_tool',
                item: {
                    tool_id: 'ts_tool',
                    language: 'typescript',
                    code: 'async function run(args, state) { return {}; }',
                },
            });
        };

        el._onPickTool();

        expect(last.patch.tools).to.deep.equal([{ tool_id: 'ts_tool', language: 'typescript' }]);
    });

    it('flows-llm-node-editor — flow из picker сохраняется как полный typed reference', async () => {
        const node = { node_id: 'a', type: 'llm_node', name: 'A', prompt: 'hi', tools: [] };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        el.openModal = (kind, props) => {
            expect(kind).to.equal('flows.tool_picker');
            props.onPick({
                kind: 'flow',
                tool_id: 'fitness_coach',
                item: {
                    tool_id: 'fitness_coach',
                    title: 'Фитнес-тренер',
                    description: 'Строит план тренировок',
                    parameters_schema: {
                        type: 'object',
                        properties: { request: { type: 'string' } },
                        required: ['request'],
                        additionalProperties: false,
                    },
                },
            });
        };

        el._onPickTool();

        expect(last.patch).to.not.have.property('call_type');
        expect(last.patch.tools).to.deep.equal([{
            tool_id: 'fitness_coach',
            type: 'flow',
            flow_id: 'fitness_coach',
            branch_id: 'default',
            call_type: 'call',
            name: 'Фитнес-тренер',
            description: 'Строит план тренировок',
            parameters_schema: {
                type: 'object',
                properties: { request: { type: 'string' } },
                required: ['request'],
                additionalProperties: false,
            },
        }]);
    });

    it('flows-llm-node-editor — Call/Handoff меняется только на выбранном flow chip', async () => {
        const flowTool = {
            tool_id: 'fitness_coach',
            type: 'flow',
            flow_id: 'fitness_coach',
            branch_id: 'default',
            call_type: 'call',
            name: 'Фитнес-тренер',
            description: '',
            parameters_schema: { type: 'object', properties: {}, required: [] },
        };
        const codeTool = { tool_id: 'calculator' };
        const node = {
            node_id: 'a',
            type: 'llm_node',
            name: 'A',
            prompt: 'hi',
            tools: [flowTool, codeTool],
        };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const modeButton = base.querySelector('.chip-call-type');
        expect(modeButton).to.not.be.null;
        expect(modeButton.dataset.callType).to.equal('call');
        await modeButton.updateComplete;
        const chips = [...base.querySelectorAll('.chip')];
        expect(chips.length).to.equal(2);
        const flowChipHeight = chips[0].getBoundingClientRect().height;
        const codeChipHeight = chips[1].getBoundingClientRect().height;
        const innerModeButton = modeButton.shadowRoot.querySelector('button');
        expect(Math.abs(flowChipHeight - codeChipHeight)).to.be.at.most(2);
        expect(innerModeButton.getBoundingClientRect().height).to.be.at.most(22);

        setTimeout(() => modeButton.click());
        const changeEv = await oneEvent(el, 'change');

        expect(changeEv.detail.patch).to.not.have.property('call_type');
        expect(changeEv.detail.patch.tools[0]).to.deep.equal({ ...flowTool, call_type: 'handoff' });
        expect(changeEv.detail.patch.tools[1]).to.equal(codeTool);
    });

    it('flows-llm-node-editor — клик по skill chip открывает flows.agent_skill_edit', async () => {
        const node = {
            node_id: 'a',
            type: 'llm_node',
            name: 'A',
            prompt: 'hi',
            tools: [],
            agent_skills: ['networkle'],
        };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        let opened = null;
        el.openModal = (kind, props) => {
            opened = { kind, props };
        };
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const skillChip = [...base.querySelectorAll('.chip')].find((chip) =>
            chip.textContent.includes('networkle'),
        );
        expect(skillChip).to.not.be.undefined;
        skillChip.click();
        expect(opened).to.not.be.null;
        expect(opened.kind).to.equal('flows.agent_skill_edit');
        expect(opened.props.agentSkillId).to.equal('networkle');
        expect(typeof opened.props.onDuplicated).to.equal('function');

        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        opened.props.onDuplicated({ fromId: 'networkle', toId: 'networkle-copy' });
        expect(last.patch.agent_skills).to.deep.equal(['networkle-copy']);
    });

    it('flows-llm-node-editor — выбранный MCP tool сохраняет server/tool metadata', async () => {
        const node = { node_id: 'a', type: 'llm_node', name: 'A', prompt: 'hi', tools: [] };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        el.openModal = (kind, props) => {
            expect(kind).to.equal('flows.tool_picker');
            props.onPick({
                kind: 'tool',
                tool_id: 'mcp:browser:browser_create_session',
                item: {
                    tool_id: 'mcp:browser:browser_create_session',
                    item_type: 'tool',
                    code_mode: 'mcp_tool',
                    mcp_server_id: 'browser',
                    mcp_tool_name: 'browser_create_session',
                },
            });
        };

        el._onPickTool();

        expect(last.patch.tools).to.deep.equal([{
            tool_id: 'mcp:browser:browser_create_session',
            type: 'mcp',
            code_mode: 'mcp_tool',
            mcp_server_id: 'browser',
            mcp_tool_name: 'browser_create_session',
        }]);
    });

    it('flows-code-workbench — прокидывает выбранный язык в completionContext', async () => {
        const workbench = await fixture(html`
            <flows-code-workbench
                .variant=${'node'}
                .language=${'go'}
                .code=${''}
                .documentationPerspective=${'node'}
            ></flows-code-workbench>
        `);
        await elementUpdated(workbench);
        let editor = workbench.shadowRoot.querySelector('flows-code-editor');
        expect(editor).to.not.be.null;
        expect(editor.completionContext).to.deep.include({
            language: 'go',
            perspective: 'node',
            include_runtime_namespace_extras: true,
        });

        workbench.language = 'csharp';
        await elementUpdated(workbench);
        editor = workbench.shadowRoot.querySelector('flows-code-editor');
        expect(editor.completionContext).to.deep.include({
            language: 'csharp',
            perspective: 'node',
            include_runtime_namespace_extras: true,
        });
    });

    it('flows-code-workbench — debounce-валидация отправляет language и kind', async () => {
        const workbench = await fixture(html`
            <flows-code-workbench
                .variant=${'resource'}
                .language=${'typescript'}
                .code=${'async function run(args, state) { return {}; }'}
                .completionFlowId=${'flow-a'}
                .completionBranchId=${'draft'}
            ></flows-code-workbench>
        `);
        await elementUpdated(workbench);
        await aTimeout(720);
        await waitUntil(
            () => fetchMock.calls.some((call) => call.method === 'POST' && call.url.endsWith('/flows/api/v1/code/validate')),
            'code validation request',
        );
        const call = fetchMock.calls.find((item) => item.method === 'POST' && item.url.endsWith('/flows/api/v1/code/validate'));
        const body = JSON.parse(call.init.body);
        expect(body).to.deep.include({
            language: 'typescript',
            kind: 'tool',
            node_type: 'tool',
            flow_id: 'flow-a',
            branch_id: 'draft',
        });
        const status = workbench.shadowRoot.querySelector('.code-validation-status[data-state="valid"]');
        expect(status).to.not.be.null;
    });

    it('flows-channel-node-editor — поля channel/action', async () => {
        const node = { node_id: 'a', type: 'channel', name: 'A', channel: 'telegram', action: 'send_message', channel_config: {} };
        const el = await fixture(html`
            <flows-channel-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'channel'}>
            </flows-channel-node-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && Object.prototype.hasOwnProperty.call(e.detail, 'patch')) {
                last = e.detail;
            }
        });
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const channelPf = base.querySelector('.grid platform-field[data-field="channel"]');
        expect(channelPf, 'channel enum field').to.not.be.null;
        const pfEnum = channelPf.shadowRoot.querySelector('platform-field-enum');
        expect(pfEnum, 'channel platform-field-enum').to.not.be.null;
        const inp = pfEnum.shadowRoot.querySelector('input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(pfEnum);
        const webhookRow = pfEnum.shadowRoot.querySelector('[data-enum-value="webhook"]');
        expect(webhookRow, 'webhook enum row').to.not.be.null;
        webhookRow.click();
        expect(last, 'editor change event').to.exist;
        expect(last.patch).to.have.property('channel', 'webhook');
        expect(last.patch).to.have.property('channel_config').that.deep.equals({});

        const actionPf = base.querySelector('.grid platform-field[data-field="action"]');
        expect(actionPf, 'action enum field').to.not.be.null;
        expect(actionPf.getAttribute('type')).to.equal('enum');
        const actionEnum = actionPf.shadowRoot.querySelector('platform-field-enum');
        expect(actionEnum, 'action platform-field-enum').to.not.be.null;
    });

    it('flows-channel-node-editor — email facade пишет input_mapping.recipient', async () => {
        const node = {
            node_id: 'a',
            type: 'channel',
            name: 'A',
            channel: 'email',
            action: 'send_message',
            channel_config: { delivery: 'mailbox', mailbox_binding_id: 'mailbind_1' },
            input_mapping: { recipient: '', subject: '', text: '' },
        };
        const el = await fixture(html`
            <flows-channel-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'channel'}>
            </flows-channel-node-editor>
        `);
        await elementUpdated(el);
        el._mailSelect = {
            value: {
                connection: { company_id: 'c1' },
                bindings: [
                    {
                        mailbox_binding_id: 'mailbind_1',
                        email_address: 'me@example.com',
                        is_default: true,
                    },
                ],
            },
        };
        el.requestUpdate();
        await elementUpdated(el);

        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && Object.prototype.hasOwnProperty.call(e.detail, 'patch')) {
                last = e.detail;
            }
        });

        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const actionPf = base.querySelector('.grid platform-field[data-field="action"]');
        expect(actionPf, 'action enum').to.not.be.null;
        const actionEnum = actionPf.shadowRoot.querySelector('platform-field-enum');
        const actionOpts = [...actionEnum.shadowRoot.querySelectorAll('[data-enum-value]')].map(
            (n) => n.getAttribute('data-enum-value'),
        );
        const actionInp = actionEnum.shadowRoot.querySelector('input.field-pill-enum-input');
        actionInp.focus();
        await elementUpdated(actionEnum);
        const openedOpts = [...actionEnum.shadowRoot.querySelectorAll('[data-enum-value]')].map(
            (n) => n.getAttribute('data-enum-value'),
        );
        const realActions = (openedOpts.length ? openedOpts : actionOpts).filter((v) => v !== '');
        expect(realActions).to.deep.equal(['send_message']);

        const deliveryPf = base.querySelector('platform-field[data-field="delivery"]');
        expect(deliveryPf, 'delivery enum').to.not.be.null;

        const toInput = base.querySelector('platform-variable-input[data-field="recipient"]');
        expect(toInput, 'to variable input').to.not.be.null;
        toInput.value = 'user@example.com';
        toInput.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'user@example.com' },
            bubbles: true,
            composed: true,
        }));
        expect(last, 'mapping patch').to.exist;
        expect(last.patch.input_mapping).to.have.property('recipient', 'user@example.com');

        last = null;
        const bodyEditor = base.querySelector('platform-markdown-editor[data-field="text"]');
        expect(bodyEditor, 'message body markdown editor').to.not.be.null;
        bodyEditor.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'Hello @state:response' },
            bubbles: true,
            composed: true,
        }));
        expect(last, 'body patch').to.exist;
        expect(last.patch.input_mapping).to.have.property('text', 'Hello @state:response');
    });

    it('flows-channel-node-editor — telegram message body через markdown-editor', async () => {
        const node = {
            node_id: 'a',
            type: 'channel',
            name: 'A',
            channel: 'telegram',
            action: 'send_message',
            channel_config: { bot_token: '@var:tg_token' },
            input_mapping: { recipient: '', text: '' },
        };
        const el = await fixture(html`
            <flows-channel-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'channel'}
                .flowVariables=${{ chat_id: { value: '1', type: 'string' } }}>
            </flows-channel-node-editor>
        `);
        await elementUpdated(el);

        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && Object.prototype.hasOwnProperty.call(e.detail, 'patch')) {
                last = e.detail;
            }
        });

        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const toInput = base.querySelector('platform-variable-input[data-field="recipient"]');
        expect(toInput, 'telegram recipient').to.not.be.null;
        toInput.dispatchEvent(new CustomEvent('change', {
            detail: { value: '@state:variables.chat_id' },
            bubbles: true,
            composed: true,
        }));
        expect(last.patch.input_mapping.recipient).to.equal('@state:variables.chat_id');

        last = null;
        const bodyEditor = base.querySelector('platform-markdown-editor[data-field="text"]');
        expect(bodyEditor, 'telegram body editor').to.not.be.null;
        expect(bodyEditor.enableVariables).to.equal(true);
        bodyEditor.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'Привет {user_name}' },
            bubbles: true,
            composed: true,
        }));
        expect(last, 'telegram body patch').to.exist;
        expect(last.patch.input_mapping).to.have.property('text', 'Привет {user_name}');
    });

    it('flows-channel-node-editor — email delivery smtp пишет channel_config', async () => {
        const node = {
            node_id: 'a',
            type: 'channel',
            name: 'A',
            channel: 'email',
            action: 'send_message',
            channel_config: { delivery: 'mailbox', mailbox_binding_id: 'mailbind_1' },
            input_mapping: { recipient: '', subject: '', text: '' },
        };
        const el = await fixture(html`
            <flows-channel-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'channel'}>
            </flows-channel-node-editor>
        `);
        await elementUpdated(el);
        el._mailSelect = {
            value: {
                connection: { company_id: 'c1' },
                bindings: [
                    {
                        mailbox_binding_id: 'mailbind_1',
                        email_address: 'me@example.com',
                        is_default: true,
                    },
                ],
            },
        };
        el.requestUpdate();
        await elementUpdated(el);

        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && Object.prototype.hasOwnProperty.call(e.detail, 'patch')) {
                last = e.detail;
            }
        });

        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const deliveryPf = base.querySelector('platform-field[data-field="delivery"]');
        expect(deliveryPf, 'delivery enum').to.not.be.null;
        deliveryPf.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'smtp' },
            bubbles: true,
            composed: true,
        }));
        expect(last, 'delivery patch').to.exist;
        expect(last.patch.channel_config).to.include({
            delivery: 'smtp',
            smtp_port: 587,
            smtp_use_tls: true,
        });
        expect(last.patch.channel_config).to.not.have.property('mailbox_binding_id');

        el.nodeConfig = {
            ...node,
            channel_config: last.patch.channel_config,
        };
        el.requestUpdate();
        await elementUpdated(el);

        last = null;
        const passwordInput = base.querySelector('platform-variable-input[data-field="password"]');
        expect(passwordInput, 'smtp password input').to.not.be.null;
        passwordInput.dispatchEvent(new CustomEvent('change', {
            detail: { value: '@var:smtp_password' },
            bubbles: true,
            composed: true,
        }));
        expect(last, 'password patch').to.exist;
        expect(last.patch.channel_config).to.include({
            delivery: 'smtp',
            password: '@var:smtp_password',
        });
    });

    it('flows-hitl-node-editor — work_queue_slug устанавливается', async () => {
        const node = { node_id: 'a', type: 'hitl_node', name: 'A' };
        const el = await fixture(html`
            <flows-hitl-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'hitl_node'} .flowVariables=${{}}>
            </flows-hitl-node-editor>
        `);
        await elementUpdated(el);
        await waitUntil(() => Array.isArray(el._queues.items) && el._queues.items.length > 0);
        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && Object.prototype.hasOwnProperty.call(e.detail, 'patch')) {
                last = e.detail;
            }
        });
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const combobox = base.querySelector('platform-searchable-combobox');
        expect(combobox, 'queue combobox').to.exist;
        expect(combobox.createLabel, 'createLabel for on-the-fly create').to.be.a('string').and.not.empty;
        combobox.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'support' },
            bubbles: true,
            composed: true,
        }));
        expect(last, 'editor change event').to.exist;
        expect(last.patch).to.deep.equal({ work_queue_slug: 'support' });

        const titleInput = base.querySelector('platform-variable-input[data-field="handoff_task_title"]');
        expect(titleInput, 'task title variable input').to.exist;
        const md = base.querySelector('platform-markdown-editor');
        expect(md, 'user message markdown').to.exist;
        expect(md.enableVariables, 'enableVariables').to.equal(true);
        expect(md.variableSyntax, 'variableSyntax at-ref').to.equal('at-ref');
        expect(md.hint, 'user message hint').to.be.a('string').and.not.empty;
    });

    it('flows-hitl-node-editor — create из combobox открывает форму при пустом query', async () => {
        const node = { node_id: 'a', type: 'hitl_node', name: 'A' };
        const el = await fixture(html`
            <flows-hitl-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'hitl_node'} .flowVariables=${{}}>
            </flows-hitl-node-editor>
        `);
        await elementUpdated(el);
        expect(el._showCreate).to.equal(false);
        el._onQueueCreate({ detail: { query: '' } });
        expect(el._showCreate).to.equal(true);
    });

    it('flows-external-api-editor — смена HTTP-метода эмитит patch', async () => {
        const node = { node_id: 'a', type: 'external_api', name: 'API', url: 'https://x', method: 'POST' };
        const el = await fixture(html`
            <flows-external-api-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'external_api'}>
            </flows-external-api-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && Object.prototype.hasOwnProperty.call(e.detail, 'patch')) {
                last = e.detail;
            }
        });
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const methodToggle = base.querySelector('platform-segmented-control');
        expect(methodToggle, 'method segmented control').to.not.be.null;
        expect(
            base.querySelectorAll('.settings-wrap details').length,
            'POST shows body + headers',
        ).to.equal(2);
        const getBtn = methodToggle.shadowRoot.querySelector('button.segment[aria-label="GET"]');
        expect(getBtn, 'GET method segment').to.not.be.null;
        getBtn.click();
        expect(last, 'editor change event').to.exist;
        expect(last.patch).to.deep.equal({ method: 'GET' });
    });

    it('flows-external-api-editor — GET скрывает секцию тела запроса', async () => {
        const node = {
            node_id: 'a',
            type: 'external_api',
            name: 'API',
            url: 'https://x',
            method: 'GET',
            body_template: '{"keep":true}',
        };
        const el = await fixture(html`
            <flows-external-api-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'external_api'}>
            </flows-external-api-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        expect(
            base.querySelectorAll('.settings-wrap details').length,
            'GET shows only headers',
        ).to.equal(1);
        expect(
            base.querySelector('.settings-wrap flows-http-headers-editor'),
            'headers editor',
        ).to.not.be.null;
        expect(
            base.querySelector('.settings-wrap platform-json-editor'),
            'no body json editor on GET',
        ).to.be.null;
    });

    it('flows-external-api-editor — headers editor эмитит patch', async () => {
        const node = {
            node_id: 'a',
            type: 'external_api',
            name: 'API',
            url: 'https://x',
            method: 'GET',
            headers: {},
        };
        const el = await fixture(html`
            <flows-external-api-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'external_api'}>
            </flows-external-api-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && Object.prototype.hasOwnProperty.call(e.detail, 'patch')) {
                last = e.detail;
            }
        });
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const headersEditor = base.querySelector('flows-http-headers-editor');
        expect(headersEditor, 'headers editor').to.not.be.null;
        const addBtn = headersEditor.shadowRoot.querySelector('platform-button.header-pairs-add');
        expect(addBtn, 'add header button').to.not.be.null;
        addBtn.click();
        await elementUpdated(headersEditor);
        const nameInputs = headersEditor.shadowRoot.querySelectorAll('platform-variable-input');
        expect(nameInputs.length, 'header name+value inputs').to.equal(2);
        const nameField = nameInputs[0];
        const valueInput = nameInputs[1];
        nameField.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'Authorization' },
            bubbles: true,
            composed: true,
        }));
        await elementUpdated(headersEditor);
        valueInput.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'Bearer @var:token' },
            bubbles: true,
            composed: true,
        }));
        expect(last, 'editor change event').to.exist;
        expect(last.patch).to.deep.equal({
            headers: { Authorization: 'Bearer @var:token' },
        });
    });

    it('flows-mcp-node-editor — pick tool button opens tool_picker', async () => {
        const node = { node_id: 'a', type: 'mcp', name: 'M' };
        const el = await fixture(html`
            <flows-mcp-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'mcp'}>
            </flows-mcp-node-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const pickBtn = base.querySelector('.mcp-actions platform-button');
        expect(pickBtn, 'pick tool button').to.exist;
        let opened = null;
        el.openModal = (kind, props) => {
            opened = { kind, props };
        };
        pickBtn.click();
        expect(opened).to.exist;
        expect(opened.kind).to.equal('flows.tool_picker');
        expect(opened.props.pickMode).to.equal('mcp_only');
        expect(opened.props.onPick).to.be.a('function');
    });

    it('flows-mcp-node-editor — читает mcp_server_id/mcp_tool_name из ToolReference', async () => {
        const node = {
            node_id: 'mcp:browser:browser_create_session',
            type: 'mcp',
            name: 'MCP tool',
            mcp_server_id: 'browser',
            mcp_tool_name: 'browser_create_session',
        };
        const el = await fixture(html`
            <flows-mcp-node-editor .nodeId=${'mcp:browser:browser_create_session'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'mcp'}>
            </flows-mcp-node-editor>
        `);
        await elementUpdated(el);
        const selection = el.shadowRoot.querySelector('flows-base-node-editor')
            .querySelector('.mcp-selection-meta');
        expect(selection).to.exist;
        expect(selection.textContent.trim()).to.equal('mcp:browser:browser_create_session');
    });

    it('flows-flow-node-editor — toggle ручного ID', async () => {
        const node = { node_id: 'a', type: 'flow', name: 'F', flow_id: 'subflow_x', branch_id: 'default' };
        const el = await fixture(html`
            <flows-flow-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'flow'}>
            </flows-flow-node-editor>
        `);
        await elementUpdated(el);
        const root = el.shadowRoot.querySelector('flows-base-node-editor');
        const modeControl = settingsSegmentedControl(root, 'platform-segmented-control.source-mode');
        expect(modeControl).to.not.be.null;
        expect(segmentedSegments(modeControl).length).to.equal(2);
    });

    it('flows-flow-node-editor — режим Call/Handoff расположен рядом с веткой и эмитит enum', async () => {
        const node = {
            node_id: 'a',
            type: 'flow',
            name: 'F',
            flow_id: 'subflow_x',
            branch_id: 'default',
            call_type: 'call',
        };
        const el = await fixture(html`
            <flows-flow-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'flow'}>
            </flows-flow-node-editor>
        `);
        await elementUpdated(el);
        const root = el.shadowRoot.querySelector('flows-base-node-editor');
        const row = root.querySelector('.branch-mode-row');
        const modeField = row.querySelector('.call-type-field platform-segmented-control');
        expect(modeField).to.not.be.null;
        expect(modeField.value).to.equal('call');
        expect(modeField.items.map((item) => item.value)).to.deep.equal(['call', 'handoff']);
        expect(segmentedSegments(modeField).length).to.equal(2);

        setTimeout(() => modeField.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'handoff' },
            bubbles: true,
            composed: true,
        })));
        const changeEv = await oneEvent(el, 'change');
        expect(changeEv.detail.patch).to.deep.equal({ call_type: 'handoff' });
    });

    it('flows-remote-flow-editor — protocol panel + url clears flow_id', async () => {
        const node = { node_id: 'a', type: 'remote_flow', name: 'R', url: 'https://api/x' };
        const el = await fixture(html`
            <flows-remote-flow-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'remote_flow'}>
            </flows-remote-flow-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        await elementUpdated(base);

        const protocolPanel = settingsQuery(base, '[data-testid="remote-flow-protocol-panel"]');
        expect(protocolPanel).to.not.be.null;
        expect(settingsQuery(base, 'platform-segmented-control.endpoint-mode')).to.be.null;

        const urlField = settingsQuery(base, '.remote-flow-endpoint-stack platform-field');
        expect(urlField).to.not.be.null;
        setTimeout(() => urlField.dispatchEvent(new CustomEvent('change', {
            detail: { value: 'https://partner.example/a2a' },
            bubbles: true,
            composed: true,
        })));
        const changeEv = await oneEvent(el, 'change');
        expect(changeEv.detail.patch).to.deep.equal({
            url: 'https://partner.example/a2a',
            flow_id: null,
        });
    });

    it('flows-remote-flow-editor — metadata_template json editor', async () => {
        const node = { node_id: 'a', type: 'remote_flow', name: 'R', url: 'https://api/x' };
        const el = await fixture(html`
            <flows-remote-flow-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'remote_flow'}>
            </flows-remote-flow-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        await elementUpdated(base);

        const metaBlock = settingsQuery(base, '[data-testid="remote-flow-metadata"]');
        expect(metaBlock).to.not.be.null;
        const jsonEditor = settingsQuery(base, '[data-testid="remote-flow-metadata"] platform-json-editor');
        expect(jsonEditor).to.not.be.null;
        setTimeout(() => jsonEditor.dispatchEvent(new CustomEvent('change', {
            detail: { parsed: { variables: { order_id: '@state:order.id' } } },
            bubbles: true,
            composed: true,
        })));
        const changeEv = await oneEvent(el, 'change');
        expect(changeEv.detail.patch).to.have.property('metadata_template');
        expect(JSON.parse(changeEv.detail.patch.metadata_template)).to.deep.equal({
            variables: { order_id: '@state:order.id' },
        });
    });

    it('flows-base-node-editor — id ноды только для чтения (rename отключён)', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A' };
        const el = await fixture(html`
            <flows-base-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'}>
            </flows-base-node-editor>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.node-id-rename-input')).to.be.null;
        expect(el.shadowRoot.querySelector('.icon-btn')).to.be.null;
    });

    it('flows-base-node-editor — master-detail layout', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A' };
        const el = await fixture(html`
            <flows-base-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'}>
            </flows-base-node-editor>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.panel-layout')).to.not.be.null;
        expect(el.shadowRoot.querySelector('.panel-sidebar')).to.not.be.null;
        expect(el.shadowRoot.querySelector('.panel-main')).to.not.be.null;
    });
});
