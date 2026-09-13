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

import { LitElement, html, nothing } from '../../lit-shim.js';
import { buildFlowSessionFileCreateSpecJson } from '../../utils/file-create-spec.js';
import { resolvePlatformFileRefs } from '../../utils/platform-file-upload.js';
import { stopStreamTtsPlayback } from '../../voice/stream-tts-registry.js';
import { normalizeFlowUIBranchId } from '../protocol/a2a-codec.js';
import { flowUIIsAbortError } from '../protocol/a2a-stream.js';
import { resolveAgentIdentityImageSrc } from '../runtime/agent-identity-image.js';
import { sessionFiles } from '../runtime/conversation.js';
import { FlowUIClient } from '../runtime/flow-ui-client.js';
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

const EDITING_CAPABILITIES = Object.freeze({ cancel: false, files: false, voice: false });

export class PlatformFlowUI extends LitElement {
    static properties = {
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

    static styles = platformFlowUIStyles;

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
        this._onDrawerPointerDown = (event) => {
            if (this.display !== 'drawer') return;
            if (!event.composedPath().some((node) => node instanceof Element && node.classList.contains('topbar'))) return;
            emitDrawerMoveStart(this, event);
        };
    }

    connectedCallback() {
        super.connectedCallback();
        this.addEventListener('pointerdown', this._onDrawerPointerDown);
        if (typeof MutationObserver !== 'undefined' && globalThis.document?.documentElement) {
            this._themeObserver = new MutationObserver(() => this.requestUpdate());
            this._themeObserver.observe(globalThis.document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
        }
        queueMicrotask(() => this._start());
    }

    disconnectedCallback() {
        this.removeEventListener('pointerdown', this._onDrawerPointerDown);
        this._themeObserver?.disconnect();
        this._themeObserver = null;
        this._generation += 1;
        this._dispose();
        super.disconnectedCallback();
    }

    updated(changed) {
        if (!this.isConnected) return;
        if (this.editing) {
            if (changed.has('initialDocument') && this.initialDocument !== null) this.store.setDocument(this.initialDocument);
            if (changed.has('sampleState')) this.store.setState(this.sampleState ?? {});
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
        const drift = (changed.has('flowId') && (this.flowId || '') !== (target.flowId || ''))
            || (changed.has('embedId') && (this.embedId || '') !== (target.embedId || ''))
            || (changed.has('branchId') && normalizeFlowUIBranchId(this.branchId) !== target.branchId)
            || (changed.has('contextId') && hostContextId !== '' && hostContextId !== this.client.contextId);
        if (drift) void this._restart();
    }

    _emit(name, detail = {}) {
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
        this.store.setState(this.sampleState ?? {});
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
                const conversation = this.interactionPolicy.conversation;
                this.flowId = conversation.flow_id;
                this.contextId = conversation.context_id;
                if (typeof conversation.branch_id === 'string' && conversation.branch_id.trim() !== '') this.branchId = conversation.branch_id;
            }
            const client = new FlowUIClient({
                baseUrl: this.baseUrl,
                flowId: this.flowId,
                embedId: this.embedId,
                branchId: this.branchId,
                credentials: this.credentials,
                getHeaders: () => (typeof this.getRequestHeaders === 'function' ? this.getRequestHeaders() : {}),
                getVariables: () => (typeof this.getExtraMetadataVariables === 'function' ? this.getExtraMetadataVariables() : null),
                store: this.store,
            });
            client.on('frame', (frame) => this._emit('flow-ui-a2a-frame', { contextId: client.contextId, frame }));
            client.on('error', (error) => this._emit('flow-ui-error', { error }));
            this.client = client;
            this._status = 'loading';
            if (hitl) {
                this._hitl = new FlowUIHitlTransport({
                    workItemId: this.workItemId,
                    conversation: this.interactionPolicy.conversation,
                    mode: this.interactionPolicy.mode,
                    baseUrl: this.baseUrl,
                    credentials: this.credentials,
                    getHeaders: () => (typeof this.getRequestHeaders === 'function' ? this.getRequestHeaders() : {}),
                });
                await this._hitl.attach(client);
            } else {
                await client.open({ contextId: this.contextId.trim() || null, document: this.initialDocument });
            }
            if (generation !== this._generation || this.client !== client) return;
            this.contextId = client.contextId;
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

    _assertHitlConfig() {
        if (typeof this.workItemId !== 'string' || this.workItemId.trim() === '') throw new Error('platform-flow-ui: operator_handoff requires work-item-id');
        const policy = this.interactionPolicy;
        if (!policy || typeof policy !== 'object') throw new Error('platform-flow-ui: operator_handoff requires interactionPolicy');
        if (policy.mode !== 'takeover' && policy.mode !== 'single_reply') throw new Error(`platform-flow-ui: unsupported HITL mode ${JSON.stringify(policy.mode)}`);
        if (!policy.conversation || typeof policy.conversation !== 'object') throw new Error('platform-flow-ui: interactionPolicy.conversation required');
        for (const key of ['flow_id', 'context_id', 'session_id', 'a2a_task_id']) {
            if (typeof policy.conversation[key] !== 'string' || policy.conversation[key].trim() === '') throw new Error(`platform-flow-ui: conversation.${key} required`);
        }
    }

    _onStoreChange() {
        if (this.client && this.client.contextId && this.contextId !== this.client.contextId) this.contextId = this.client.contextId;
        this.requestUpdate();
        if (this._status === 'ready') this._emit('flow-ui-state-changed', { state: this.store.state, pageId: this.store.pageId });
    }

    get resolvedLocale() {
        return resolveFlowUILocale(this.locale);
    }

    get interface() {
        return this.store.interface;
    }

    get capabilities() {
        if (this.editing) return EDITING_CAPABILITIES;
        const capabilities = this.interface?.capabilities;
        if (!capabilities) throw new Error('platform-flow-ui: capabilities require interface');
        return capabilities;
    }

    get hitlMode() {
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
        if (this.interface?.viewer?.can_interact === false) return true;
        return this.userHandoff?.mode === 'single_reply';
    }

    _identityImageUrl() {
        return resolveAgentIdentityImageSrc({
            document: this.store.document,
            flowIdentity: this.interface?.flow_identity ?? null,
            platformUiOrigin: this.platformUiOrigin,
        });
    }

    /** Контекст рендера блоков страницы и карточек ленты. */
    blockContext() {
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
            flowIdentity: this.interface?.flow_identity ?? null,
            pending: this.store.turnActive || this.store.streaming,
            fieldErrors: this.store.fieldErrors,
            uploading: this.store.uploading,
            // Страница и лента перерисовываются по подписке на store, а не по requestUpdate хоста
            requestUpdate: () => this.store.emitChange(),
            fieldValue: (field) => this.store.fieldValue(field),
            onFieldChange: (field, value) => this.setFieldValue(field, value),
            onAction: (block, action) => { void this.submitAction(block, action); },
            onNavigate: (pageId) => this.navigate(pageId),
            onOpenUrl: (url) => window.open(url, '_blank', 'noopener,noreferrer'),
            onPrompt: (text) => { void this.sendText(text, []); },
            onFilesSelected: (block, files) => { void this.uploadFieldFiles(block, files); },
            onHtmlBridgeEvent: null,
        };
    }

    setFieldValue(field, value) {
        this.store.setEdit(field, value);
    }

    /**
     * ui-action: значения полей страницы + payload действия одним data Part.
     * У оператора (``operator_handoff``) ход уходит текстом HITL-транспорта: у него нет A2A-хода.
     */
    async submitAction(block, action) {
        if (this.effectiveReadonly) return;
        const { fields, missing } = this.store.collectFields();
        this.store.setFieldErrors(missing);
        if (missing.size > 0) return;
        if (this._hitl) {
            await this._hitl.send(operatorTurnFromAction(action, fields, this.store.inputBlocks(), this.resolvedLocale));
            this.store.clearEdits(Object.keys(fields));
            return;
        }
        await this._submit({ action: { action: action.name, source: block.block_id, fields, payload: action.payload ?? {} } });
    }

    async sendText(text, files) {
        if (this.effectiveReadonly) return;
        if (this._hitl) {
            await this._hitl.send({ text, files });
            return;
        }
        const refs = await this._uploadFiles(files, '');
        await this._submit({ text, files: refs });
    }

    async _submit(message) {
        this._emit('flow-ui-submit-start', { contextId: this.client.contextId });
        let task = null;
        try {
            task = await this.client.send(message);
        } finally {
            this._emit('flow-ui-submit-end', { contextId: this.client.contextId, taskId: task ? task.id : null });
        }
    }

    async _uploadFiles(files, field) {
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
            buildSpec: () => buildFlowSessionFileCreateSpecJson({ flowId, sessionId: `${flowId}:${this.client.contextId}` }),
            onProgress: (progress) => this._emit('flow-ui-file-progress', { ...progress, field }),
        });
    }

    async uploadFieldFiles(block, files) {
        this.store.setUploading(block.field, true);
        try {
            const refs = await this._uploadFiles(files, block.field);
            const current = this.store.fieldValue(block.field);
            const merged = block.multiple ? [...(Array.isArray(current) ? current : []), ...refs] : refs.slice(0, 1);
            this.setFieldValue(block.field, merged);
            this._emit('flow-ui-files-ready', { field: block.field, files: merged });
        } finally {
            this.store.setUploading(block.field, false);
        }
    }

    navigate(pageId) {
        this.store.navigate(pageId);
        this._emit('flow-ui-navigation', { pageId });
    }

    async startNewContext() {
        if (!this.client) throw new Error('platform-flow-ui: client is not ready');
        stopStreamTtsPlayback();
        const contextId = this.client.newContext();
        this.contextId = contextId;
        this._emit('flow-ui-ready', { contextId });
        return contextId;
    }

    cancelActiveTask() {
        stopStreamTtsPlayback();
        return this.client?.cancel();
    }

    applyA2AFrame(frame) {
        return this.client?.applyFrame(frame);
    }

    createShare(options) {
        if (!this.client) throw new Error('platform-flow-ui: client is not ready');
        return this.client.createShare(options);
    }

    revokeShare(grantId) {
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

    openBrowserPreview({ url, screenshot, status }) {
        this._emit('browser-preview-open', { viewerUrl: screenshot, sessionId: `${this.flowId}:${this.contextId}`, currentUrl: url, status });
    }

    _chromeMode() {
        if (this.editing || this.initialDocument !== null || this.profile === 'editor_test' || this.profile === 'operator_handoff') return 'none';
        if (this.store.document.pages.length > 1) return 'full';
        if (this.display === 'drawer') return 'minimal';
        if (this.profile === 'spa' || this.display === 'panel') return this.interface?.viewer?.can_share === true ? 'minimal' : 'none';
        return 'full';
    }

    _brandTitle(page) {
        const override = typeof this.assistantTitle === 'string' ? this.assistantTitle.trim() : '';
        if (override !== '') return override;
        const look = this.interface?.look;
        if (look && typeof look.assistant_title === 'string' && look.assistant_title.trim() !== '') return look.assistant_title;
        const identity = this.interface?.flow_identity;
        if (identity && typeof identity.title === 'string' && identity.title.trim() !== '') return identity.title;
        const pageTitle = resolvedText(page.title, this.store.state) ?? '';
        return pageTitle !== '' ? pageTitle : 'Linnex';
    }

    _topActions(chromeMode, locale) {
        if (chromeMode === 'none') return nothing;
        const settings = this.store.conversationSettings();
        const files = settings.show_files_panel === false || this.capabilities.files === false ? [] : sessionFiles(this.store);
        const share = html`<flow-ui-share-menu .host=${this} locale=${locale} ?can-share=${this.interface?.viewer?.can_share === true} embed-page-url=${this._embedPageUrl()}></flow-ui-share-menu>`;
        return html`<div class="top-actions">
            ${files.length > 0 ? html`<flow-ui-files-panel .files=${files} locale=${locale}></flow-ui-files-panel>` : nothing}
            ${this.effectiveReadonly && chromeMode === 'full' ? html`<span class="readonly-pill">${flowUIText(locale, 'read_only')}</span>` : nothing}
            <flow-ui-task-controls .active=${this.store.taskRunning} .canCancel=${this.capabilities.cancel === true && !this.effectiveReadonly} locale=${locale} @task-cancel=${() => this.cancelActiveTask()}></flow-ui-task-controls>
            ${this.display === 'drawer' ? this._drawerControls(locale, share, true) : share}
        </div>`;
    }

    /** Expand/close drawer обрамляют содержимое (share-меню); с упавшим интерфейсом остаётся только close. */
    _drawerControls(locale, content, showExpand) {
        return html`<flow-ui-drawer-controls .expanded=${this.drawerExpanded} ?show-expand=${showExpand} locale=${locale} platform-ui-origin=${this.platformUiOrigin}
            @drawer-expand-toggle=${() => this._emit('flow-ui-drawer-expand-toggle', { expanded: !this.drawerExpanded })} @drawer-close=${() => this._emit('flow-ui-drawer-close')}>${content}</flow-ui-drawer-controls>`;
    }

    _waitingBanner(locale) {
        const handoff = this.userHandoff;
        if (!handoff) return nothing;
        return html`<div class="input-required-banner" role="status">
            ${handoff.workItemId ? html`<platform-work-item-badge work-item-id=${handoff.workItemId} size="sm"></platform-work-item-badge>` : nothing}
            <span>${flowUIText(locale, handoff.mode === 'takeover' ? 'hitl_banner_takeover' : 'hitl_banner_single_reply')}</span>
        </div>`;
    }

    /** Композер оператора, когда у интерфейса нет блока conversation. */
    _hostComposer(locale, page) {
        if (this.profile !== 'operator_handoff' || this.effectiveReadonly || pageFillsViewport(page)) return nothing;
        const sendLabel = hitlComposerSendLabel(locale, this.hitlMode);
        const canSend = this._hostComposerText.trim() !== '' || this._hostComposerFiles.length > 0;
        return html`<div class="hitl-host-composer">
            <textarea data-canon="composer" .value=${this._hostComposerText} placeholder=${flowUIText(locale, 'composer_placeholder')}
                @input=${(event) => { this._hostComposerText = event.target.value; }}></textarea>
            <div class="hitl-host-composer-row">
                <input type="file" multiple @change=${(event) => { this._hostComposerFiles = [...this._hostComposerFiles, ...event.target.files]; event.target.value = ''; }}>
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

    render() {
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
                    ${this.store.document.pages.map((item) => html`<button type="button" class="page" aria-current=${item.page_id === page.page_id ? 'page' : nothing} @click=${() => this.navigate(item.page_id)}>${resolvedText(item.title, this.store.state) || item.page_id}</button>`)}
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
