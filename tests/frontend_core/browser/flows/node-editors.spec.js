/**
 * Smoke-набор для всех 9 node-editors (llm/code/channel/hitl/external_api/
 * mcp/flow/remote_flow/base) + базовых полей идентификации (rename/delete).
 *
 * Цель: проверить рендер top-level полей `NodeConfig` и эмит правильных
 * патчей по верному backend-контракту.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { installFetchMock } from '../helpers/fake-fetch.js';
import { registerFactory, collectFactories } from '@platform/lib/events/index.js';

import { editorResource, editorBulkDeleteOp } from '../../../../apps/flows/ui/events/resources/editor.resource.js';
import { resourcesBundleResource, resourceUpdateOp } from '../../../../apps/flows/ui/events/resources/resources-bundle.resource.js';
import { fileUploadOp } from '../../../../apps/flows/ui/events/resources/files.resource.js';
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
import { variablesResource } from '../../../../apps/flows/ui/events/resources/variables.resource.js';
import { toolsResource } from '../../../../apps/flows/ui/events/resources/tools.resource.js';
import { exceptionAbsorbAllowNamesOp, executionLimitsOp } from '../../../../apps/flows/ui/events/resources/metadata.resource.js';

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
    fileUploadOp,
    flowValidateOp, flowsResource,
    modelsListOp,
    providersListOp,
    codeCompletionsOp, codeDocumentationOp, codeTemplatesOp, codeEditorStateOp,
    codeSourceOp, codeFlowFunctionsOp, codeToolSourceOp, codeParseSignatureOp,
    codeValidateOp, codeExecuteOp,
    mcpServersResource, mcpServerSyncOp, mcpServerUpdateOp, mcpServerTestOp,
    promptRenderOp,
    variablesResource,
    toolsResource,
    exceptionAbsorbAllowNamesOp,
    executionLimitsOp,
];

function bootstrap() {
    for (const f of FACTORIES) registerFactory(f);
    const collected = collectFactories(FACTORIES);
    const effects = collected.effects.filter((effect) => (
        effect.__factoryName === 'flows/code_validate'
        || effect.__factoryName === 'flows/code_editor_state'
    ));
    return bootstrapTestBus({ slices: collected.slices, effects });
}

describe('node editors — top-level NodeConfig contract', () => {
    let fetchMock;
    beforeEach(() => {
        resetPlatformState();
        bootstrap();
        fetchMock = installFetchMock();
        fetchMock.respondJson('POST', (url) => url.endsWith('/flows/api/v1/code/validate'), { valid: true, warnings: [] });
        fetchMock.respondJson('GET', (url) => url.includes('/flows/api/v1/code/editor-state'), { variables: {} });
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
        expect(titles.length).to.be.lessThanOrEqual(6);
        expect(titles.some((title) => title.includes('section_react') || title.includes('ReAct'))).to.equal(false);
        expect(base.querySelector('platform-llm-context-editor')).to.not.be.null;
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
        const tabs = workbench.shadowRoot.querySelectorAll('.main-tab');
        expect(tabs.length).to.be.greaterThanOrEqual(2);
        tabs[1].click();
        await elementUpdated(workbench);
        await elementUpdated(el);
        const jsonEditor = workbench.shadowRoot.querySelector('flows-code-editor[language="json"]');
        expect(jsonEditor).to.not.be.null;
    });

    it('flows-code-node-editor — переключение языка кода эмитит language patch', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A', code: '' };
        const el = await fixture(html`
            <flows-code-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'}>
            </flows-code-node-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const workbench = el.shadowRoot.querySelector('flows-code-workbench');
        await elementUpdated(workbench);
        const buttons = Array.from(workbench.shadowRoot.querySelectorAll('.language-button'));
        expect(buttons.length).to.equal(5);
        const tsButton = buttons.find((button) => button.getAttribute('aria-label') === 'TypeScript');
        expect(tsButton).to.not.be.undefined;
        expect(tsButton.querySelector('flows-code-language-icon[language="typescript"]')).to.not.be.null;
        tsButton.click();
        await elementUpdated(workbench);
        expect(last.patch).to.have.property('language', 'typescript');
        expect(last.patch.code).to.include('async function run');
        expect(last.patch).to.have.property('tool_id', null);
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
        const channelPf = base.querySelector('.grid platform-field[type="enum"]');
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
    });

    it('flows-hitl-node-editor — work_queue_slug устанавливается', async () => {
        const node = { node_id: 'a', type: 'hitl_node', name: 'A' };
        const el = await fixture(html`
            <flows-hitl-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'hitl_node'} .flowVariables=${{}}>
            </flows-hitl-node-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => {
            if (e.detail && Object.prototype.hasOwnProperty.call(e.detail, 'patch')) {
                last = e.detail;
            }
        });
        el._onQueueSlug({ detail: { value: 'support' } });
        expect(last, 'editor change event').to.exist;
        expect(last.patch).to.deep.equal({ work_queue_slug: 'support' });
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
        const methodPf = base.querySelector('.grid platform-field[type="enum"]');
        expect(methodPf, 'method enum field').to.not.be.null;
        const pfEnum = methodPf.shadowRoot.querySelector('platform-field-enum');
        expect(pfEnum, 'method platform-field-enum').to.not.be.null;
        const inp = pfEnum.shadowRoot.querySelector('input.field-pill-enum-input');
        inp.focus();
        await elementUpdated(pfEnum);
        const getRow = pfEnum.shadowRoot.querySelector('[data-enum-value="GET"]');
        expect(getRow, 'GET enum row').to.not.be.null;
        getRow.click();
        expect(last, 'editor change event').to.exist;
        expect(last.patch).to.deep.equal({ method: 'GET' });
    });

    it('flows-mcp-node-editor — server select', async () => {
        const node = { node_id: 'a', type: 'mcp', name: 'M' };
        const el = await fixture(html`
            <flows-mcp-node-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'mcp'}>
            </flows-mcp-node-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const enumFields = base.querySelectorAll('platform-field[type="enum"]');
        expect(enumFields.length).to.be.greaterThanOrEqual(2);
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
        const fields = el.shadowRoot.querySelector('flows-base-node-editor')
            .querySelectorAll('.mcp-control-row platform-field');
        expect(fields[0].value).to.equal('browser');
        expect(fields[1].value).to.equal('browser_create_session');
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
        const buttons = root.querySelectorAll('.toggle button');
        expect(buttons.length).to.equal(2);
    });

    it('flows-remote-flow-editor — toggle url ↔ flow_id', async () => {
        const node = { node_id: 'a', type: 'remote_flow', name: 'R', url: 'https://api/x' };
        const el = await fixture(html`
            <flows-remote-flow-editor .nodeId=${'a'} .flowId=${'demo'} .branchId=${'base'}
                .nodeConfig=${node} .nodeType=${'remote_flow'}>
            </flows-remote-flow-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const buttons = el.shadowRoot.querySelector('flows-base-node-editor').querySelectorAll('.toggle button');
        buttons[1].click();
        expect(last.patch).to.have.property('flow_id', '');
        expect(last.patch).to.have.property('url', null);
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
