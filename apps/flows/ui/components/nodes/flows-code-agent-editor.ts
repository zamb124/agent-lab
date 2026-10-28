/**
 * flows-code-agent-editor — инспектор ноды code_agent (дерево Documents + rebuild).
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-json-editor.js';
import '@platform/lib/components/platform-spinner.js';
import { buildCodeAgentSourceFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { buildDocumentsCatalogEntryUrl } from '@platform/lib/utils/build-service-entry-url.js';
import { getActivePlatformNamespaceName } from '@platform/lib/utils/platform-namespace.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { commitShaFromGitUrl } from '../../_helpers/code-agent-git.js';
import { parseJsonStringList } from '../../_helpers/code-agent-json-list.js';
import { asObject, isPlainObject } from '../../_helpers/flows-resolvers.js';
import './flows-base-node-editor.js';
import '../editors/flows-state-mapping-editor.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

function elementRenderRoot(host: Element, label: string): ParentNode {
    if (!('renderRoot' in host)) {
        throw new Error(`flows-code-agent-editor: ${label} render root required`);
    }
    const root = host.renderRoot;
    if (root instanceof ShadowRoot || root instanceof HTMLElement || root instanceof DocumentFragment) {
        return root;
    }
    throw new Error(`flows-code-agent-editor: ${label} render root required`);
}

/**
 * @typedef {{ kind: 'file', title: string } | { kind: 'dir', title: string, children: CodeAgentTreeNode[] }} CodeAgentTreeNode
 */

export class FlowsCodeAgentEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        nodeId: { type: String },
        flowId: { type: String },
        branchId: { type: String },
        nodeConfig: { type: Object },
        nodeType: { type: String },
        flowVariables: { type: Object },
        graphNodes: { type: Array },
        previewExecutionState: { type: Object },
        dataflowNode: { type: Object },
        embedded: { type: Boolean, reflect: true },
        _tree: { state: true },
        _status: { state: true },
        _draftGitUrl: { state: true },
        _draftSourceSha: { state: true },
        _draftArgvText: { state: true },
        _draftEgressText: { state: true },
        _treeLoading: { state: true },
    }
    declare nodeId: string;
    declare flowId: string;
    declare branchId: string;
    declare nodeConfig: Record<string, any> | null;
    declare nodeType: any;
    declare flowVariables: Record<string, any> | null;
    declare graphNodes: any[] | null;
    declare previewExecutionState: Record<string, any> | null;
    declare dataflowNode: Record<string, any> | null;
    declare embedded: boolean;
    declare _tree: any;
    declare _status: any;
    declare _draftGitUrl: any;
    declare _draftSourceSha: any;
    declare _draftArgvText: any;
    declare _draftEgressText: any;
    declare _treeLoading: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        glassStyles,
        css`
            :host { display: block; height: 100%; min-height: 0; }
            .stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .section {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .section-title {
                margin: 0;
                font-size: var(--text-xs);
                font-weight: 600;
                letter-spacing: 0.04em;
                text-transform: uppercase;
                color: var(--text-tertiary);
            }
            .source-row,
            .row-2 {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                gap: var(--space-2);
                align-items: end;
            }
            .source-row {
                grid-template-columns: minmax(0, 1fr) auto;
            }
            .source-row.has-sha {
                grid-template-columns: minmax(0, 1.6fr) minmax(12rem, 0.8fr);
            }
            .files-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                min-height: 12rem;
            }
            .dropzone {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: var(--space-2);
                padding: var(--space-4);
                border: 1px dashed var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                cursor: pointer;
            }
            .dropzone-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            .tree {
                margin: 0;
                padding: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary);
                max-height: 16rem;
                overflow: auto;
            }
            .tree ul {
                margin: 0;
                padding-left: var(--space-4);
            }
            .tree li {
                margin: var(--space-1) 0;
            }
            .tree-loading {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .status-line {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.4;
                margin: 0;
            }
            .open-docs {
                font-size: var(--text-sm);
                align-self: flex-start;
            }
            .image-bar {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }
            .image-meta {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                min-width: 0;
                flex: 1;
            }
            details.metadata-block {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
            }
            details.metadata-block summary {
                cursor: pointer;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            .field-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin: var(--space-2) 0;
                line-height: 1.35;
            }
            @media (max-width: 640px) {
                .source-row,
                .source-row.has-sha,
                .row-2 {
                    grid-template-columns: minmax(0, 1fr);
                }
            }
        `,
    ];
    private _importGitOp: OpController;
    private _importArchiveOp: OpController;
    private _rebuildOp: OpController;
    private _statusOp: OpController;
    private _catalogItemsOp: OpController;
    private _fileUpload: OpController;
    private _authSel: SelectController<any>;

    constructor() {
        super();
        this.nodeId = '';
        this.flowId = '';
        this.branchId = '';
        this.nodeConfig = null;
        this.nodeType = 'code_agent';
        this.flowVariables = null;
        this.graphNodes = null;
        this.previewExecutionState = null;
        this.dataflowNode = null;
        this.embedded = false;
        this._tree = null;
        this._status = null;
        this._draftGitUrl = null;
        this._draftSourceSha = null;
        this._draftArgvText = null;
        this._draftEgressText = null;
        this._treeLoading = false;
        this._importGitOp = this.useOp('flows/code_agent_import_git');
        this._importArchiveOp = this.useOp('flows/code_agent_import_archive');
        this._rebuildOp = this.useOp('flows/code_agent_rebuild');
        this._statusOp = this.useOp('flows/code_agent_status');
        this._catalogItemsOp = this.useOp('office/catalog_items');
        this._fileUpload = this.useOp('platform/file_create');
        this._authSel = this.select((s) => (s as any).auth.user);
    }

    _emitPatch(patch: any) {
        this.emit('change', { nodeId: this.nodeId, patch });
    }

    _apiBranchId() {
        const raw = typeof this.branchId === 'string' ? this.branchId : '';
        if (raw.length === 0 || raw === 'base') {
            return 'default';
        }
        return raw;
    }

    _liveGitUrl() {
        if (this._draftGitUrl !== null) {
            return this._draftGitUrl;
        }
        const cfg = asObject(this.nodeConfig);
        return typeof (cfg as any).git_url === 'string' ? (cfg as any).git_url : '';
    }

    _liveSourceSha() {
        if (this._draftSourceSha !== null) {
            return this._draftSourceSha;
        }
        const cfg = asObject(this.nodeConfig);
        return typeof (cfg as any).source_sha === 'string' ? (cfg as any).source_sha : '';
    }

    _liveArgvText() {
        if (this._draftArgvText !== null) {
            return this._draftArgvText;
        }
        const cfg = asObject(this.nodeConfig);
        if (Array.isArray((cfg as any).invoke_argv) && (cfg as any).invoke_argv.length > 0) {
            return JSON.stringify((cfg as any).invoke_argv);
        }
        return '';
    }

    _liveEgressText() {
        if (this._draftEgressText !== null) {
            return this._draftEgressText;
        }
        const cfg = asObject(this.nodeConfig);
        return Array.isArray((cfg as any).egress_hosts) ? JSON.stringify((cfg as any).egress_hosts) : '';
    }

    _ingestBusy() {
        return Boolean(
            this._importGitOp.busy
            || this._importArchiveOp.busy
            || this._fileUpload.busy
            || this._treeLoading
        );
    }

    _catalogId() {
        const cfg = asObject(this.nodeConfig);
        const catalogId = (cfg as any).catalog_id;
        if (typeof catalogId === 'string' && catalogId.length > 0) {
            return catalogId;
        }
        return '';
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('flowId') || changed.has('nodeId')) {
            this._draftGitUrl = null;
            this._draftSourceSha = null;
            this._draftArgvText = null;
            this._draftEgressText = null;
            this._tree = null;
            this._status = null;
        }
        if (
            changed.has('nodeConfig')
            || changed.has('flowId')
            || changed.has('nodeId')
            || changed.has('branchId')
        ) {
            const catalogId = this._catalogId();
            if (catalogId.length > 0 && this.flowId && this.nodeId) {
                void this._reloadTree(catalogId);
                void this._reloadStatus();
            }
        }
    }

    /**
     * @param {string} catalogId
     * @returns {Promise<CodeAgentTreeNode[]>}
     */
    async _loadCatalogTree(catalogId: any): Promise<any[]> {
        const items = await this._catalogItemsOp.run({ catalog_id: catalogId });
        if (!isPlainObject(items)) {
            throw new Error('flows-code-agent-editor: catalog items object required');
        }
        const catalogs = items.catalogs;
        const documents = items.documents;
        if (!Array.isArray(catalogs)) {
            throw new Error('flows-code-agent-editor: catalog items.catalogs array required');
        }
        if (!Array.isArray(documents)) {
            throw new Error('flows-code-agent-editor: catalog items.documents array required');
        }
        /** @type {CodeAgentTreeNode[]} */
        const nodes = [];
        for (const catalog of catalogs) {
            if (catalog === null || typeof catalog !== 'object') {
                throw new Error('flows-code-agent-editor: catalog entry must be an object');
            }
            const childId = catalog.catalog_id;
            const title = catalog.title;
            if (typeof childId !== 'string' || childId.length === 0) {
                throw new Error('flows-code-agent-editor: child catalog_id required');
            }
            if (typeof title !== 'string' || title.length === 0) {
                throw new Error('flows-code-agent-editor: child catalog title required');
            }
            nodes.push({
                kind: 'dir',
                title,
                children: await this._loadCatalogTree(childId),
            });
        }
        for (const document of documents) {
            if (document === null || typeof document !== 'object') {
                throw new Error('flows-code-agent-editor: document entry must be an object');
            }
            const title = document.title;
            if (typeof title !== 'string' || title.length === 0) {
                throw new Error('flows-code-agent-editor: document title required');
            }
            nodes.push({ kind: 'file', title });
        }
        return nodes;
    }

    async _reloadTree(catalogId: any) {
        this._treeLoading = true;
        try {
            this._tree = await this._loadCatalogTree(catalogId);
        } finally {
            this._treeLoading = false;
        }
    }

    async _reloadStatus() {
        const status = await this._statusOp.run({
            flow_id: this.flowId,
            node_id: this.nodeId,
            branch_id: this._apiBranchId(),
        });
        this._status = status;
    }

    _onGitUrl(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d) || typeof d.value !== 'string') {
            throw new Error('flows-code-agent-editor: git_url string required');
        }
        this._draftGitUrl = d.value;
        const fromUrl = commitShaFromGitUrl(d.value);
        if (fromUrl.length > 0) {
            this._draftSourceSha = fromUrl;
            this._emitPatch({ git_url: d.value, source_sha: fromUrl });
            return;
        }
        this._emitPatch({ git_url: d.value, source_sha: null });
    }

    _onSourceSha(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d) || typeof d.value !== 'string') {
            throw new Error('flows-code-agent-editor: source_sha string required');
        }
        this._draftSourceSha = d.value;
        this._emitPatch({ source_sha: d.value.length > 0 ? d.value : null });
    }

    _onLanguage(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d) || typeof d.value !== 'string') {
            throw new Error('flows-code-agent-editor: language string required');
        }
        this._emitPatch({ language: d.value });
    }

    _onInvokeKind(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d) || typeof d.value !== 'string') {
            throw new Error('flows-code-agent-editor: invoke_kind string required');
        }
        this._emitPatch({ invoke_kind: d.value });
    }

    _onInvokeArgv(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d) || typeof d.value !== 'string') {
            throw new Error('flows-code-agent-editor: invoke_argv string required');
        }
        this._draftArgvText = d.value;
        const parsed = parseJsonStringList(d.value);
        if (parsed.status !== 'ok') {
            return;
        }
        this._emitPatch({ invoke_argv: parsed.items });
    }

    _onListenPort(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d)) {
            throw new Error('flows-code-agent-editor: invoke_listen_port value required');
        }
        const value = d.value;
        if (value === null || value === '') {
            this._emitPatch({ invoke_listen_port: null });
            return;
        }
        if (typeof value !== 'number' || !Number.isInteger(value) || value < 1 || value > 65535) {
            throw new Error('flows-code-agent-editor: invoke_listen_port must be an integer 1..65535');
        }
        this._emitPatch({ invoke_listen_port: value });
    }

    _onEgressHosts(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d) || typeof d.value !== 'string') {
            throw new Error('flows-code-agent-editor: egress_hosts string required');
        }
        this._draftEgressText = d.value;
        const parsed = parseJsonStringList(d.value);
        if (parsed.status === 'empty') {
            this._emitPatch({ egress_hosts: [] });
            return;
        }
        if (parsed.status !== 'ok') {
            return;
        }
        this._emitPatch({ egress_hosts: parsed.items });
    }

    _onIdleTtl(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d)) {
            throw new Error('flows-code-agent-editor: idle_ttl_seconds value required');
        }
        const value = d.value;
        if (value === null || value === '') {
            this._emitPatch({ idle_ttl_seconds: null });
            return;
        }
        if (typeof value !== 'number' || !Number.isInteger(value) || value < 1 || value > 86400) {
            throw new Error('flows-code-agent-editor: idle_ttl_seconds must be an integer 1..86400');
        }
        this._emitPatch({ idle_ttl_seconds: value });
    }

    _guestEnvKeyIsReserved(key: string) {
        const reservedPrefixes = ['OPENAI_', 'CAPABILITY_', 'PLATFORM_', 'GUEST_'];
        const reservedKeys = new Set([
            'PATH', 'HOME', 'LANG', 'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE',
            'PYTHONPATH', 'PYTHONHOME', 'OPENAI_API_KEY', 'OPENAI_BASE_URL',
            'CAPABILITY_GATEWAY_URL', 'GUEST_LISTEN_PORT',
        ]);
        return reservedKeys.has(key) || reservedPrefixes.some((prefix) => key.startsWith(prefix));
    }

    _onGuestEnvMapping(e: CustomEvent) {
        const detail = e && typeof e === 'object' ? e.detail : null;
        if (!isPlainObject(detail) || !Object.prototype.hasOwnProperty.call(detail, 'mapping')) {
            return;
        }
        if (typeof e.stopPropagation === 'function') {
            e.stopPropagation();
        }
        const mapping = detail.mapping;
        if (!isPlainObject(mapping)) {
            throw new Error('flows-code-agent-editor: guest_env mapping must be an object');
        }
        const guestEnv = {};
        for (const [key, item] of Object.entries(mapping)) {
            if (!/^[A-Z][A-Z0-9_]*$/.test(key)) {
                throw new Error(`flows-code-agent-editor: guest_env key ${key} is invalid`);
            }
            if (this._guestEnvKeyIsReserved(key)) {
                throw new Error(`flows-code-agent-editor: guest_env key ${key} is reserved`);
            }
            if (typeof item !== 'string' || item.length === 0) {
                throw new Error(`flows-code-agent-editor: guest_env ${key} must be a non-empty string`);
            }
            (guestEnv as any)[key] = item;
        }
        this._emitPatch({ guest_env: guestEnv });
    }

    _onMetadataTemplate(parsed: any) {
        if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
            throw new Error('flows-code-agent-editor: metadata_template must be a JSON object');
        }
        this._emitPatch({ metadata_template: JSON.stringify(parsed, null, 2) });
    }

    _stateSuggestions() {
        const df = isPlainObject(this.dataflowNode) ? this.dataflowNode : null;
        const rows = df && Array.isArray(df.incoming_state) ? df.incoming_state : [];
        const writes = df && Array.isArray(df.writes) ? df.writes : [];
        const paths = [];
        for (const item of [...rows, ...writes]) {
            if (!item || typeof item.path !== 'string' || item.path.length === 0) continue;
            if (item.path.startsWith('variables.')) continue;
            paths.push(item.path);
        }
        return Array.from(new Set(paths));
    }

    _varSuggestions() {
        const df = isPlainObject(this.dataflowNode) ? this.dataflowNode : null;
        const rows = df && Array.isArray(df.incoming_state) ? df.incoming_state : [];
        const vars = [];
        for (const item of rows) {
            if (!item || typeof item.path !== 'string') continue;
            if (item.path.startsWith('variables.')) vars.push(item.path.slice('variables.'.length));
        }
        const fv = this.flowVariables && typeof this.flowVariables === 'object' ? this.flowVariables : {};
        for (const key of Object.keys(fv)) {
            vars.push(key);
        }
        return Array.from(new Set(vars));
    }

    _platformFieldInputValue(testid: any) {
        const host = this.renderRoot.querySelector(`[data-testid="${testid}"]`);
        if (host === null) {
            return null;
        }
        const stringFieldHost = elementRenderRoot(host, testid).querySelector('platform-field-string');
        if (!(stringFieldHost instanceof Element)) {
            throw new Error(`flows-code-agent-editor: ${testid} string field required`);
        }
        const input = elementRenderRoot(stringFieldHost, testid).querySelector('input.field-pill-input');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error(`flows-code-agent-editor: ${testid} input required`);
        }
        return input.value;
    }

    async _onImportGit() {
        const fieldUrl = this._platformFieldInputValue('code-agent-git-url');
        if (typeof fieldUrl === 'string') {
            this._draftGitUrl = fieldUrl;
        }
        const fieldSha = this._platformFieldInputValue('code-agent-source-sha');
        if (typeof fieldSha === 'string') {
            this._draftSourceSha = fieldSha;
        }
        const gitUrl = this._liveGitUrl().trim();
        const fromUrl = commitShaFromGitUrl(gitUrl);
        const sourceSha = (fromUrl.length > 0 ? fromUrl : this._liveSourceSha()).trim();
        if (fromUrl.length > 0) {
            this._draftSourceSha = fromUrl;
        }
        if (gitUrl.length === 0) {
            this.toast('code_agent_editor.toast_git_url_required', { type: 'error' });
            return;
        }
        const imported = await this._importGitOp.run({
            flow_id: this.flowId,
            node_id: this.nodeId,
            branch_id: this._apiBranchId(),
            git_url: gitUrl,
            source_sha: sourceSha,
        });
        if (imported === null) {
            return;
        }
        if (!isPlainObject(imported) || typeof imported.source_sha !== 'string' || imported.source_sha.length === 0) {
            throw new Error('flows-code-agent-editor: import-git source_sha required');
        }
        this._draftSourceSha = imported.source_sha;
        this._emitPatch({ git_url: gitUrl, source_sha: imported.source_sha });
        await this._reloadAfterMutation();
    }

    async _reloadAfterMutation() {
        const catalogId = this._catalogId();
        if (catalogId.length > 0) {
            await this._reloadTree(catalogId);
        }
        await this._reloadStatus();
    }

    async _onRebuild() {
        const catalogId = this._catalogId();
        if (catalogId.length === 0) {
            this.toast('code_agent_editor.toast_catalog_required', { type: 'error' });
            return;
        }
        const cfg = asObject(this.nodeConfig);
        const language = (cfg as any).language;
        if (typeof language !== 'string' || language.length === 0) {
            throw new Error('flows-code-agent-editor: language required for rebuild');
        }
        const invokeKind = (cfg as any).invoke_kind;
        if (typeof invokeKind !== 'string' || invokeKind.length === 0) {
            throw new Error('flows-code-agent-editor: invoke_kind required for rebuild');
        }
        const argvParsed = parseJsonStringList(this._liveArgvText());
        if (argvParsed.status === 'empty') {
            this.toast('code_agent_editor.toast_invoke_argv_required', { type: 'error' });
            return;
        }
        if (argvParsed.status !== 'ok') {
            this.toast('code_agent_editor.toast_invoke_argv_invalid', { type: 'error' });
            return;
        }
        const invokeArgv = argvParsed.items;
        const listenPort = (cfg as any).invoke_listen_port;
        if (
            listenPort !== undefined
            && listenPort !== null
            && (typeof listenPort !== 'number' || !Number.isInteger(listenPort))
        ) {
            throw new Error('flows-code-agent-editor: invoke_listen_port must be int or null');
        }
        const egressParsed = parseJsonStringList(this._liveEgressText());
        let resolvedEgress;
        if (egressParsed.status === 'empty') {
            resolvedEgress = [];
        } else if (egressParsed.status !== 'ok') {
            this.toast('code_agent_editor.toast_egress_hosts_invalid', { type: 'error' });
            return;
        } else {
            resolvedEgress = egressParsed.items;
        }
        const rebuilt = await this._rebuildOp.run({
            flow_id: this.flowId,
            node_id: this.nodeId,
            branch_id: this._apiBranchId(),
            language,
            invoke_kind: invokeKind,
            invoke_argv: invokeArgv,
            invoke_listen_port: typeof listenPort === 'number' ? listenPort : null,
            egress_hosts: resolvedEgress,
            git_url: this._liveGitUrl(),
            source_sha: this._liveSourceSha(),
        });
        if (rebuilt === null) {
            return;
        }
        await this._reloadStatus();
    }

    _onOpenLogs() {
        if (this.flowId.length === 0 || this.nodeId.length === 0) {
            throw new Error('flows-code-agent-editor: flowId and nodeId required for logs');
        }
        this.openModal('flows.logs', { flowId: this.flowId, nodeId: this.nodeId });
    }

    _relativeDirFromFile(file: any) {
        const relative = typeof file.webkitRelativePath === 'string' ? file.webkitRelativePath : '';
        if (relative.length === 0) {
            return '';
        }
        const parts = relative.split('/');
        if (parts.length < 2) {
            return '';
        }
        return parts.slice(0, -1).join('/');
    }

    async _uploadSourceFile(file: any, relativeDir: any) {
        const spec = buildCodeAgentSourceFileCreateSpecJson({
            flowId: this.flowId,
            nodeId: this.nodeId,
            relativeDir: relativeDir.length > 0 ? relativeDir : undefined,
        });
        const result = await this._fileUpload.run({ file, spec });
        if (!isPlainObject(result) || typeof result.file_id !== 'string' || result.file_id.length === 0) {
            throw new Error('flows-code-agent-editor: upload must return file_id');
        }
        return result.file_id;
    }

    async _ingestFiles(files: any) {
        if (!files || files.length === 0) {
            return;
        }
        const list = Array.from(files);
        const onlyZip = list.length === 1 && (list as any)[0].name.toLowerCase().endsWith('.zip');
        if (onlyZip) {
            const fileId = await this._uploadSourceFile(list[0], '');
            await this._importArchiveOp.run({
                flow_id: this.flowId,
                node_id: this.nodeId,
                branch_id: this._apiBranchId(),
                file_id: fileId,
            });
        } else {
            for (const file of list) {
                await this._uploadSourceFile(file, this._relativeDirFromFile(file));
            }
        }
        await this._reloadAfterMutation();
    }

    async _onPickFiles(e: Event) {
        const input = e.target;
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('flows-code-agent-editor: file input required');
        }
        await this._ingestFiles(input.files);
        input.value = '';
    }

    _onDragOver(e: Event) {
        e.preventDefault();
    }

    async _onDrop(e: Event) {
        e.preventDefault();
        if (!(e instanceof DragEvent)) {
            throw new Error('flows-code-agent-editor: drop event required');
        }
        await this._ingestFiles(e.dataTransfer === null ? null : e.dataTransfer.files);
    }

    _clickHiddenInput(testid: any) {
        const input = this.renderRoot.querySelector(`[data-testid="${testid}"]`);
        if (!(input instanceof HTMLInputElement)) {
            throw new Error(`flows-code-agent-editor: ${testid} input required`);
        }
        input.click();
    }

    _documentsHref() {
        const catalogId = this._catalogId();
        if (catalogId.length === 0) {
            throw new Error('flows-code-agent-editor: catalog_id required for Documents link');
        }
        const user = this._authSel.value;
        const companyId = user && typeof user.company_id === 'string' ? user.company_id : '';
        if (companyId.length === 0) {
            throw new Error('flows-code-agent-editor: company_id required for Documents link');
        }
        return buildDocumentsCatalogEntryUrl(catalogId, getActivePlatformNamespaceName(companyId));
    }

    /**
     * @param {CodeAgentTreeNode[]} nodes
     */
    _renderTreeNodes(nodes: any) {
        return html`
            <ul>
                ${nodes.map((node: any) => {
                    if (node.kind === 'dir') {
                        return html`<li>${node.title}/${this._renderTreeNodes(node.children)}</li>`;
                    }
                    return html`<li>${node.title}</li>`;
                })}
            </ul>
        `;
    }

    _renderTree() {
        const tree = this._tree;
        if (!Array.isArray(tree)) {
            return html`<p class="status-line">${this.t('code_agent_editor.tree_empty')}</p>`;
        }
        if (tree.length === 0) {
            return html`<p class="status-line">${this.t('code_agent_editor.tree_empty')}</p>`;
        }
        return html`<div class="tree">${this._renderTreeNodes(tree)}</div>`;
    }

    override render(): TemplateResult {
        const cfg = asObject(this.nodeConfig);
        const gitUrl = this._liveGitUrl();
        const sourceSha = this._liveSourceSha();
        const shaFromUrl = commitShaFromGitUrl(gitUrl);
        const needsSha = shaFromUrl.length === 0;
        const language = typeof (cfg as any).language === 'string' ? (cfg as any).language : '';
        const invokeKind = typeof (cfg as any).invoke_kind === 'string' ? (cfg as any).invoke_kind : '';
        const argvText = this._liveArgvText();
        const listenPort = typeof (cfg as any).invoke_listen_port === 'number' ? (cfg as any).invoke_listen_port : null;
        const idleTtl = typeof (cfg as any).idle_ttl_seconds === 'number' ? (cfg as any).idle_ttl_seconds : null;
        const egressText = this._liveEgressText();
        const guestEnv =
            (cfg as any).guest_env !== null && typeof (cfg as any).guest_env === 'object' && !Array.isArray((cfg as any).guest_env)
                ? (cfg as any).guest_env
                : {};
        const metadataTemplateStr =
            typeof (cfg as any).metadata_template === 'string' && (cfg as any).metadata_template.length > 0
                ? (cfg as any).metadata_template
                : '{}';
        const catalogId = this._catalogId();
        const status = isPlainObject(this._status) ? this._status : null;
        const digest = status !== null && typeof status.image_digest === 'string' ? status.image_digest : '';
        const buildStatus = status !== null && typeof status.build_status === 'string' ? status.build_status : 'none';
        const buildError = status !== null && typeof status.build_error === 'string' ? status.build_error : '';
        const ingestBusy = this._ingestBusy();
        return html`
            <flows-base-node-editor
                .nodeId=${this.nodeId}
                .flowId=${this.flowId}
                .branchId=${this.branchId}
                .nodeConfig=${this.nodeConfig}
                .nodeType=${typeof this.nodeType === 'string' && this.nodeType.length > 0 ? this.nodeType : 'code_agent'}
                .flowVariables=${this.flowVariables}
                .graphNodes=${this.graphNodes}
                .previewExecutionState=${this.previewExecutionState}
                .dataflowNode=${this.dataflowNode}
                ?embedded=${this.embedded}
            >
                <div slot="settings" class="stack">
                    <p class="status-line">${this.t('code_agent_editor.user_does_not_bring_docker')}</p>
                    <section class="section">
                        <h3 class="section-title">${this.t('code_agent_editor.section_source')}</h3>
                        <div class=${needsSha ? 'source-row has-sha' : 'source-row'}>
                            <platform-field
                                data-testid="code-agent-git-url"
                                pill-density="compact"
                                mode="edit"
                                type="string"
                                input-type="url"
                                .label=${this.t('code_agent_editor.git_url')}
                                .hint=${this.t('code_agent_editor.git_url_hint')}
                                .placeholder=${this.t('code_agent_editor.git_url_placeholder')}
                                .value=${gitUrl}
                                @change=${this._onGitUrl}
                            >
                                <platform-button
                                    slot="suffix"
                                    data-testid="code-agent-import-git"
                                    density="compact"
                                    variant="primary"
                                    .loading=${this._importGitOp.busy}
                                    @click=${() => this._onImportGit()}
                                >
                                    ${this.t('code_agent_editor.import_git')}
                                </platform-button>
                            </platform-field>
                            ${needsSha ? html`
                                <platform-field
                                    data-testid="code-agent-source-sha"
                                    pill-density="compact"
                                    mode="edit"
                                    type="string"
                                    .label=${this.t('code_agent_editor.source_sha')}
                                    .hint=${this.t('code_agent_editor.source_sha_hint')}
                                    .value=${sourceSha}
                                    @change=${this._onSourceSha}
                                ></platform-field>
                            ` : ''}
                        </div>
                    </section>
                    <section class="section">
                        <h3 class="section-title">${this.t('code_agent_editor.section_files')}</h3>
                        <div class="files-card" data-testid="code-agent-files">
                            <div
                                class="dropzone"
                                data-testid="code-agent-dropzone"
                                @dragover=${this._onDragOver}
                                @drop=${this._onDrop}
                                @click=${() => this._clickHiddenInput('code-agent-file')}
                            >
                                <p class="status-line">${this.t('code_agent_editor.upload_hint')}</p>
                                <div class="dropzone-actions">
                                    <platform-button
                                        density="compact"
                                        variant="secondary"
                                        @click=${(e: Event) => { e.stopPropagation(); this._clickHiddenInput('code-agent-file'); }}
                                    >
                                        ${this.t('code_agent_editor.dropzone_files')}
                                    </platform-button>
                                    <platform-button
                                        density="compact"
                                        variant="secondary"
                                        @click=${(e: Event) => { e.stopPropagation(); this._clickHiddenInput('code-agent-folder'); }}
                                    >
                                        ${this.t('code_agent_editor.dropzone_folder')}
                                    </platform-button>
                                </div>
                                <input hidden data-testid="code-agent-file" type="file" multiple @change=${(e: Event) => this._onPickFiles(e)} @click=${(e: Event) => e.stopPropagation()} />
                                <input hidden data-testid="code-agent-folder" type="file" webkitdirectory directory multiple @change=${(e: Event) => this._onPickFiles(e)} @click=${(e: Event) => e.stopPropagation()} />
                            </div>
                            ${catalogId.length > 0 ? html`
                                <a class="open-docs" href=${this._documentsHref()} target="_blank" rel="noopener">
                                    ${this.t('code_agent_editor.open_documents')}
                                </a>
                            ` : html`<p class="status-line">${this.t('code_agent_editor.waiting_catalog')}</p>`}
                            ${ingestBusy ? html`
                                <div class="tree-loading" data-testid="code-agent-tree-loading">
                                    <platform-spinner size="xs"></platform-spinner>
                                    ${this.t('code_agent_editor.tree_loading')}
                                </div>
                            ` : this._renderTree()}
                        </div>
                    </section>
                    <section class="section">
                        <h3 class="section-title">${this.t('code_agent_editor.section_run')}</h3>
                        <div class="row-2">
                            <platform-field
                                data-testid="code-agent-language"
                                pill-density="compact"
                                mode="edit"
                                type="enum"
                                .label=${this.t('code_agent_editor.language')}
                                .value=${language}
                                .config=${{ values: [
                                    { value: 'python', label: this.t('code_agent_editor.language_python') },
                                    { value: 'node', label: this.t('code_agent_editor.language_node') },
                                ] }}
                                @change=${this._onLanguage}
                            ></platform-field>
                            <platform-field
                                pill-density="compact"
                                mode="edit"
                                type="enum"
                                .label=${this.t('code_agent_editor.invoke_kind')}
                                .value=${invokeKind}
                                .config=${{ values: [
                                    { value: 'cli', label: this.t('code_agent_editor.invoke_kind_cli') },
                                    { value: 'a2a', label: this.t('code_agent_editor.invoke_kind_a2a') },
                                ] }}
                                @change=${this._onInvokeKind}
                            ></platform-field>
                        </div>
                        <platform-field
                            data-testid="code-agent-argv"
                            pill-density="compact"
                            mode="edit"
                            type="string"
                            .label=${this.t('code_agent_editor.invoke_argv')}
                            .hint=${this.t('code_agent_editor.invoke_argv_hint')}
                            .placeholder=${this.t('code_agent_editor.invoke_argv_placeholder')}
                            .value=${argvText}
                            @change=${this._onInvokeArgv}
                        ></platform-field>
                        <div class="row-2">
                            <platform-field
                                pill-density="compact"
                                mode="edit"
                                type="integer"
                                .label=${this.t('code_agent_editor.invoke_listen_port')}
                                .hint=${this.t('code_agent_editor.invoke_listen_port_hint')}
                                .value=${listenPort}
                                @change=${this._onListenPort}
                            ></platform-field>
                            <platform-field
                                data-testid="code-agent-idle-ttl"
                                pill-density="compact"
                                mode="edit"
                                type="integer"
                                .label=${this.t('code_agent_editor.idle_ttl_seconds')}
                                .hint=${this.t('code_agent_editor.idle_ttl_seconds_hint')}
                                .value=${idleTtl}
                                @change=${this._onIdleTtl}
                            ></platform-field>
                        </div>
                        <platform-field
                            data-testid="code-agent-egress"
                            pill-density="compact"
                            mode="edit"
                            type="string"
                            .label=${this.t('code_agent_editor.egress_hosts')}
                            .hint=${this.t('code_agent_editor.egress_hosts_hint')}
                            .value=${egressText}
                            @change=${this._onEgressHosts}
                        ></platform-field>
                        <details class="glass-subtle metadata-block" data-testid="code-agent-guest-env">
                            <summary>${this.t('code_agent_editor.guest_env')}</summary>
                            <p class="field-hint">${this.t('code_agent_editor.guest_env_hint')}</p>
                            <flows-state-mapping-editor
                                syncKey=${`${String(this.flowId)}--${String(this.nodeId)}--guest-env`}
                                kind="input"
                                .allowPlatform=${true}
                                .title=${this.t('code_agent_editor.guest_env')}
                                .mapping=${guestEnv}
                                .stateSuggestions=${this._stateSuggestions()}
                                .varSuggestions=${this._varSuggestions()}
                                .platformSuggestions=${[
                                    'OPENAI_API_KEY',
                                    'OPENAI_BASE_URL',
                                    'CAPABILITY_GATEWAY_URL',
                                    'PLATFORM_EXECUTION_TOKEN',
                                    'PLATFORM_SESSION_ID',
                                    'PLATFORM_TASK_ID',
                                    'PLATFORM_CONTEXT_ID',
                                    'PLATFORM_FLOW_ID',
                                    'PLATFORM_NODE_ID',
                                    'PLATFORM_COMPANY_ID',
                                    'PLATFORM_USER_ID',
                                    'PLATFORM_BRANCH_ID',
                                    'PLATFORM_CHANNEL',
                                    'PLATFORM_REQUEST_ID',
                                    'PLATFORM_TRACE_ID',
                                    'PLATFORM_NAMESPACE',
                                    'PLATFORM_TEST_SCOPE',
                                ]}
                                @change=${this._onGuestEnvMapping}
                            ></flows-state-mapping-editor>
                        </details>
                        <details class="glass-subtle metadata-block" data-testid="code-agent-metadata">
                            <summary>${this.t('code_agent_editor.metadata')}</summary>
                            <p class="field-hint">${this.t('code_agent_editor.metadata_hint')}</p>
                            <platform-json-editor
                                validate-json
                                show-toolbar="false"
                                .readonly=${false}
                                .value=${metadataTemplateStr}
                                @change=${(e: CustomEvent) => {
                                    if (e.detail && 'parsed' in e.detail) {
                                        this._onMetadataTemplate(e.detail.parsed);
                                    }
                                }}
                            ></platform-json-editor>
                        </details>
                    </section>
                    <section class="section">
                        <h3 class="section-title">${this.t('code_agent_editor.section_image')}</h3>
                        <div class="image-bar">
                            <platform-button
                                data-testid="code-agent-rebuild"
                                variant="primary"
                                density="compact"
                                .loading=${this._rebuildOp.busy}
                                @click=${() => this._onRebuild()}
                            >
                                ${this.t('code_agent_editor.rebuild')}
                            </platform-button>
                            <platform-button
                                data-testid="code-agent-logs"
                                variant="secondary"
                                density="compact"
                                @click=${() => this._onOpenLogs()}
                            >
                                ${this.t('code_agent_editor.open_logs')}
                            </platform-button>
                            <div class="image-meta">
                                <p class="status-line">${this.t('code_agent_editor.build_status')}: ${buildStatus}</p>
                                ${digest.length > 0 ? html`<p class="status-line">${this.t('code_agent_editor.digest')}: ${digest}</p>` : ''}
                                ${buildError.length > 0 ? html`<p class="status-line">${buildError}</p>` : ''}
                            </div>
                        </div>
                    </section>
                </div>
            </flows-base-node-editor>
        `;
    }
}

customElements.define('flows-code-agent-editor', FlowsCodeAgentEditor);
