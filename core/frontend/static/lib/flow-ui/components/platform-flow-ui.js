import { LitElement, css, html, nothing } from '../../lit-shim.js';
import { brandLogoSrc } from '../shell/brand-logo.js';
import { FlowUIController } from '../runtime/flow-ui-controller.js';
import { createLocalFlowUIProfile } from '../runtime/flow-ui-profile.js';
import { FlowUIHitlTransport } from '../runtime/hitl-transport.js';
import { createFlowUIRenderContext } from '../rendering/render-context.js';
import { flowUIRenderFingerprint } from '../rendering/render-fingerprint.js';
import { FLOW_UI_CATALOG_MANIFEST } from '../catalog/manifest.js';
import { flowUIGlyph } from '../catalog/flow-ui-glyph.js';
import { activeConversationTask, conversationSessionFiles, mergeConversationTasks } from '../catalog/platform/conversation-turn.js';
import { normalizeFlowUIBranchId } from '../protocol/a2a-codec.js';
import { resolveFlowUITheme } from '../shell/resolve-theme.js';
import { flowUIText, resolveFlowUILocale } from '../utils/text.js';
import { copyTextToClipboard } from '../../utils/clipboard.js';
import {
    flowUIVoiceSessionReady,
    stopFlowUIVoiceSession,
    toggleFlowUIVoiceSession,
} from '../voice/coordinator.js';
import { stopStreamTtsPlayback } from '../../voice/stream-tts-registry.js';
import './flow-ui-error-boundary.js';
import './flow-ui-surface.js';
import './flow-ui-turn-toasts.js';
import './flow-ui-files-panel.js';
import { deriveTurnActivityToasts } from '../runtime/turn-activity.js';

const FORWARDED_EVENTS = [
    'flow-ui-ready', 'flow-ui-error', 'flow-ui-a2a-frame', 'flow-ui-value-change',
    'flow-ui-saved', 'flow-ui-conflict', 'flow-ui-submit-start', 'flow-ui-submit-end',
    'flow-ui-preview-submit', 'flow-ui-validation-failed', 'flow-ui-navigation', 'flow-ui-file-progress',
    'flow-ui-files-ready', 'flow-ui-share-created', 'flow-ui-share-revoked',
];

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
        selectedComponentId: { attribute: false },
        workItemId: { type: String, attribute: 'work-item-id' },
        interactionPolicy: { attribute: false },
        controller: { attribute: false },
        runtimeState: { state: true },
        parityReady: { state: true },
        renderFingerprint: { state: true },
        shareState: { state: true },
        embedState: { state: true },
        voiceSessionActive: { state: true },
        drawerExpanded: { type: Boolean, attribute: 'drawer-expanded', reflect: true },
        companyId: { type: String, attribute: 'company-id' },
        voiceBaseUrl: { type: String, attribute: 'voice-base-url' },
        platformUiOrigin: { type: String, attribute: 'platform-ui-origin' },
        getRequestHeaders: { attribute: false },
        getExtraMetadataVariables: { attribute: false },
        assistantTitle: { type: String, attribute: 'assistant-title' },
    };

    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            min-width: 0;
            min-height: 0;
            height: 100%;
            overflow: hidden;
            color: var(--flow-ui-text);
            font-family: var(--font-sans);
            font-size: var(--font-size-sm, 14px);
            line-height: 1.45;
            background: var(--flow-ui-page-background, var(--bg-primary, #16213e));
        }
        /*
         * Viewport row MUST be minmax(0, 1fr): bare 1fr is minmax(auto, 1fr) and
         * refuses to shrink below content, so ConversationFeed never becomes a
         * scrollport and overflow:hidden ancestors just clip the chat.
         */
        .shell {
            position: relative;
            flex: 1 1 0;
            min-height: 0;
            height: 100%;
            display: grid;
            grid-template-rows: auto minmax(0, 1fr) auto;
        }
        /*
         * Minimal chrome: Share overlays the viewport. Absolute topbar must NOT create
         * a grid track — auto-placement would park <main.viewport> in a 0px first row
         * and overflow:hidden clips the entire conversation (blank SPA chat).
         */
        :host([data-chrome="minimal"]) .shell,
        :host([data-chrome="none"]) .shell {
            grid-template-rows: minmax(0, 1fr);
        }
        :host([data-chrome="minimal"]) .viewport,
        :host([data-chrome="none"]) .viewport {
            grid-row: 1;
            min-height: 0;
            height: 100%;
        }
        .topbar {
            min-height: 48px; display: flex; align-items: center; justify-content: space-between; gap: 12px;
            padding: 8px 14px; border-bottom: 1px solid var(--flow-ui-border);
            background: color-mix(in srgb, var(--flow-ui-panel-strong, transparent) 88%, transparent);
            position: sticky; top: 0; z-index: 4; backdrop-filter: blur(16px);
        }
        :host([data-chrome="minimal"]) .topbar {
            min-height: 0; justify-content: flex-end; border-bottom: 0; background: transparent;
            position: absolute; inset: 8px 10px auto auto; padding: 0; pointer-events: none;
            z-index: 5;
        }
        :host([data-chrome="minimal"]) .top-actions,
        :host([data-chrome="none"]) .top-actions { pointer-events: auto; }
        :host([data-chrome="none"]) .topbar {
            min-height: 0; justify-content: flex-end; border-bottom: 0; background: transparent;
            position: absolute; inset: 8px 10px auto auto; padding: 0; pointer-events: none;
            z-index: 5;
        }
        .brand { display: flex; align-items: center; gap: 9px; min-width: 0; font-weight: 650; letter-spacing: -.015em; color: var(--flow-ui-heading); }
        .brand-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .mark {
            width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
            display: grid; place-items: center;
            background: var(--flow-ui-logo-disc-bg, #0c0c0f);
            border: 1px solid var(--flow-ui-logo-disc-border, rgba(255, 255, 255, 0.14));
            box-shadow: var(--flow-ui-logo-disc-shadow);
            /* overflow visible: disc shadow must paint outside the mark. */
            overflow: visible;
        }
        .mark img { width: 18px; height: 18px; object-fit: contain; display: block; }
        nav { display: flex; gap: 5px; overflow: auto; }
        nav button { border: 0; background: transparent; color: var(--flow-ui-muted); padding: 7px 10px; border-radius: 9px; cursor: pointer; }
        nav button[aria-current="page"] { color: var(--flow-ui-text); background: var(--flow-ui-accent-muted); }
        .top-actions { display: flex; align-items: center; gap: 6px; }
        .readonly-pill { padding: 5px 9px; border: 1px solid var(--flow-ui-border); border-radius: 999px; color: var(--flow-ui-muted); font-size: 11px; white-space: nowrap; }
        .chrome-icon-btn {
            width: 36px; height: 36px; min-height: 36px; padding: 0; border-radius: 50%;
            display: inline-grid; place-items: center; cursor: pointer; box-sizing: border-box;
            border: 1px solid var(--flow-ui-border);
            background: color-mix(in srgb, var(--flow-ui-panel-strong, var(--flow-ui-panel)) 92%, transparent);
            color: var(--flow-ui-text);
            box-shadow: var(--flow-ui-panel-shadow);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
        }
        .chrome-icon-btn:hover:not(:disabled) {
            border-color: color-mix(in srgb, var(--flow-ui-accent) 45%, var(--flow-ui-border));
            background: color-mix(in srgb, var(--flow-ui-accent-muted) 55%, var(--flow-ui-panel-strong, var(--flow-ui-panel)));
        }
        .chrome-icon-btn:disabled { opacity: .72; cursor: default; }
        .task-run-control { position: relative; }
        .task-run-control__ring {
            position: absolute; inset: 5px; border-radius: 50%;
            border: 2px solid color-mix(in srgb, var(--flow-ui-accent) 22%, transparent);
            border-top-color: var(--flow-ui-accent);
            animation: flow-ui-chrome-spin .75s linear infinite;
        }
        .task-run-control__stop {
            position: relative; z-index: 1;
            width: 10px; height: 10px; border-radius: 2px; background: currentColor;
        }
        @keyframes flow-ui-chrome-spin { to { transform: rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) {
            .task-run-control__ring { animation-duration: 1.6s; }
        }
        .chrome-icon-btn .flow-ui-glyph {
            display: block;
            filter: brightness(0) saturate(100%) invert(88%) opacity(0.92);
        }
        :host([theme="light"]) .chrome-icon-btn .flow-ui-glyph,
        :host-context(html[data-theme="light"]) .chrome-icon-btn .flow-ui-glyph {
            filter: brightness(0) opacity(0.72);
        }
        .chrome-icon-btn:hover:not(:disabled) .flow-ui-glyph {
            opacity: 1;
        }
        details.share { position: relative; }
        details.share > summary {
            list-style: none; cursor: pointer;
        }
        details.share > summary::-webkit-details-marker { display: none; }
        .share-card {
            position: absolute; inset: calc(100% + 9px) 0 auto auto; z-index: 10;
            width: min(320px, calc(100vw - 28px));
            padding: var(--space-4, 16px);
            display: grid;
            gap: var(--space-3, 12px);
            border: 1px solid var(--glass-border-medium, var(--flow-ui-border-strong));
            border-radius: var(--radius-2xl, 25px);
            background: var(--glass-solid-strong, var(--flow-ui-panel-strong, var(--flow-ui-panel)));
            box-shadow: var(--glass-shadow-strong, var(--flow-ui-panel-shadow));
        }
        .share-title {
            font-weight: 650;
            font-size: var(--font-size-sm, 14px);
            letter-spacing: -.01em;
            color: var(--flow-ui-heading, var(--text-primary));
        }
        .share-copy {
            color: var(--flow-ui-muted, var(--text-tertiary));
            font-size: var(--font-size-xs, 12px);
            line-height: 1.45;
        }
        .share-options {
            display: flex;
            flex-direction: column;
            gap: var(--space-2, 8px);
        }
        .share-card .share-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 36px;
            padding: 8px 16px;
            border: none;
            border-radius: var(--btn-radius, 22px);
            font-family: inherit;
            font-size: var(--font-size-sm, 14px);
            font-weight: 400;
            line-height: 20px;
            white-space: nowrap;
            cursor: pointer;
            user-select: none;
            transition: var(--motion-transition-interactive, background .15s ease, box-shadow .15s ease);
        }
        .share-options .share-btn,
        .share-card > .share-btn,
        .embed-card .share-btn {
            width: 100%;
        }
        .share-card .share-btn.secondary,
        .embed-card .share-btn.secondary {
            color: var(--platform-btn-secondary-text, #99A6F9);
            background: var(--platform-btn-secondary-bg, rgba(153, 166, 249, 0.15));
        }
        .share-card .share-btn.secondary:hover:not(:disabled),
        .embed-card .share-btn.secondary:hover:not(:disabled) {
            background: var(--platform-btn-secondary-bg-hover, rgba(153, 166, 249, 0.1));
            box-shadow: var(--platform-btn-secondary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.2));
        }
        .share-card .share-btn.primary {
            color: var(--platform-btn-primary-text, #ffffff);
            background: var(--platform-btn-primary-bg, #99A6F9);
            box-shadow: var(--platform-btn-primary-shadow, none);
        }
        .share-card .share-btn.primary:hover:not(:disabled) {
            background: var(--platform-btn-primary-bg-hover, #8794F0);
            box-shadow: var(--platform-btn-primary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.6));
        }
        .share-card .share-btn.ghost {
            color: var(--text-secondary, var(--flow-ui-muted));
            background: transparent;
        }
        .share-card .share-btn.ghost:hover:not(:disabled) {
            color: var(--text-primary, var(--flow-ui-text));
            background: var(--platform-btn-secondary-bg, rgba(153, 166, 249, 0.12));
        }
        .share-card .share-btn:disabled { opacity: .5; cursor: wait; }
        .share-result {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: var(--space-2, 8px);
            align-items: center;
        }
        .share-result input {
            min-width: 0;
            height: 36px;
            border: 1px solid var(--border-default, var(--flow-ui-border));
            border-radius: var(--btn-radius, 22px);
            background: var(--flow-ui-input, var(--glass-solid-subtle));
            color: var(--flow-ui-text);
            padding: 0 14px;
            font: inherit;
            font-size: var(--font-size-sm, 14px);
        }
        .share-error { color: var(--error, #ff8da3); font-size: 12px; }
        details.embed { position: relative; }
        details.embed > summary {
            list-style: none; cursor: pointer;
        }
        details.embed > summary::-webkit-details-marker { display: none; }
        .embed-card {
            position: absolute; inset: calc(100% + 9px) 0 auto auto; z-index: 10;
            width: min(320px, calc(100vw - 28px));
            padding: var(--space-4, 16px);
            display: grid;
            gap: var(--space-3, 12px);
            border: 1px solid var(--glass-border-medium, var(--flow-ui-border-strong));
            border-radius: var(--radius-2xl, 25px);
            background: var(--glass-solid-strong, var(--flow-ui-panel-strong, var(--flow-ui-panel)));
            box-shadow: var(--glass-shadow-strong, var(--flow-ui-panel-shadow));
        }
        .embed-title {
            font-weight: 650;
            font-size: var(--font-size-sm, 14px);
            letter-spacing: -.01em;
            color: var(--flow-ui-heading, var(--text-primary));
        }
        .embed-copy {
            color: var(--flow-ui-muted, var(--text-tertiary));
            font-size: var(--font-size-xs, 12px);
            line-height: 1.45;
        }
        .embed-result {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: var(--space-2, 8px);
            align-items: center;
        }
        .embed-result input {
            min-width: 0;
            height: 36px;
            border: 1px solid var(--border-default, var(--flow-ui-border));
            border-radius: var(--btn-radius, 22px);
            background: var(--flow-ui-input, var(--glass-solid-subtle));
            color: var(--flow-ui-text);
            padding: 0 14px;
            font: inherit;
            font-size: var(--font-size-sm, 14px);
        }
        .viewport {
            min-height: 0;
            overflow: hidden;
            container-type: inline-size;
            display: flex;
            flex-direction: column;
        }
        flow-ui-surface { flex: 1 1 0; min-height: 0; height: 100%; }
        .statusbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 6px 13px; border-top: 1px solid var(--flow-ui-border); color: var(--flow-ui-muted); font-size: 11px; }
        .status { display: inline-flex; align-items: center; gap: 6px; }
        .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success, #5ad0a0); box-shadow: 0 0 0 3px color-mix(in srgb, var(--success, #5ad0a0) 20%, transparent); }
        .dot.pending { background: var(--warning, #f8bc60); }
        .dot.error { background: var(--error, #ff718d); }
        .skeleton { min-height: 320px; padding: 22px; display: grid; align-content: start; gap: 14px; }
        .shimmer { height: 74px; border-radius: 17px; background: linear-gradient(90deg, var(--flow-ui-surface-subtle), var(--flow-ui-surface-hover), var(--flow-ui-surface-subtle)); background-size: 220% 100%; animation: shimmer 1.4s infinite linear; }
        @keyframes shimmer { to { background-position: -220% 0; } }
        /*
         * Drawer/panel: never put box-shadow on the same box as overflow:hidden.
         * Chromium/WebKit then paint dark triangular nicks in the rounded corners.
         * Shadow stays on :host; content clips on .shell with matching radius.
         */
        :host([display="panel"]), :host([display="drawer"]) {
            border-radius: 22px;
            overflow: visible;
            box-shadow: var(--flow-ui-panel-shadow);
            background: var(--flow-ui-panel-strong, var(--flow-ui-page-background, var(--bg-surface, #1e2a47)));
        }
        :host([display="inline"]) {
            border-radius: 16px;
            overflow: visible;
            background: var(--flow-ui-panel-strong, var(--flow-ui-page-background, var(--bg-surface, #1e2a47)));
        }
        :host([display="panel"]) .shell,
        :host([display="drawer"]) .shell,
        :host([display="inline"]) .shell {
            border-radius: inherit;
            overflow: hidden;
        }
        @media (prefers-reduced-motion: reduce) { .shimmer { animation: none; } }
        @media (max-width: 680px) { nav { order: 3; width: 100%; } .topbar { flex-wrap: wrap; } .readonly-pill { display: none; } }
    `;

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
        this.locale = 'ru';
        this.initialDocument = null;
        this.readonly = false;
        this.credentials = 'include';
        this.selectedComponentId = null;
        this.workItemId = '';
        this.interactionPolicy = null;
        this.controller = null;
        this.runtimeState = null;
        this.parityReady = false;
        this.renderFingerprint = '';
        this.shareState = {
            loading: false, url: '', grantId: '', permission: 'viewer', copied: false, error: '',
        };
        this.embedState = { copied: false };
        this.voiceSessionActive = false;
        this.drawerExpanded = false;
        this.companyId = '';
        this.voiceBaseUrl = '';
        this.platformUiOrigin = '';
        this.getRequestHeaders = null;
        this.getExtraMetadataVariables = null;
        this.assistantTitle = '';
        this._hitlTransport = null;
        this._themeObserver = null;
        this._sessionGeneration = 0;
        this._voiceMedia = null;
        this._voiceBridge = null;
        this._onThemeAttribute = () => this.requestUpdate();
    }

    connectedCallback() {
        super.connectedCallback();
        this._observePlatformTheme();
        queueMicrotask(() => this._start());
    }

    disconnectedCallback() {
        this._sessionGeneration += 1;
        this._disconnectThemeObserver();
        this._disposeSession();
        super.disconnectedCallback();
    }

    updated(changedProperties) {
        if (!this.isConnected || !this.controller) {
            return;
        }
        if (!this._hostSessionDrift(changedProperties)) {
            return;
        }
        void this._restartSession();
    }

    _hostSessionDrift(changedProperties) {
        const target = this.controller?.target;
        if (!target) {
            return false;
        }
        // Local-document mode (interface editor frame): a new document is a local
        // re-hydrate, so the host swaps it in place instead of reloading the frame.
        if (changedProperties.has('initialDocument') && this.initialDocument != null) {
            return true;
        }
        if (changedProperties.has('flowId') && (this.flowId || '') !== (target.flowId || '')) {
            return true;
        }
        if (
            changedProperties.has('branchId')
            && normalizeFlowUIBranchId(this.branchId) !== target.branchId
        ) {
            return true;
        }
        if (changedProperties.has('embedId') && (this.embedId || '') !== (target.embedId || '')) {
            return true;
        }
        if (!changedProperties.has('contextId')) {
            return false;
        }
        // Empty host contextId is "open/create" during first bootstrap and must not
        // tear down a live controller when the parent has not caught up to the URL yet.
        // Non-empty host context that differs from the active controller is an explicit retarget
        // (history / deep-link session switch).
        const hostContextId = typeof this.contextId === 'string' ? this.contextId.trim() : '';
        if (hostContextId === '') {
            return false;
        }
        return hostContextId !== (this.controller.contextId || '');
    }

    _disposeSession() {
        this._hitlTransport?.dispose();
        this._hitlTransport = null;
        void stopFlowUIVoiceSession(this);
        if (this.controller) {
            this.controller.dispose();
            this.controller = null;
        }
        this.runtimeState = null;
        this.parityReady = false;
        this.renderFingerprint = '';
        this.removeAttribute('parity-ready');
    }

    async _restartSession() {
        const sessionGeneration = ++this._sessionGeneration;
        this._disposeSession();
        if (sessionGeneration !== this._sessionGeneration || !this.isConnected) {
            return;
        }
        await this._start();
    }

    _observePlatformTheme() {
        this._disconnectThemeObserver();
        if (typeof MutationObserver === 'undefined' || !globalThis.document?.documentElement) {
            return;
        }
        this._themeObserver = new MutationObserver(this._onThemeAttribute);
        this._themeObserver.observe(globalThis.document.documentElement, {
            attributes: true,
            attributeFilter: ['data-theme'],
        });
    }

    _disconnectThemeObserver() {
        if (this._themeObserver) {
            this._themeObserver.disconnect();
            this._themeObserver = null;
        }
    }

    _resolvedTheme() {
        return resolveFlowUITheme(this.theme, globalThis.document);
    }

    _chromeMode(document) {
        // Interface editor production frame: host chrome is outside the iframe.
        if (this.initialDocument != null || this.profile === 'editor_test') {
            return 'none';
        }
        const pages = Object.values(document?.pages || {}).filter((page) => page.navigation?.visible !== false);
        if (pages.length > 1) return 'full';
        // Drawer always keeps minimal chrome so Expand / Share / Embed stay reachable.
        if (this.display === 'drawer') {
            return 'minimal';
        }
        if (this.profile === 'spa' || this.display === 'panel') {
            return this.runtimeState?.profile?.viewer?.can_share === true ? 'minimal' : 'none';
        }
        return 'full';
    }

    async _start() {
        if (!this.isConnected || this.controller) return;
        const sessionGeneration = this._sessionGeneration;
        const hitl = this.profile === 'operator_handoff';
        if (hitl) {
            this._assertHitlConfig();
            this.flowId = this.interactionPolicy.conversation.flow_id;
            this.contextId = this.interactionPolicy.conversation.context_id;
            if (typeof this.interactionPolicy.conversation.branch_id === 'string'
                && this.interactionPolicy.conversation.branch_id.trim() !== '') {
                this.branchId = this.interactionPolicy.conversation.branch_id;
            }
        }
        if (sessionGeneration !== this._sessionGeneration || !this.isConnected) {
            return;
        }
        const localProfile = this.initialDocument ? createLocalFlowUIProfile(this.profile || 'editor_test') : null;
        const host = this;
        const controller = new FlowUIController({
            flowId: this.flowId, branchId: this.branchId, embedId: this.embedId,
            contextId: this.contextId, baseUrl: this.baseUrl,
            initialDocument: this.initialDocument, profile: localProfile,
            profileKind: this.profile || 'spa',
            credentials: this.credentials || 'include',
            headers: () => typeof host.getRequestHeaders === 'function' ? host.getRequestHeaders() : {},
            // Read the host-bound hook at call time (not construction time). Never assign
            // this wrapper onto host.getExtraMetadataVariables — that would recurse.
            getExtraMetadataVariables: async () => {
                const hook = host.getExtraMetadataVariables;
                if (typeof hook !== 'function') {
                    return null;
                }
                // Host passes arrow/bound hooks; do not rebind `this` to platform-flow-ui.
                return hook();
            },
        });
        if (sessionGeneration !== this._sessionGeneration || !this.isConnected) {
            controller.dispose();
            return;
        }
        this.controller = controller;
        controller.addEventListener('change', (event) => {
            if (this.controller !== controller) return;
            this.runtimeState = event.detail.state;
            this.contextId = controller.contextId;
            this.requestUpdate();
            this.updateComplete.then(() => this._markParityReady());
            this.dispatchEvent(new CustomEvent('flow-ui-state-changed', {
                bubbles: true, composed: true, detail: event.detail,
            }));
        });
        for (const name of FORWARDED_EVENTS) {
            controller.addEventListener(name, (event) => {
                if (this.controller !== controller) return;
                this.dispatchEvent(new CustomEvent(name, {
                    bubbles: true, composed: true, detail: event.detail,
                }));
            });
        }
        try {
            if (hitl) {
                this._hitlTransport = new FlowUIHitlTransport({
                    workItemId: this.workItemId,
                    conversation: this.interactionPolicy.conversation,
                    mode: this.interactionPolicy.mode,
                    baseUrl: this.baseUrl,
                    getHeaders: async () => (
                        typeof this.getRequestHeaders === 'function' ? this.getRequestHeaders() : {}
                    ),
                });
                this._hitlTransport.attach(controller);
                await controller.connect();
                if (
                    sessionGeneration !== this._sessionGeneration
                    || !this.isConnected
                    || this.controller !== controller
                ) {
                    return;
                }
                await this._hitlTransport.loadHistory();
            } else {
                await controller.connect();
            }
            if (
                sessionGeneration !== this._sessionGeneration
                || !this.isConnected
                || this.controller !== controller
            ) {
                return;
            }
        } catch (error) {
            if (error && typeof error === 'object' && error.name === 'AbortError') return;
            /* rendered by state */
        }
    }

    _assertHitlConfig() {
        if (typeof this.workItemId !== 'string' || this.workItemId.trim() === '') {
            throw new Error('platform-flow-ui: operator_handoff requires work-item-id');
        }
        const policy = this.interactionPolicy;
        if (!policy || typeof policy !== 'object') {
            throw new Error('platform-flow-ui: operator_handoff requires interactionPolicy');
        }
        if (policy.mode !== 'takeover' && policy.mode !== 'single_reply') {
            throw new Error(`platform-flow-ui: unsupported HITL mode ${JSON.stringify(policy.mode)}`);
        }
        const conversation = policy.conversation;
        if (!conversation || typeof conversation !== 'object') {
            throw new Error('platform-flow-ui: interactionPolicy.conversation required');
        }
        for (const key of ['flow_id', 'context_id', 'session_id', 'a2a_task_id']) {
            if (typeof conversation[key] !== 'string' || conversation[key].trim() === '') {
                throw new Error(`platform-flow-ui: conversation.${key} required`);
            }
        }
    }

    async _markParityReady() {
        const document = this.controller?.document;
        if (!document) return;
        if (globalThis.document?.fonts?.ready) await globalThis.document.fonts.ready;
        const images = [...this.renderRoot.querySelectorAll('img')];
        await Promise.all(images.map((image) => image.complete ? Promise.resolve() : new Promise((resolve) => {
            image.addEventListener('load', resolve, { once: true });
            image.addEventListener('error', resolve, { once: true });
        })));
        const context = createFlowUIRenderContext({
            document, display: this.display, theme: this._resolvedTheme(), locale: this.locale,
            catalogManifestChecksum: FLOW_UI_CATALOG_MANIFEST.checksum,
            targetSurfaceProfileId: `runtime.${this.display}.v1`,
            taskProjectionSequence: this.controller.activeContext?.taskOrder?.length || 0,
        });
        this.renderFingerprint = flowUIRenderFingerprint(context);
        this.parityReady = true;
        this.setAttribute('parity-ready', '');
        this.dispatchEvent(new CustomEvent('flow-ui-render-committed', {
            bubbles: true, composed: true,
            detail: Object.freeze({ revision: document.revision, fingerprint: this.renderFingerprint, context }),
        }));
    }

    hydrateContext(snapshot) { return this.controller?.hydrateContext(snapshot); }
    startNewContext() { return this.controller?.startNewContext(); }
    submit(surfaceId, componentId) { return this.controller?.submit(surfaceId, componentId); }
    cancelActiveTask() {
        stopStreamTtsPlayback();
        return this.controller?.cancelActiveTask();
    }
    stopVoice() {
        void stopFlowUIVoiceSession(this);
        this.dispatchEvent(new CustomEvent('flow-ui-stop-voice', { bubbles: true, composed: true }));
    }
    voiceSessionReady() {
        return flowUIVoiceSessionReady(this);
    }
    toggleVoiceSession() {
        return toggleFlowUIVoiceSession(this);
    }
    navigate(pageId) { return this.controller?.navigate(pageId); }
    applyA2AFrame(frame) { return this.controller?.applyA2AFrame(frame); }
    createShare(options) { return this.controller?.createShare(options); }
    revokeShare(grantId) { return this.controller?.revokeShare(grantId); }

    _toggleDrawerExpand() {
        this.dispatchEvent(new CustomEvent('flow-ui-drawer-expand-toggle', {
            bubbles: true,
            composed: true,
            detail: { expanded: this.drawerExpanded !== true },
        }));
    }

    _embedPageUrl() {
        const embedId = typeof this.embedId === 'string' ? this.embedId.trim() : '';
        if (embedId === '') {
            return '';
        }
        if (typeof window === 'undefined' || !window.location) {
            throw new Error('flow-ui embed: window.location required');
        }
        return `${window.location.origin}/flow-embed-page?embed=${encodeURIComponent(embedId)}`;
    }

    async _copyEmbedPageUrl() {
        const url = this._embedPageUrl();
        if (url === '') {
            throw new Error('flow-ui embed: embedId required');
        }
        try {
            await copyTextToClipboard(url);
            this.embedState = { copied: true };
        } catch {
            const input = this.renderRoot.querySelector('.embed-result input');
            input?.select();
            this.embedState = { copied: false };
        }
    }

    getRenderContext() {
        const document = this.controller?.document;
        if (!document) {
            throw new Error('platform-flow-ui: getRenderContext requires hydrated document');
        }
        return createFlowUIRenderContext({
            document,
            display: this.display,
            theme: this._resolvedTheme(),
            locale: this.locale,
            catalogManifestChecksum: FLOW_UI_CATALOG_MANIFEST.checksum,
            targetSurfaceProfileId: `runtime.${this.display}.v1`,
            taskProjectionSequence: this.controller.activeContext?.taskOrder?.length || 0,
        });
    }

    async _createShare(permission) {
        this.shareState = {
            loading: true, url: '', grantId: '', permission, copied: false, error: '',
        };
        try {
            const result = await this.createShare({ permission });
            const grantId = result?.grant?.grant_id;
            if (typeof grantId !== 'string' || !grantId) {
                throw new Error('flow-ui share: grant_id missing from create response');
            }
            this.shareState = {
                loading: false,
                url: result.share_url,
                grantId,
                permission,
                copied: false,
                error: '',
            };
        } catch (error) {
            this.shareState = {
                loading: false, url: '', grantId: '', permission, copied: false,
                error: error instanceof Error ? error.message : String(error),
            };
        }
    }

    async _copyShare() {
        if (!this.shareState.url) return;
        try {
            await copyTextToClipboard(this.shareState.url);
            this.shareState = { ...this.shareState, copied: true };
        } catch {
            const input = this.renderRoot.querySelector('.share-result input');
            input?.select();
            this.shareState = { ...this.shareState, copied: false };
        }
    }

    async _revokeShare() {
        const grantId = this.shareState.grantId;
        if (!grantId) throw new Error('flow-ui: no active share grant to revoke');
        this.shareState = { ...this.shareState, loading: true, error: '' };
        try {
            await this.revokeShare(grantId);
            this.shareState = {
                loading: false, url: '', grantId: '', permission: this.shareState.permission,
                copied: false, error: '',
            };
        } catch (error) {
            this.shareState = {
                ...this.shareState,
                loading: false,
                error: error instanceof Error ? error.message : String(error),
            };
        }
    }

    _taskRunControl(effectiveReadonly) {
        const tasks = this.controller?.activeContext
            ? this.controller.activeContext.taskOrder
                .map((id) => this.controller.activeContext.tasksById[id])
                .filter(Boolean)
            : [];
        const active = activeConversationTask(tasks);
        if (!active) return nothing;
        const cancelAllowed = this.runtimeState?.profile?.capabilities?.cancel === true;
        const canCancel = cancelAllowed && !effectiveReadonly;
        const locale = resolveFlowUILocale(this.locale);
        const label = flowUIText(locale, canCancel ? 'stop_task' : 'task_running');
        return html`<button
            type="button"
            class="chrome-icon-btn task-run-control"
            ?disabled=${!canCancel}
            aria-label=${label}
            title=${label}
            aria-busy="true"
            @click=${() => {
                if (!canCancel) return;
                this.cancelActiveTask();
            }}
        >
            <span class="task-run-control__ring" aria-hidden="true"></span>
            ${canCancel
                ? html`<span class="task-run-control__stop" aria-hidden="true"></span>`
                : nothing}
        </button>`;
    }

    _sessionFilesPanelAllowed() {
        const policy = this.controller?.document?.policy;
        if (policy && policy.show_files_panel === false) return false;
        const capabilities = this.runtimeState?.profile?.capabilities;
        if (capabilities && capabilities.files === false) return false;
        return true;
    }

    _sessionFiles() {
        if (!this._sessionFilesPanelAllowed()) return [];
        const context = this.controller?.activeContext;
        if (!context) return [];
        const tasks = context.taskOrder
            .map((id) => context.tasksById[id])
            .filter(Boolean);
        return conversationSessionFiles(mergeConversationTasks(tasks, context.pendingTurns));
    }

    _shareMenu() {
        if (this.runtimeState?.profile?.viewer?.can_share !== true) return nothing;
        const locale = resolveFlowUILocale(this.locale);
        return html`<details class="share">
            <summary
                class="chrome-icon-btn"
                aria-label=${flowUIText(locale, 'share_aria')}
                title=${flowUIText(locale, 'share')}
            >${flowUIGlyph('share', 18, this.platformUiOrigin)}</summary>
            <div class="share-card">
                <div><div class="share-title">${flowUIText(locale, 'share_title')}</div><div class="share-copy">${flowUIText(locale, 'share_description')}</div></div>
                <div class="share-options">
                    <button
                        type="button"
                        class="share-btn secondary"
                        ?disabled=${this.shareState.loading}
                        @click=${() => this._createShare('viewer')}
                    >${flowUIText(locale, 'share_view_only')}</button>
                    <button
                        type="button"
                        class="share-btn primary"
                        ?disabled=${this.shareState.loading}
                        @click=${() => this._createShare('editor')}
                    >${flowUIText(locale, 'share_can_interact')}</button>
                </div>
                ${this.shareState.loading ? html`<div class="share-copy">${flowUIText(locale, 'share_creating')}</div>` : nothing}
                ${this.shareState.url ? html`
                    <div class="share-result">
                        <input readonly .value=${this.shareState.url} aria-label=${flowUIText(locale, 'share_link')}>
                        <button type="button" class="share-btn secondary" @click=${this._copyShare}>${flowUIText(locale, this.shareState.copied ? 'share_copied' : 'share_copy')}</button>
                    </div>
                    <button
                        type="button"
                        class="share-btn ghost"
                        ?disabled=${this.shareState.loading}
                        @click=${this._revokeShare}
                    >${flowUIText(locale, 'share_revoke')}</button>
                ` : nothing}
                ${this.shareState.error ? html`<div class="share-error" role="alert">${this.shareState.error}</div>` : nothing}
            </div>
        </details>`;
    }

    _embedMenu() {
        const pageUrl = this._embedPageUrl();
        if (pageUrl === '') return nothing;
        const locale = resolveFlowUILocale(this.locale);
        return html`<details class="embed">
            <summary
                class="chrome-icon-btn"
                aria-label=${flowUIText(locale, 'embed_aria')}
                title=${flowUIText(locale, 'embed')}
            >${flowUIGlyph('code', 18, this.platformUiOrigin)}</summary>
            <div class="embed-card">
                <div>
                    <div class="embed-title">${flowUIText(locale, 'embed_title')}</div>
                    <div class="embed-copy">${flowUIText(locale, 'embed_page_description')}</div>
                </div>
                <div class="embed-copy">${flowUIText(locale, 'embed_page_url')}</div>
                <div class="embed-result">
                    <input readonly .value=${pageUrl} aria-label=${flowUIText(locale, 'embed_page_url')}>
                    <button type="button" class="share-btn secondary" @click=${this._copyEmbedPageUrl}>
                        ${flowUIText(locale, this.embedState.copied ? 'embed_copied' : 'embed_copy')}
                    </button>
                </div>
            </div>
        </details>`;
    }

    _expandControl() {
        if (this.display !== 'drawer') return nothing;
        const locale = resolveFlowUILocale(this.locale);
        const expanded = this.drawerExpanded === true;
        return html`<button
            type="button"
            class="chrome-icon-btn"
            aria-pressed=${expanded ? 'true' : 'false'}
            aria-label=${flowUIText(locale, expanded ? 'collapse_aria' : 'expand_aria')}
            title=${flowUIText(locale, expanded ? 'collapse_aria' : 'expand_aria')}
            @click=${this._toggleDrawerExpand}
        >${flowUIGlyph(expanded ? 'minimize' : 'expand', 18, this.platformUiOrigin)}</button>`;
    }

    _topActions(chromeMode, effectiveReadonly) {
        const sessionFiles = this._sessionFiles();
        const filesPanel = sessionFiles.length > 0
            ? html`<flow-ui-files-panel
                .files=${sessionFiles}
                locale=${resolveFlowUILocale(this.locale)}
            ></flow-ui-files-panel>`
            : nothing;
        const runControl = this._taskRunControl(effectiveReadonly);
        const shareMenu = this._shareMenu();
        const embedMenu = this._embedMenu();
        const expandControl = this._expandControl();
        const readonlyPill = effectiveReadonly && chromeMode === 'full'
            ? html`<span class="readonly-pill">${flowUIText(resolveFlowUILocale(this.locale), 'read_only')}</span>`
            : nothing;
        if (
            filesPanel === nothing
            && runControl === nothing
            && shareMenu === nothing
            && embedMenu === nothing
            && expandControl === nothing
            && readonlyPill === nothing
        ) {
            return nothing;
        }
        return html`<div class="top-actions">${filesPanel}${readonlyPill}${runControl}${expandControl}${embedMenu}${shareMenu}</div>`;
    }

    _navigation(document) {
        const pages = Object.values(document.pages || {}).filter((page) => page.navigation?.visible !== false);
        if (pages.length <= 1) return nothing;
        return html`<nav aria-label=${flowUIText(resolveFlowUILocale(this.locale), 'pages_nav')}>${pages.map((page) => html`<button aria-current=${document.active_page_id === page.page_id ? 'page' : nothing} @click=${() => this.navigate(page.page_id)}>${page.title?.default || page.page_id}</button>`)}</nav>`;
    }

    render() {
        const context = this.controller?.activeContext;
        if (!context || context.hydration === 'idle' || context.hydration === 'loading') {
            return html`<div class="skeleton" aria-busy="true" aria-label=${flowUIText(resolveFlowUILocale(this.locale), 'loading_interface')}><div class="shimmer"></div><div class="shimmer"></div><div class="shimmer"></div></div>`;
        }
        if (context.hydration === 'error') return html`<flow-ui-error-boundary .error=${context.error}></flow-ui-error-boundary>`;
        const document = context.document;
        const page = document?.pages?.[document.active_page_id];
        const surface = page ? document.surfaces?.[page.root_surface_id] : null;
        if (!surface) return html`<flow-ui-error-boundary .error=${new Error('Active page surface is missing')}></flow-ui-error-boundary>`;
        const tasks = context.taskOrder.map((id) => context.tasksById[id]).filter(Boolean);
        const statusClass = context.saveStatus === 'pending' ? 'pending' : context.saveStatus === 'conflict' ? 'error' : '';
        const effectiveReadonly = this.readonly || this.runtimeState?.profile?.viewer?.can_interact === false;
        const chromeMode = this._chromeMode(document);
        this.setAttribute('data-chrome', chromeMode);
        const locale = resolveFlowUILocale(this.locale);
        const statusLabel = this.initialDocument
            ? flowUIText(locale, 'status_preview')
            : effectiveReadonly
              ? flowUIText(locale, 'status_read_only')
              : context.saveStatus === 'pending'
                ? flowUIText(locale, 'status_saving')
                : context.saveStatus === 'conflict'
                  ? flowUIText(locale, 'status_conflict')
                  : flowUIText(locale, 'status_saved');
        const titleOverride = typeof this.assistantTitle === 'string' ? this.assistantTitle.trim() : '';
        const brandTitle = titleOverride !== ''
            ? titleOverride
            : (this.runtimeState?.profile?.flow_identity?.title || page.title?.default || 'Linnex');
        const turnToasts = deriveTurnActivityToasts({
            document,
            context,
            locale,
            capabilities: this.runtimeState?.profile?.capabilities || null,
        });
        const topActions = this._topActions(chromeMode, effectiveReadonly);
        const showTopbar = chromeMode === 'full' || topActions !== nothing;
        return html`<div class="shell" data-chrome=${chromeMode}>
            ${showTopbar ? html`<header class="topbar">
                ${chromeMode === 'full' ? html`<div class="brand">
                    <span class="mark" aria-hidden="true"><img src=${brandLogoSrc(this.platformUiOrigin)} alt=""></span>
                    <span class="brand-label">${brandTitle}</span>
                </div>` : nothing}
                ${chromeMode === 'full' ? this._navigation(document) : nothing}
                ${topActions}
            </header>` : nothing}
            <main class="viewport"><flow-ui-surface
                .surface=${surface} .tasks=${tasks} .controller=${this.controller}
                .readonly=${effectiveReadonly} .locale=${resolveFlowUILocale(this.locale)}
                .platformUiOrigin=${this.platformUiOrigin}
                .selectedComponentId=${this.selectedComponentId}
            ></flow-ui-surface></main>
            ${chromeMode === 'full' ? html`<footer class="statusbar"><span class="status"><span class="dot ${statusClass}"></span>${statusLabel}</span><span>${document.revision ? `r${document.revision}` : ''}${this.parityReady ? ' · Exact' : ''}</span></footer>` : nothing}
            ${turnToasts.length > 0
                ? html`<flow-ui-turn-toasts
                    .toasts=${turnToasts}
                    locale=${locale}
                    @turn-toast-cancel=${() => this.cancelActiveTask()}
                ></flow-ui-turn-toasts>`
                : nothing}
        </div>`;
    }
}

if (!customElements.get('platform-flow-ui')) customElements.define('platform-flow-ui', PlatformFlowUI);
