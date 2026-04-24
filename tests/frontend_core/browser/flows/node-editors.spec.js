/**
 * Smoke-набор для всех 9 node-editors (llm/code/channel/hitl/external_api/
 * mcp/flow/remote_flow/base) + базовых полей идентификации (rename/delete).
 *
 * Цель: проверить рендер top-level полей `NodeConfig` и эмит правильных
 * патчей по верному backend-контракту.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
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
import { operatorQueuesResource } from '../../../../apps/flows/ui/events/resources/operator.resource.js';
import { promptRenderOp } from '../../../../apps/flows/ui/events/resources/prompts.resource.js';
import { variablesResource } from '../../../../apps/flows/ui/events/resources/variables.resource.js';
import { toolsResource } from '../../../../apps/flows/ui/events/resources/tools.resource.js';

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
    operatorQueuesResource,
    promptRenderOp,
    variablesResource,
    toolsResource,
];

function bootstrap() {
    for (const f of FACTORIES) registerFactory(f);
    const collected = collectFactories(FACTORIES);
    return bootstrapTestBus({ slices: collected.slices });
}

describe('node editors — top-level NodeConfig contract', () => {
    beforeEach(() => { resetPlatformState(); bootstrap(); });
    afterEach(() => fixtureCleanup());

    it('flows-llm-node-editor рендерит секции', async () => {
        const node = { node_id: 'a', type: 'llm_node', name: 'A', prompt: 'hi', tools: [] };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        expect(base).to.not.be.null;
        const blocks = base.querySelectorAll('section.block');
        expect(blocks.length).to.be.greaterThanOrEqual(5);
        const detailsLeftover = base.querySelectorAll('details');
        expect(detailsLeftover.length).to.equal(0);
    });

    it('flows-llm-node-editor structured_output скрывает react секцию', async () => {
        const node = { node_id: 'a', type: 'llm_node', name: 'A', structured_output: true };
        const el = await fixture(html`
            <flows-llm-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'llm_node'} .flowVariables=${{}} .graphNodes=${[]}>
            </flows-llm-node-editor>
        `);
        await elementUpdated(el);
        const base = el.shadowRoot.querySelector('flows-base-node-editor');
        const titles = Array.from(base.querySelectorAll('section.block .block-title')).map((s) => s.textContent);
        expect(titles.length).to.be.lessThanOrEqual(5);
    });

    it('flows-code-node-editor — вкладки Код / Схема', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A', code: 'print(1)' };
        const el = await fixture(html`
            <flows-code-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'}>
            </flows-code-node-editor>
        `);
        await elementUpdated(el);
        const tabs = el.shadowRoot.querySelectorAll('.main-tab');
        expect(tabs.length).to.be.greaterThanOrEqual(2);
        tabs[1].click();
        await elementUpdated(el);
        const jsonEditor = el.shadowRoot.querySelector('flows-code-editor[language="json"]');
        expect(jsonEditor).to.not.be.null;
    });

    it('flows-channel-node-editor — поля channel/action', async () => {
        const node = { node_id: 'a', type: 'channel', name: 'A', channel: 'telegram', action: 'send_message', channel_config: {} };
        const el = await fixture(html`
            <flows-channel-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'channel'}>
            </flows-channel-node-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const select = el.shadowRoot.querySelector('flows-base-node-editor').querySelector('select');
        select.value = 'webhook';
        select.dispatchEvent(new Event('change'));
        expect(last.patch).to.have.property('channel', 'webhook');
        expect(last.patch).to.have.property('channel_config').that.deep.equals({});
    });

    it('flows-hitl-node-editor — operator_queue_slug устанавливается', async () => {
        const node = { node_id: 'a', type: 'hitl_node', name: 'A' };
        const el = await fixture(html`
            <flows-hitl-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'hitl_node'} .flowVariables=${{}}>
            </flows-hitl-node-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const inputs = el.shadowRoot.querySelector('flows-base-node-editor').querySelectorAll('input[type="text"]');
        const slugInput = inputs[1];
        slugInput.value = 'support';
        slugInput.dispatchEvent(new Event('input'));
        expect(last.patch).to.deep.equal({ operator_queue_slug: 'support' });
    });

    it('flows-external-api-editor — добавление параметра', async () => {
        const node = { node_id: 'a', type: 'external_api', name: 'API', url: 'https://x', method: 'POST', parameters: [] };
        const el = await fixture(html`
            <flows-external-api-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'external_api'}>
            </flows-external-api-editor>
        `);
        await elementUpdated(el);
        let last = null;
        el.addEventListener('change', (e) => { last = e.detail; });
        const addBtn = el.shadowRoot.querySelector('flows-base-node-editor').querySelector('glass-button');
        addBtn.click();
        expect(last.patch.parameters).to.have.lengthOf(1);
        expect(last.patch.parameters[0]).to.have.property('location', 'body');
    });

    it('flows-mcp-node-editor — server select', async () => {
        const node = { node_id: 'a', type: 'mcp', name: 'M' };
        const el = await fixture(html`
            <flows-mcp-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'mcp'}>
            </flows-mcp-node-editor>
        `);
        await elementUpdated(el);
        const selects = el.shadowRoot.querySelector('flows-base-node-editor').querySelectorAll('select');
        expect(selects.length).to.be.greaterThanOrEqual(2);
    });

    it('flows-flow-node-editor — toggle ручного ID', async () => {
        const node = { node_id: 'a', type: 'flow', name: 'F', flow_id: 'subflow_x', skill_id: 'default' };
        const el = await fixture(html`
            <flows-flow-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
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
            <flows-remote-flow-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
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

    it('flows-base-node-editor — rename emit события', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A' };
        const el = await fixture(html`
            <flows-base-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'}>
            </flows-base-node-editor>
        `);
        await elementUpdated(el);
        let renamed = null;
        el.addEventListener('rename-node', (e) => { renamed = e.detail; });
        el._editingId = true;
        el._draftId = 'a_renamed';
        await elementUpdated(el);
        el._commitRenameId();
        expect(renamed).to.deep.equal({ oldId: 'a', newId: 'a_renamed' });
    });

    it('flows-base-node-editor — compact: одна колонка без panel-layout', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A' };
        const el = await fixture(html`
            <flows-base-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'}>
            </flows-base-node-editor>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.compact')).to.not.be.null;
        expect(el.shadowRoot.querySelector('.panel-layout')).to.be.null;
    });

    it('flows-base-node-editor — expanded: master-detail layout', async () => {
        const node = { node_id: 'a', type: 'code', name: 'A' };
        const el = await fixture(html`
            <flows-base-node-editor .nodeId=${'a'} .flowId=${'demo'} .skillId=${'base'}
                .nodeConfig=${node} .nodeType=${'code'} ?expanded=${true}>
            </flows-base-node-editor>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.panel-layout')).to.not.be.null;
        expect(el.shadowRoot.querySelector('.panel-sidebar')).to.not.be.null;
        expect(el.shadowRoot.querySelector('.panel-main')).to.not.be.null;
        expect(el.shadowRoot.querySelector('.compact')).to.be.null;
    });
});
