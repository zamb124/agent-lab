/**
 * Кнопка «Запустить ноду» (play) и портальный пузырь со сводкой execute.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';
import { getCodeExecuteRequestClientId } from '../_helpers/flows-code-execute-run-gate.js';

const PORTAL_STYLE_ID = 'flows-node-run-control-portal-styles';

function ensurePortalStyles() {
    if (typeof document === 'undefined' || document.getElementById(PORTAL_STYLE_ID)) {
        return;
    }
    const style = document.createElement('style');
    style.id = PORTAL_STYLE_ID;
    style.textContent = `
        .flows-node-run-bubble {
            position: fixed;
            transform: translateX(-50%);
            width: min(720px, calc(100vw - 24px));
            min-width: min(200px, calc(100vw - 24px));
            max-height: min(70vh, 720px);
            overflow: auto;
            padding: 10px 12px;
            font-size: 12px;
            font-weight: 400;
            line-height: 1.45;
            text-align: left;
            white-space: pre-wrap;
            word-break: break-word;
            overflow-wrap: anywhere;
            color: var(--text-primary);
            background: var(--bg-elevated);
            border: 1px solid var(--glass-border-subtle, rgba(255, 255, 255, 0.12));
            border-radius: var(--radius-md, 10px);
            box-shadow: var(--glass-shadow-strong, 0 8px 28px rgba(0, 0, 0, 0.35));
            pointer-events: auto;
            box-sizing: border-box;
        }
        .flows-node-run-bubble--ok {
            background: var(--bg-elevated);
            border: 1px solid var(--success-border);
        }
        .flows-node-run-bubble--error {
            background: var(--bg-elevated);
            border: 1px solid var(--error-border);
        }
        .flows-node-run-bubble .duration {
            font-size: 11px;
            color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
            margin-bottom: 8px;
        }
        .flows-node-run-bubble ul {
            margin: 0 0 8px 0;
            padding-left: 1.1em;
            max-width: 100%;
            box-sizing: border-box;
        }
        .flows-node-run-bubble li {
            word-break: break-word;
            overflow-wrap: anywhere;
            max-width: 100%;
            box-sizing: border-box;
        }
        .flows-node-run-bubble .full-btn {
            background: none;
            border: none;
            padding: 0;
            color: var(--accent, #7c8cff);
            font: inherit;
            font-size: 12px;
            cursor: pointer;
            text-decoration: underline;
        }
        .flows-node-run-bubble .full-btn:hover { color: var(--text-primary, #fff); }
    `;
    document.head.appendChild(style);
}

export class FlowsNodeRunControl extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        viewModel: { type: Object },
        busy: { type: Boolean },
        /** Совпадает с flows-base-node-editor._codeExecuteClientId — чей запрос, тот пузырь. */
        requestClientId: { type: String },
        _bubbleOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: inline-flex; align-items: center; vertical-align: middle; }
            .root { position: relative; display: inline-flex; align-items: center; }
            .play-btn {
                width: 32px; height: 32px; padding: 0;
                display: inline-flex; align-items: center; justify-content: center;
                background: var(--glass-solid-medium, rgba(255,255,255,0.08));
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.12));
                border-radius: var(--radius-md, 8px);
                color: var(--accent, #7c8cff);
                cursor: pointer;
            }
            .play-btn:hover:not(:disabled) {
                background: var(--glass-solid-strong, rgba(255,255,255,0.12));
            }
            .play-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        `,
    ];

    constructor() {
        super();
        this.viewModel = null;
        this.busy = false;
        this.requestClientId = '';
        this._bubbleOpen = false;
        this._wasBusy = false;
        this._portalEl = null;
        this._bubbleZ = 0;
        this._onDocPointerDown = this._onDocPointerDown.bind(this);
        this._onGlobalKeydown = this._onGlobalKeydown.bind(this);
        this._onGlobalScroll = this._onGlobalScroll.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._wasBusy = this.busy;
    }

    disconnectedCallback() {
        this._detachGlobalListeners();
        this._teardownPortal();
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('busy')) {
            if (this._wasBusy === true && this.busy === false && this.viewModel) {
                const rid = typeof this.requestClientId === 'string' ? this.requestClientId : '';
                const mayShow =
                    rid.length === 0
                    ? true
                    : getCodeExecuteRequestClientId() === rid;
                if (mayShow) {
                    this._bubbleOpen = true;
                }
            }
            this._wasBusy = this.busy;
        }
        if (changed.has('_bubbleOpen') || changed.has('viewModel')) {
            if (this._bubbleOpen && this.viewModel) {
                queueMicrotask(() => this._mountOrUpdatePortal());
            } else {
                this._teardownPortal();
            }
        }
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('viewModel') && this.viewModel === null) {
            this._bubbleOpen = false;
        }
    }

    _detachGlobalListeners() {
        document.removeEventListener('pointerdown', this._onDocPointerDown, true);
        window.removeEventListener('keydown', this._onGlobalKeydown, true);
        window.removeEventListener('scroll', this._onGlobalScroll, true);
        window.removeEventListener('resize', this._onGlobalScroll, true);
    }

    _attachGlobalListeners() {
        document.addEventListener('pointerdown', this._onDocPointerDown, true);
        window.addEventListener('keydown', this._onGlobalKeydown, true);
        window.addEventListener('scroll', this._onGlobalScroll, true);
        window.addEventListener('resize', this._onGlobalScroll, true);
    }

    _onGlobalScroll() {
        if (this._bubbleOpen && this._portalEl) {
            this._syncPortalPosition();
        }
    }

    _onGlobalKeydown(e) {
        if (e.key === 'Escape' && this._bubbleOpen) {
            this._bubbleOpen = false;
        }
    }

    _onDocPointerDown(e) {
        if (!this._bubbleOpen || !this._portalEl) {
            return;
        }
        const path = e.composedPath();
        if (path.includes(this._portalEl) || path.includes(this)) {
            return;
        }
        this._bubbleOpen = false;
    }

    _syncPortalPosition() {
        if (!this._portalEl) {
            return;
        }
        const btn = this.renderRoot?.querySelector('.play-btn');
        if (!btn) {
            return;
        }
        const r = btn.getBoundingClientRect();
        const gap = 8;
        this._portalEl.style.top = `${r.bottom + gap}px`;
        this._portalEl.style.zIndex = String(this._bubbleZ);
        this._portalEl.style.transform = 'translateX(-50%)';
        const desiredCenterX = r.left + r.width / 2;
        this._portalEl.style.left = `${desiredCenterX}px`;
        const margin = 12;
        const viewW = window.innerWidth;
        const bubbleRect = this._portalEl.getBoundingClientRect();
        const half = bubbleRect.width / 2;
        let centerX = desiredCenterX;
        const minCenter = margin + half;
        const maxCenter = viewW - margin - half;
        if (minCenter <= maxCenter) {
            if (centerX < minCenter) {
                centerX = minCenter;
            }
            if (centerX > maxCenter) {
                centerX = maxCenter;
            }
        } else {
            centerX = viewW / 2;
        }
        this._portalEl.style.left = `${centerX}px`;
    }

    _teardownPortal() {
        this._detachGlobalListeners();
        if (this._portalEl) {
            this._portalEl.remove();
            this._portalEl = null;
        }
    }

    _fillPortalContent(root, vm) {
        root.className = `flows-node-run-bubble ${vm.kind === 'ok' ? 'flows-node-run-bubble--ok' : 'flows-node-run-bubble--error'}`;
        root.setAttribute('role', 'status');
        root.textContent = '';

        if (vm.durationMs !== null) {
            const d = document.createElement('div');
            d.className = 'duration';
            d.textContent = this.t('node_run.duration_ms', { ms: String(vm.durationMs) });
            root.appendChild(d);
        }

        const list = document.createElement('ul');
        const lines = Array.isArray(vm.lines) ? vm.lines : [];
        if (lines.length === 0 && vm.kind === 'ok') {
            const one = document.createElement('li');
            one.textContent = this.t('node_run.empty_diff');
            list.appendChild(one);
        } else {
            for (let i = 0; i < lines.length; i += 1) {
                const li = document.createElement('li');
                li.textContent = lines[i];
                list.appendChild(li);
            }
        }
        root.appendChild(list);

        if (vm.canOpenFull === true) {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'full-btn';
            b.textContent = this.t('node_run.open_full');
            b.addEventListener('click', () => {
                if (vm.fullPayload !== null && typeof vm.fullPayload === 'object') {
                    this.emit('open-full', { value: vm.fullPayload });
                }
            });
            root.appendChild(b);
        }
    }

    _mountOrUpdatePortal() {
        if (!this._bubbleOpen || !this.viewModel) {
            this._teardownPortal();
            return;
        }
        ensurePortalStyles();
        this._bubbleZ = nextModalLayerZIndex();
        if (!this._portalEl) {
            const el = document.createElement('div');
            document.body.appendChild(el);
            this._portalEl = el;
            this._attachGlobalListeners();
        }
        this._fillPortalContent(this._portalEl, this.viewModel);
        this._syncPortalPosition();
        requestAnimationFrame(() => {
            requestAnimationFrame(() => this._syncPortalPosition());
        });
    }

    _onPlay() {
        this.emit('run', {});
    }

    render() {
        const title = this.t('test_panel.action_run');
        return html`
            <div class="root" part="root">
                <button
                    type="button"
                    class="play-btn"
                    title=${title}
                    aria-label=${title}
                    ?disabled=${this.busy}
                    @click=${this._onPlay}
                >
                    ${this.busy
                        ? html`<glass-spinner size="sm" aria-hidden="true"></glass-spinner>`
                        : html`<platform-icon name="play" size="18"></platform-icon>`}
                </button>
            </div>
        `;
    }
}

customElements.define('flows-node-run-control', FlowsNodeRunControl);
