/**
 * ``<platform-flow-ui>`` — единственный хост интерфейса flow: SPA-чат, drawer/panel embed,
 * shared session, панель выполнения редактора, HITL оператора. Транспорт — ``FlowUIClient``,
 * состояние — ``FlowUIStore``; страницы рендерит ``<flow-ui-page>``, ленту — ``<flow-ui-conversation>``.
 *
 * Внешний контракт: атрибуты ``flow-id``/``branch-id``/``embed-id``/``context-id``/``base-url``/``display``/
 * ``profile``/``theme``/``locale``/``readonly``/``credentials``/``work-item-id``/``company-id``/``voice-base-url``/
 * ``platform-ui-origin``/``assistant-title``; свойства ``initialDocument``, ``interactionPolicy``,
 * ``getRequestHeaders``, ``getExtraMetadataVariables``; методы ``startNewContext``, ``cancelActiveTask``,
 * ``navigate``, ``applyA2AFrame``, ``createShare``, ``revokeShare``, ``stopVoice``, ``toggleVoiceSession``;
 * события ``flow-ui-ready``/``flow-ui-error``/``flow-ui-a2a-frame``/``flow-ui-submit-start``/``flow-ui-submit-end``/
 * ``flow-ui-state-changed``/``flow-ui-navigation``/``flow-ui-file-progress``/``flow-ui-share-created``/
 * ``flow-ui-share-revoked``/``flow-ui-identity-changed``/``flow-ui-drawer-*``/``flow-ui-stop-voice``/
 * ``flow-ui-open-observability``/``browser-preview-open``.
 */

import { isPlainRecord, recordField } from '../../events/payload.js';
import { LitElement, html, nothing, type PropertyValues } from 'lit';
import { buildFlowSessionFileCreateSpecJson } from '../../utils/file-create-spec.js';
import { resolvePlatformFileRefs } from '../../utils/platform-file-upload.js';
import { getPlatformBrandBootstrap } from '../../utils/platform-brand.js';
import { stopStreamTtsPlayback } from '../../voice/stream-tts-registry.js';
import type { VoiceAgentBridge } from '../../voice/voice-agent-bridge.js';
import type { VoiceMediaSession } from '../../voice/voice-media-session.js';
import { normalizeFlowUIBranchId } from '../../a2a/a2a-codec.js';
import { flowUIIsAbortError } from '../../a2a/a2a-stream.js';
import { resolveAgentIdentityImageSrc } from '../runtime/agent-identity-image.js';
import { sessionFiles } from '../runtime/conversation.js';
import type { FlowUiSendInput } from '../runtime/flow-ui-client.js';
import { FlowUIClient } from '../runtime/flow-ui-client.js';
import type { FlowUiBlock, FlowUiDocument, FlowUiHostLike, FlowUiPage, FlowUiRecord, FlowUiRenderContext } from '../runtime/flow-ui-store.js';
import { FlowUIStore } from '../runtime/flow-ui-store.js';
import { FlowUIHitlTransport, operatorTurnFromAction } from '../runtime/hitl-transport.js';
import { operatorHandoffFromTasks } from '../runtime/operator-handoff-from-task.js';
import { resolvedText } from '../runtime/templating.js';
import { deriveTurnToasts } from '../runtime/turn-activity.js';
import { emitDrawerMoveStart } from '../shell/drawer-move.js';
import { resolveFlowUITheme } from '../shell/resolve-theme.js';
import { flowUIText, hitlComposerSendLabel, resolveFlowUILocale } from '../utils/text.js';
import { flowUIVoiceSessionReady, stopFlowUIVoiceSession, toggleFlowUIVoiceSession } from '../voice/coordinator.js';
import { platformFlowUIStyles } from './platform-flow-ui.styles.js';
import {
    EDITING_CAPABILITIES,
    fileSources,
    flowRecord,
    formControlValue,
    presentText,
    requireHitlConversation,
} from './platform-flow-ui-helpers.js';
import type { FlowUiInteractionPolicy, FlowUiStatus, HitlMode } from './platform-flow-ui-helpers.js';
import { pageFillsViewport } from './flow-ui-page.js';
import './flow-ui-page.js';
import './flow-ui-conversation.js';
import './flow-ui-error-boundary.js';
import './flow-ui-turn-toasts.js';
import './flow-ui-files-panel.js';
import './flow-ui-task-controls.js';
import './flow-ui-share-menu.js';
import './flow-ui-drawer-controls.js';
import './flow-ui-run-trace.js';
import '../../components/platform-work-item-badge.js';

export type { FlowUiInteractionPolicy } from './platform-flow-ui-helpers.js';

export class PlatformFlowUI extends LitElement {
    declare flowId: string;
    declare branchId: string;
    declare embedId: string;
    declare contextId: string;
    declare baseUrl: string;
    declare display: string;
    declare profile: string;
    declare theme: string;
    declare locale: string;
    declare initialDocument: FlowUiDocument | null;
    declare readonly: boolean;
    declare credentials: string;
    declare workItemId: string;
    declare interactionPolicy: FlowUiInteractionPolicy | null;
    declare drawerExpanded: boolean;
    declare companyId: string;
    declare voiceBaseUrl: string;
    declare platformUiOrigin: string;
    declare getRequestHeaders: (() => Promise<Record<string, string>> | Record<string, string>) | null;
    declare getExtraMetadataVariables: (() => Record<string, unknown> | null) | null;
    declare assistantTitle: string;
    declare editing: boolean;
    declare selectedBlockId: string;
    declare pageId: string;
    declare sampleState: FlowUiRecord | null;
    declare voiceSessionActive: boolean;
    declare _status: FlowUiStatus;
    declare _hostComposerText: string;
    declare _hostComposerFiles: File[];
    store: FlowUIStore;
    client: FlowUIClient | null;
    private _error: unknown;
    private _hitl: FlowUIHitlTransport | null;
    private _generation: number;
    _voiceMedia: VoiceMediaSession | null;
    _voiceBridge: VoiceAgentBridge | null;
    private _unsubscribeStore: () => boolean;
    private _themeObserver: MutationObserver | null;
    private _onDrawerPointerDown: (event: PointerEvent) => void;

    static override properties = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        embedId: { type: String, attribute: 'embed-id' },
        contextId: { type: String, attribute: 'context-id' },
        baseUrl: { type: String, attribute: 'base-url' },
        display: { type: String, reflect: true },
        profile: { type: String, reflect: true },
        theme: { type: String, reflect: true },
        locale: { type: String },
        initialDocument: { attribute: false },
        readonly: { type: Boolean, reflect: true },
        credentials: { type: String },
        workItemId: { type: String, attribute: 'work-item-id' },
        interactionPolicy: { attribute: false },
        drawerExpanded: { type: Boolean, attribute: 'drawer-expanded', reflect: true },
        companyId: { type: String, attribute: 'company-id' },
        voiceBaseUrl: { type: String, attribute: 'voice-base-url' },
        platformUiOrigin: { type: String, attribute: 'platform-ui-origin' },
        getRequestHeaders: { attribute: false },
        getExtraMetadataVariables: { attribute: false },
        assistantTitle: { type: String, attribute: 'assistant-title' },
        editing: { type: Boolean, reflect: true },
        selectedBlockId: { type: String, attribute: 'selected-block-id' },
        pageId: { type: String, attribute: 'page-id' },
        sampleState: { attribute: false },
        voiceSessionActive: { state: true },
        _status: { state: true },
        _hostComposerText: { state: true },
        _hostComposerFiles: { state: true },
    };

    static override styles = platformFlowUIStyles;

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'default';
        this.embedId = '';
        this.contextId = '';
        this.baseUrl = '';
        this.display = 'page';
        this.profile = 'spa';
        this.theme = 'auto';
        this.locale = 'auto';
        this.initialDocument = null;
        this.readonly = false;
        this.credentials = 'include';
        this.workItemId = '';
        this.interactionPolicy = null;
        this.drawerExpanded = false;
        this.companyId = '';
        this.voiceBaseUrl = '';
        this.platformUiOrigin = '';
        this.getRequestHeaders = null;
        this.getExtraMetadataVariables = null;
        this.assistantTitle = '';
        this.editing = false;
        this.selectedBlockId = '';
        this.pageId = '';
        this.sampleState = null;
        this.voiceSessionActive = false;
        this.store = new FlowUIStore();
        this.client = null;
        this._status = 'idle';
        this._error = null;
        this._hostComposerText = '';
        this._hostComposerFiles = [];
        this._hitl = null;
        this._generation = 0;
        this._voiceMedia = null;
        this._voiceBridge = null;
        this._unsubscribeStore = this.store.subscribe(() => this._onStoreChange());
        this._themeObserver = null;
        this._onDrawerPointerDown = (event: PointerEvent) => {
            if (this.display !== 'drawer') return;
            if (!event.composedPath().some((node) => node instanceof Element && node.classList.contains('topbar'))) return;
            emitDrawerMoveStart(this, event);
        };
    }

    override connectedCallback() {
        super.connectedCallback();
        this.addEventListener('pointerdown', this._onDrawerPointerDown);
        if (typeof MutationObserver !== 'undefined' && globalThis.document?.documentElement) {
            this._themeObserver = new MutationObserver(() => this.requestUpdate());
            this._themeObserver.observe(globalThis.document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
        }
        queueMicrotask(() => this._start());
    }

    override disconnectedCallback() {
        this.removeEventListener('pointerdown', this._onDrawerPointerDown);
        this._themeObserver?.disconnect();
        this._themeObserver = null;
        this._generation += 1;
        this._dispose();
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>) {
        if (!this.isConnected) return;
        if (this.editing) {
            if (changed.has('initialDocument') && this.initialDocument !== null) this.store.setDocument(this.initialDocument);
            if (changed.has('sampleState')) this.store.setState(this.sampleState === null ? {} : this.sampleState);
            this._syncHostPage();
            return;
        }
        if (!this.client) return;
        if (changed.has('initialDocument') && this.initialDocument !== null && this._status === 'ready') {
            this.store.setDocument(this.initialDocument);
        }
        if (changed.has('pageId')) this._syncHostPage();
        const target = this.client.target;
        const hostContextId = typeof this.contextId === 'string' ? this.contextId.trim() : '';
        const drift = (changed.has('flowId') && this.flowId !== target.flowId)
            || (changed.has('embedId') && this.embedId !== target.embedId)
            || (changed.has('branchId') && normalizeFlowUIBranchId(this.branchId) !== target.branchId)
            || (changed.has('contextId') && hostContextId !== '' && hostContextId !== this.client.contextId);
        if (drift) void this._restart();
    }

    private _emit(name: string, detail: FlowUiRecord = {}) {
        this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true, detail }));
    }

    _embedPageUrl() {
        const embedId = typeof this.embedId === 'string' ? this.embedId.trim() : '';
        if (embedId === '') return '';
        return `${window.location.origin}/flow-embed-page?embed=${encodeURIComponent(embedId)}`;
    }

    _dispose() {
        this._hitl?.dispose();
        this._hitl = null;
        void stopFlowUIVoiceSession(this);
        this.client?.dispose();
        this.client = null;
        this._status = 'idle';
    }

    async _restart() {
        const generation = ++this._generation;
        this._dispose();
        if (generation !== this._generation || !this.isConnected) return;
        await this._start();
    }

    /** Холст редактора: документ и тестовый state приходят от хоста, сети и Tasks нет. */
    _startEditing() {
        if (this.initialDocument === null) throw new Error('platform-flow-ui: editing requires initialDocument');
        this.store.setState(this.sampleState === null ? {} : this.sampleState);
        this.store.setDocument(this.initialDocument);
        this._syncHostPage();
        this._status = 'ready';
    }

    /** Вкладка страницы редактора — после setDocument store ещё может держать start_page_id. */
    _syncHostPage() {
        if (this.pageId === '' || this.store.document === null) return;
        if (this.store.pageId === this.pageId || !this.store.page(this.pageId)) return;
        this.store.navigate(this.pageId);
    }

    _fitsDocument() {
        return this.editing === true || this.initialDocument !== null;
    }

    async _start() {
        await this.updateComplete;
        if (!this.isConnected || this.client) return;
        if (this.editing) {
            this._startEditing();
            return;
        }
        const generation = this._generation;
        const hitl = this.profile === 'operator_handoff';
        try {
            if (hitl) {
                this._assertHitlConfig();
                const conversation = requireHitlConversation(this.interactionPolicy);
                this.flowId = conversation.flow_id;
                this.contextId = conversation.context_id;
                if (typeof conversation.branch_id === 'string' && conversation.branch_id.trim() !== '') this.branchId = conversation.branch_id;
            }
            const client = new FlowUIClient({
                baseUrl: this.baseUrl,
                flowId: this.flowId,
                embedId: this.embedId,
                branchId: this.branchId,
                credentials: this.credentials === 'omit' ? 'omit' : 'include',
                getHeaders: () => (typeof this.getRequestHeaders === 'function' ? this.getRequestHeaders() : {}),
                getVariables: () => (typeof this.getExtraMetadataVariables === 'function' ? this.getExtraMetadataVariables() : null),
                store: this.store,
            });
            client.on('frame', (frame) => this._emit('flow-ui-a2a-frame', { contextId: client.contextId, frame }));
            client.on('error', (error) => this._emit('flow-ui-error', { error: error instanceof Error ? error : new Error(String(error)) }));
            this.client = client;
            this._status = 'loading';
            if (hitl) {
                this._hitl = new FlowUIHitlTransport({
                    workItemId: this.workItemId,
                    conversation: requireHitlConversation(this.interactionPolicy),
                    mode: this.interactionPolicy?.mode,
                    baseUrl: this.baseUrl,
                    credentials: this.credentials === 'omit' ? 'omit' : 'include',
                    getHeaders: () => (typeof this.getRequestHeaders === 'function' ? this.getRequestHeaders() : {}),
                });
                await this._hitl.attach(client);
            } else {
                const trimmedContextId = this.contextId.trim();
                await client.open({ contextId: trimmedContextId.length === 0 ? null : trimmedContextId, document: this.initialDocument });
            }
            if (generation !== this._generation || this.client !== client) return;
            this.contextId = client.contextId === null ? '' : client.contextId;
            this._syncHostPage();
            this._status = 'ready';
            this._emit('flow-ui-ready', { contextId: client.contextId });
            this._emit('flow-ui-identity-changed', { image_url: this._identityImageUrl() });
        } catch (error) {
            if (generation !== this._generation) return;
            if (flowUIIsAbortError(error)) return;
            this._error = error;
            this._status = 'error';
            this._emit('flow-ui-error', { error });
        }
    }

    private _assertHitlConfig() {
        if (typeof this.workItemId !== 'string' || this.workItemId.trim() === '') throw new Error('platform-flow-ui: operator_handoff requires work-item-id');
        const policy = this.interactionPolicy;
        if (!policy || typeof policy !== 'object') throw new Error('platform-flow-ui: operator_handoff requires interactionPolicy');
        if (policy.mode !== 'takeover' && policy.mode !== 'single_reply') throw new Error(`platform-flow-ui: unsupported HITL mode ${JSON.stringify(policy.mode)}`);
        if (!policy.conversation || typeof policy.conversation !== 'object') throw new Error('platform-flow-ui: interactionPolicy.conversation required');
        for (const key of ['flow_id', 'context_id', 'session_id', 'a2a_task_id'] as const) {
            if (typeof policy.conversation[key] !== 'string' || policy.conversation[key].trim() === '') throw new Error(`platform-flow-ui: conversation.${key} required`);
        }
    }

    _onStoreChange() {
        if (this.client && this.client.contextId && this.contextId !== this.client.contextId) this.contextId = this.client.contextId;
        this.requestUpdate();
        if (this._status === 'ready') this._emit('flow-ui-state-changed', { state: this.store.state, pageId: this.store.pageId });
    }

    get resolvedLocale(): string {
        return resolveFlowUILocale(this.locale);
    }

    get interface(): FlowUiRecord | null {
        return this.store.interface;
    }

    get capabilities(): FlowUiRecord {
        if (this.editing) return EDITING_CAPABILITIES;
        const capabilities = flowRecord(this.interface === null ? undefined : this.interface.capabilities);
        if (!capabilities) throw new Error('platform-flow-ui: capabilities require interface');
        return capabilities;
    }

    get hitlMode(): HitlMode | null {
        if (this.profile !== 'operator_handoff') return null;
        const mode = this.interactionPolicy?.mode;
        if (mode !== 'single_reply' && mode !== 'takeover') throw new Error(`platform-flow-ui: operator_handoff requires HITL mode, got ${JSON.stringify(mode)}`);
        return mode;
    }

    /** Ожидание оператора на стороне пользователя (interrupt operator_task в активном Task). */
    get userHandoff() {
        if (this.profile === 'operator_handoff') return null;
        return operatorHandoffFromTasks(this.store.tasks.tasksById, this.store.tasks.taskOrder);
    }

    get effectiveReadonly() {
        if (this.readonly || this.editing) return true;
        if (this.profile === 'operator_handoff') return this.interactionPolicy?.can_send !== true;
        const viewer = flowRecord(this.interface === null ? undefined : this.interface.viewer);
        if (viewer?.can_interact === false) return true;
        return this.userHandoff?.mode === 'single_reply';
    }

    _identityImageUrl() {
        return resolveAgentIdentityImageSrc({
            document: this.store.document,
            flowIdentity: isPlainRecord(this.interface?.flow_identity) ? this.interface.flow_identity : null,
            platformUiOrigin: this.platformUiOrigin,
        });
    }

    /** Контекст рендера блоков страницы и карточек ленты. */
    blockContext(): FlowUiRenderContext {
        return {
            host: this,
            store: this.store,
            state: this.store.state,
            slots: this.store.slots,
            locale: this.resolvedLocale,
            readonly: this.effectiveReadonly,
            editing: this.editing,
            selectedBlockId: this.editing && this.selectedBlockId !== '' ? this.selectedBlockId : null,
            platformUiOrigin: this.platformUiOrigin,
            flowIdentity: isPlainRecord(this.interface?.flow_identity) ? this.interface.flow_identity : null,
            pending: this.store.turnActive || this.store.streaming,
            fieldErrors: this.store.fieldErrors,
            uploading: this.store.uploading,
            // Страница и лента перерисовываются по подписке на store, а не по requestUpdate хоста
            requestUpdate: () => this.store.emitChange(),
            fieldValue: (field: unknown) => this.store.fieldValue(presentText(field)),
            onFieldChange: (field: unknown, value: unknown) => this.setFieldValue(presentText(field), value),
            onAction: (block: FlowUiBlock, action: unknown) => {
                const record = flowRecord(action);
                if (record === undefined) {
                    throw new Error('platform-flow-ui: action required');
                }
                void this.submitAction(block, record);
            },
            onNavigate: (pageId: unknown) => this.navigate(presentText(pageId)),
            onOpenUrl: (url: string) => { window.open(url, '_blank', 'noopener,noreferrer'); },
            onPrompt: (text: string) => { void this.sendText(text, []); },
            onFilesSelected: (block: FlowUiBlock, files: unknown) => { void this.uploadFieldFiles(block, files); },
            onHtmlBridgeEvent: null,
        };
    }

    setFieldValue(field: string, value: unknown) {
        this.store.setEdit(field, value);
    }

    /**
     * ui-action: значения полей страницы + payload действия одним data Part.
     * У оператора (``operator_handoff``) ход уходит текстом HITL-транспорта: у него нет A2A-хода.
     */
    async submitAction(block: FlowUiBlock, action: FlowUiRecord) {
        if (this.effectiveReadonly) return;
        const { fields, missing } = this.store.collectFields();
        this.store.setFieldErrors(missing);
        if (missing.size > 0) return;
        if (this._hitl) {
            await this._hitl.send(operatorTurnFromAction(action, fields, this.store.inputBlocks(), this.resolvedLocale as 'ru' | 'en'));
            this.store.clearEdits(Object.keys(fields));
            return;
        }
        await this._submit({ action: { action: action.name, source: block.block_id, fields, payload: recordField(action.payload, 'flow-ui action payload') } });
    }

    async sendText(text: string, files: File[] | FlowUiRecord[]) {
        if (this.effectiveReadonly) return;
        if (this._hitl) {
            await this._hitl.send({ text, files });
            return;
        }
        const refs = await this._uploadFiles(files, '');
        await this._submit({ text, files: fileSources(refs) });
    }

    private async _submit(message: FlowUiSendInput) {
        const client = this.client;
        if (!client) throw new Error('platform-flow-ui: client is not ready');
        this._emit('flow-ui-submit-start', { contextId: client.contextId });
        let task = null;
        try {
            task = await client.send(message);
        } finally {
            this._emit('flow-ui-submit-end', { contextId: client.contextId, taskId: task ? task.id : null });
        }
    }

    private async _uploadFiles(files: unknown, field: string) {
        const list = Array.isArray(files) ? files : [];
        if (list.length === 0) return [];
        if (this.capabilities.files !== true) throw new Error('flow-ui: file upload is disabled for this interface');
        const flowId = this.interface?.flow_id;
        if (typeof flowId !== 'string' || flowId === '') throw new Error('flow-ui: interface flow_id is required for file upload');
        const headers = typeof this.getRequestHeaders === 'function' ? await this.getRequestHeaders() : {};
        return resolvePlatformFileRefs(list, {
            credentials: this.credentials === 'omit' ? 'omit' : 'include',
            headers,
            filesApiBase: `${this.baseUrl.replace(/\/+$/, '')}/api/v1/files`,
            buildSpec: () => buildFlowSessionFileCreateSpecJson({ flowId, sessionId: `${flowId}:${this.client === null || this.client.contextId === null ? '' : this.client.contextId}` }),
            onProgress: (progress) => {
                const record = flowRecord(progress);
                if (record === undefined) {
                    throw new Error('platform-flow-ui: file progress required');
                }
                this._emit('flow-ui-file-progress', { ...record, field });
            },
        });
    }

    async uploadFieldFiles(block: FlowUiBlock, files: unknown) {
        const field = presentText(block.field);
        this.store.setUploading(field, true);
        try {
            const refs = await this._uploadFiles(files, field);
            const current = this.store.fieldValue(field);
            const merged = block.multiple === true ? [...(Array.isArray(current) ? current : []), ...refs] : refs.slice(0, 1);
            this.setFieldValue(field, merged);
            this._emit('flow-ui-files-ready', { field, files: merged });
        } finally {
            this.store.setUploading(field, false);
        }
    }

    navigate(pageId: string) {
        this.store.navigate(pageId);
        this._emit('flow-ui-navigation', { pageId });
    }

    async startNewContext() {
        if (!this.client) throw new Error('platform-flow-ui: client is not ready');
        stopStreamTtsPlayback();
        const contextId = this.client.newContext();
        this.contextId = contextId === null ? '' : contextId;
        this._emit('flow-ui-ready', { contextId });
        return contextId;
    }

    cancelActiveTask() {
        stopStreamTtsPlayback();
        return this.client?.cancel();
    }

    applyA2AFrame(frame: unknown) {
        if (!this.client) {
            return undefined;
        }
        const record = flowRecord(frame);
        if (record === undefined) {
            throw new Error('platform-flow-ui: A2A frame required');
        }
        return this.client.applyFrame(record);
    }

    createShare(options?: { permission?: string; redactedPaths?: string[]; expiresInSeconds?: number }) {
        if (!this.client) throw new Error('platform-flow-ui: client is not ready');
        return this.client.createShare(options);
    }

    revokeShare(grantId: unknown) {
        if (!this.client) throw new Error('platform-flow-ui: client is not ready');
        return this.client.revokeShare(grantId);
    }

    stopVoice() {
        void stopFlowUIVoiceSession(this);
        this._emit('flow-ui-stop-voice');
    }

    voiceSessionReady() {
        return flowUIVoiceSessionReady(this);
    }

    toggleVoiceSession() {
        return toggleFlowUIVoiceSession(this);
    }

    openBrowserPreview({ url, screenshot, status }: { url?: unknown; screenshot?: unknown; status?: unknown }) {
        this._emit('browser-preview-open', { viewerUrl: screenshot, sessionId: `${this.flowId}:${this.contextId}`, currentUrl: url, status });
    }

    _chromeMode() {
        if (this.editing || this.initialDocument !== null || this.profile === 'editor_test' || this.profile === 'operator_handoff') return 'none';
        const document = this.store.document;
        if (document !== null && document.pages.length > 1) return 'full';
        if (this.display === 'drawer') return 'minimal';
        if (this.profile === 'spa' || this.display === 'panel') {
            const viewer = flowRecord(this.interface === null ? undefined : this.interface.viewer);
            return viewer?.can_share === true ? 'minimal' : 'none';
        }
        return 'full';
    }

    private _brandTitle(page: FlowUiPage) {
        const override = typeof this.assistantTitle === 'string' ? this.assistantTitle.trim() : '';
        if (override !== '') return override;
        const look = flowRecord(this.interface === null ? undefined : this.interface.look);
        if (look && typeof look.assistant_title === 'string' && look.assistant_title.trim() !== '') return look.assistant_title;
        const identity = flowRecord(this.interface === null ? undefined : this.interface.flow_identity);
        if (identity && typeof identity.title === 'string' && identity.title.trim() !== '') return identity.title;
        const pageTitle = resolvedText(page.title, this.store.state);
        if (pageTitle !== null && pageTitle !== '') return pageTitle;
        return getPlatformBrandBootstrap()?.platformName ?? 'AI';
    }

    private _topActions(chromeMode: string, locale: string) {
        if (chromeMode === 'none') return nothing;
        const settings = this.store.conversationSettings();
        const files = settings.show_files_panel === false || this.capabilities.files === false ? [] : sessionFiles(this.store);
        const viewer = flowRecord(this.interface === null ? undefined : this.interface.viewer);
        const share = html`<flow-ui-share-menu .host=${this} locale=${locale} ?can-share=${viewer?.can_share === true} embed-page-url=${this._embedPageUrl()}></flow-ui-share-menu>`;
        return html`<div class="top-actions">
            ${files.length > 0 ? html`<flow-ui-files-panel .files=${files} locale=${locale}></flow-ui-files-panel>` : nothing}
            ${this.effectiveReadonly && chromeMode === 'full' ? html`<span class="readonly-pill">${flowUIText(locale, 'read_only')}</span>` : nothing}
            <flow-ui-task-controls .active=${this.store.taskRunning} .canCancel=${this.capabilities.cancel === true && !this.effectiveReadonly} locale=${locale} @task-cancel=${() => this.cancelActiveTask()}></flow-ui-task-controls>
            ${this.display === 'drawer' ? this._drawerControls(locale, share, true) : share}
        </div>`;
    }

    /** Expand/close drawer обрамляют содержимое (share-меню); с упавшим интерфейсом остаётся только close. */
    private _drawerControls(locale: string, content: unknown, showExpand: boolean) {
        return html`<flow-ui-drawer-controls .expanded=${this.drawerExpanded} ?show-expand=${showExpand} locale=${locale} platform-ui-origin=${this.platformUiOrigin}
            @drawer-expand-toggle=${() => this._emit('flow-ui-drawer-expand-toggle', { expanded: !this.drawerExpanded })} @drawer-close=${() => this._emit('flow-ui-drawer-close')}>${content}</flow-ui-drawer-controls>`;
    }

    private _waitingBanner(locale: string) {
        const handoff = this.userHandoff;
        if (!handoff) return nothing;
        return html`<div class="input-required-banner" role="status">
            ${handoff.workItemId ? html`<platform-work-item-badge work-item-id=${String(handoff.workItemId)} size="sm"></platform-work-item-badge>` : nothing}
            <span>${flowUIText(locale, handoff.mode === 'takeover' ? 'hitl_banner_takeover' : 'hitl_banner_single_reply')}</span>
        </div>`;
    }

    /** Композер оператора, когда у интерфейса нет блока conversation. */
    private _hostComposer(locale: string, page: FlowUiPage | null) {
        if (this.profile !== 'operator_handoff' || this.effectiveReadonly || (page !== null && pageFillsViewport(page))) return nothing;
        const sendLabel = hitlComposerSendLabel(locale, this.hitlMode);
        const canSend = this._hostComposerText.trim() !== '' || this._hostComposerFiles.length > 0;
        return html`<div class="hitl-host-composer">
            <textarea data-canon="composer" .value=${this._hostComposerText} placeholder=${flowUIText(locale, 'composer_placeholder')}
                @input=${(event: Event) => { this._hostComposerText = formControlValue(event); }}></textarea>
            <div class="hitl-host-composer-row">
                <input type="file" multiple @change=${(event: Event) => {
                    const input = event.target;
                    if (!(input instanceof HTMLInputElement)) {
                        throw new Error('platform-flow-ui: file input required');
                    }
                    const picked = input.files;
                    this._hostComposerFiles = [...this._hostComposerFiles, ...(picked === null ? [] : Array.from(picked))];
                    input.value = '';
                }}>
                <button type="button" class="hitl-host-send" ?disabled=${!canSend} aria-label=${sendLabel}
                    @click=${async () => {
                        const text = this._hostComposerText;
                        const files = this._hostComposerFiles;
                        this._hostComposerText = '';
                        this._hostComposerFiles = [];
                        await this.sendText(text, files);
                    }}>${sendLabel}</button>
            </div>
        </div>`;
    }

    override render() {
        const locale = this.resolvedLocale;
        this.setAttribute('data-resolved-theme', resolveFlowUITheme(this.theme, globalThis.document));
        if (this._status === 'error') {
            const boundary = html`<flow-ui-error-boundary .error=${this._error} locale=${locale}></flow-ui-error-boundary>`;
            if (this.display !== 'drawer') return boundary;
            return html`<div class="shell" data-chrome="minimal"><header class="topbar"><div class="top-actions">${this._drawerControls(locale, nothing, false)}</div></header><main class="viewport">${boundary}</main></div>`;
        }
        if (this._status !== 'ready' || !this.store.document) {
            return html`<div class="skeleton" aria-busy="true" aria-label=${flowUIText(locale, 'loading_interface')}><div class="shimmer"></div><div class="shimmer"></div><div class="shimmer"></div></div>`;
        }
        const page = this.store.page(this.store.pageId);
        if (page === null) {
            throw new Error('platform-flow-ui: current page is missing');
        }
        const chromeMode = this._chromeMode();
        const fitDocument = this._fitsDocument();
        this.setAttribute('data-chrome', chromeMode);
        this.setAttribute('data-fit', fitDocument ? 'document' : 'viewport');
        const topActions = this._topActions(chromeMode, locale);
        const showTopbar = chromeMode === 'full' || topActions !== nothing;
        const settings = this.store.conversationSettings();
        const toasts = this.editing || pageFillsViewport(page) ? [] : deriveTurnToasts(this.store, settings, locale, { allowCancel: this.capabilities.cancel === true && !this.effectiveReadonly });
        const statusLabel = this.initialDocument !== null
            ? flowUIText(locale, 'status_preview')
            : (this.effectiveReadonly ? flowUIText(locale, 'status_read_only') : (this.store.error ? flowUIText(locale, 'status_error') : flowUIText(locale, 'status_live')));
        return html`<div class="shell" data-chrome=${chromeMode}>
            ${showTopbar ? html`<header class="topbar">
                ${chromeMode === 'full' ? html`<div class="brand">
                    <span class="mark" aria-hidden="true"><img src=${this._identityImageUrl()} alt=""></span>
                    <span class="brand-label">${this._brandTitle(page)}</span>
                </div>` : nothing}
                ${chromeMode === 'full' && this.store.document.pages.length > 1 ? html`<nav aria-label=${flowUIText(locale, 'pages_nav')}>
                    ${this.store.document.pages.map((item: FlowUiPage) => html`<button type="button" class="page" aria-current=${item.page_id === page.page_id ? 'page' : nothing} @click=${() => this.navigate(item.page_id)}>${resolvedText(item.title, this.store.state) || item.page_id}</button>`)}
                </nav>` : nothing}
                ${topActions}
            </header>` : nothing}
            <main class="viewport">
                ${this._waitingBanner(locale)}
                <flow-ui-page .host=${this} .page=${page} .selectedBlockId=${this.editing ? this.selectedBlockId : ''} ?editing=${this.editing} ?fluid=${fitDocument} ?show-title=${chromeMode !== 'full' && !pageFillsViewport(page)}></flow-ui-page>
                ${this._hostComposer(locale, page)}
            </main>
            ${chromeMode === 'full' ? html`<footer class="statusbar"><span class="status"><span class="dot ${this.store.error ? 'error' : ''}"></span>${statusLabel}</span></footer>` : nothing}
            ${toasts.length > 0 ? html`<flow-ui-turn-toasts .toasts=${toasts} locale=${locale} @turn-toast-cancel=${() => this.cancelActiveTask()}></flow-ui-turn-toasts>` : nothing}
        </div>`;
    }
}
if (!customElements.get('platform-flow-ui')) customElements.define('platform-flow-ui', PlatformFlowUI);
