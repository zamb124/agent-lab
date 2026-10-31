/**
 * Подсказка по hover / focus. По умолчанию — кнопка «?»; опционально слот-контент
 * (кастомный триггер). Пузырёк живёт в `platform-popover` (top layer).
 * Свойство strategy для совместимости; `wide` — широкий моноширинный режим (JSON).
 * Для сложных подсказок доступны `summary`, `details`, `docHref`, `docLabel`.
 * `fill` растягивает кастомный slotted trigger на всю область хоста.
 * `placement`: `auto` — не вылезать за верх вьюпорта (снизу от якоря), `top` / `bottom` — жёстко.
 * `size`: `md` — кнопка 32×32 (как `flows-node-run-control`).
 */
import { html, css, nothing, unsafeCSS } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { resolveDocumentationHref } from '../utils/documentation-url.js';
import './platform-popover.js';
import type { PlatformPopover } from './platform-popover.js';
import type { SelectController } from '../events/select-controller.js';

function relatedNode(event: FocusEvent): Node | null {
    const related = event.relatedTarget;
    if (related === null) return null;
    if (!(related instanceof Node)) {
        throw new Error('platform-help-hint: focus moved to a non-node target');
    }
    return related;
}

const PORTAL_GAP_PX = 8;
const VIEWPORT_SIDE_INSET_PX = 8;
const CLOSE_DELAY_MS = 200;

const HINT_BUBBLE_CSS = `
        .platform-help-hint-portal-bubble {
            min-width: 200px;
            max-width: min(280px, 70vw);
            padding: 10px 12px;
            font-size: 12px;
            font-weight: 400;
            line-height: 1.45;
            text-align: left;
            white-space: normal;
            color: var(--text-primary);
            box-sizing: border-box;
        }
        .platform-help-hint-portal-bubble--wide {
            min-width: 200px;
            max-width: min(560px, 92vw);
            max-height: 50vh;
            overflow: auto;
            font-family: var(--font-mono);
            font-size: 11px;
            line-height: 1.4;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .platform-help-hint-portal-summary {
            margin: 0 0 4px;
            color: var(--text-primary);
            font-size: 12px;
            font-weight: 650;
            line-height: 1.3;
        }
        .platform-help-hint-portal-body {
            color: var(--text-secondary);
        }
        .platform-help-hint-portal-link {
            display: inline-flex;
            align-items: center;
            margin-top: 8px;
            color: var(--accent);
            font-weight: 600;
            text-decoration: none;
        }
        .platform-help-hint-portal-link:hover,
        .platform-help-hint-portal-link:focus {
            text-decoration: underline;
            outline: none;
        }
    `;

export class PlatformHelpHint extends PlatformElement {
    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        unsafeCSS(HINT_BUBBLE_CSS),
        css`
            :host {
                display: inline-flex;
                vertical-align: middle;
            }

            :host([fill]) {
                width: 100%;
                height: 100%;
            }

            .hint-root {
                position: relative;
                display: inline-flex;
                align-items: center;
                cursor: help;
            }

            :host([fill]) .hint-root {
                width: 100%;
                height: 100%;
            }

            :host([fill]) .hint-root ::slotted(*) {
                width: 100%;
                height: 100%;
            }

            .hint-btn {
                width: 20px;
                height: 20px;
                padding: 0;
                margin: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: 600;
                line-height: 1;
                color: var(--text-tertiary);
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-full);
                cursor: help;
                transition:
                    color var(--motion-duration-micro) ease,
                    background var(--motion-duration-micro) ease,
                    border-color var(--motion-duration-micro) ease;
            }

            :host([size='md']) .hint-btn {
                width: 32px;
                height: 32px;
                font-size: 14px;
                border-radius: var(--radius-md);
            }

            .hint-btn:hover,
            .hint-root:focus-within .hint-btn {
                color: var(--text-primary);
                background: rgba(255, 255, 255, 0.1);
                border-color: var(--border-default);
            }

        `,
    ];

    static override properties: PropertyDeclarations = {
        text: { type: String },
        summary: { type: String },
        details: { type: String },
        docHref: { type: String, attribute: 'doc-href' },
        docLabel: { type: String, attribute: 'doc-label' },
        label: { type: String },
        strategy: { type: String },
        /** @type {'auto'|'top'|'bottom'} */
        placement: { type: String, reflect: true },
        /** Площадь кнопки как у flows-node-run-control (32×32). */
        size: { type: String, reflect: true },
        wide: { type: Boolean, reflect: true },
        fill: { type: Boolean, reflect: true },
        _open: { state: true },
    };

    declare text: string;
    declare summary: string;
    declare details: string;
    declare docHref: string;
    declare docLabel: string;
    declare label: string;
    declare strategy: string;
    declare placement: string;
    declare size: string;
    declare wide: boolean;
    declare fill: boolean;
    declare _open: boolean;

    _bubbleId: string;
    _closeTimer: number | null;
    _anchor: HTMLElement | null;
    _localeSelect: SelectController<string>;

    constructor() {
        super();
        this.text = '';
        this.summary = '';
        this.details = '';
        this.docHref = '';
        this.docLabel = '';
        this.label = 'Справка';
        this.strategy = 'portal';
        this.placement = 'auto';
        this.size = '';
        this.wide = false;
        this.fill = false;
        this._open = false;
        this._bubbleId = `platform-help-hint-${Math.random().toString(36).slice(2, 10)}`;
        this._closeTimer = null;
        this._anchor = null;
        this._cancelClose = this._cancelClose.bind(this);
        this._scheduleClose = this._scheduleClose.bind(this);
        this._closeNow = this._closeNow.bind(this);
        this._onPortalFocusOut = this._onPortalFocusOut.bind(this);
        this._localeSelect = this.select((s) => s.i18n.locale);
    }

    override disconnectedCallback(): void {
        this._clearCloseTimer();
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (this._anchor === null) {
            const root = this.renderRoot?.querySelector('.hint-root');
            if (root instanceof HTMLElement) {
                this._anchor = root;
            }
        }
        if (this._open) {
            this.renderRoot?.querySelector<PlatformPopover>('platform-popover')?.reposition();
        }
    }

    _clearCloseTimer(): void {
        if (this._closeTimer !== null) {
            clearTimeout(this._closeTimer);
            this._closeTimer = null;
        }
    }

    _scheduleClose(): void {
        this._clearCloseTimer();
        this._closeTimer = window.setTimeout(() => {
            this._closeTimer = null;
            this._open = false;
        }, CLOSE_DELAY_MS);
    }

    _cancelClose(): void {
        this._clearCloseTimer();
    }

    _closeNow(): void {
        this._clearCloseTimer();
        this._open = false;
    }

    _hasDocLink(): boolean {
        return typeof this.docHref === 'string' && this.docHref.trim() !== '';
    }

    _textValue(value: unknown): string {
        return typeof value === 'string' ? value.trim() : '';
    }

    _renderBubble(): typeof nothing | TemplateResult {
        if (!this._open) {
            return nothing;
        }
        const summary = this._textValue(this.summary);
        const details = this._textValue(this.details);
        const text = this._textValue(this.text);
        const classes = this.wide
            ? 'platform-help-hint-portal-bubble platform-help-hint-portal-bubble--wide'
            : 'platform-help-hint-portal-bubble';

        // Широкая подсказка без структуры — это моноширинный дамп (JSON),
        // его нельзя резать на summary/body.
        const isRawWide = this.wide && summary === '' && details === '' && !this._hasDocLink();

        return html`
            <div
                id=${this._bubbleId}
                class=${classes}
                tabindex="-1"
                aria-label=${this._hasDocLink() ? (summary || this.label) : nothing}
                aria-modal=${this._hasDocLink() ? 'false' : nothing}
                @mouseenter=${this._cancelClose}
                @mouseleave=${this._scheduleClose}
                @focusin=${this._cancelClose}
                @focusout=${this._onPortalFocusOut}
            >
                ${isRawWide ? text : html`
                    ${summary !== ''
                        ? html`<div class="platform-help-hint-portal-summary">${summary}</div>`
                        : nothing}
                    ${(details || text) !== ''
                        ? html`<div class="platform-help-hint-portal-body">${details || text}</div>`
                        : nothing}
                    ${this._hasDocLink()
                        ? html`<a
                              class="platform-help-hint-portal-link"
                              href=${resolveDocumentationHref(this.docHref.trim(), {
                                  locale: this._localeSelect.value,
                              })}
                              target="_blank"
                              rel="noopener noreferrer"
                          >${this._textValue(this.docLabel) || 'Open documentation'}</a>`
                        : nothing}
                `}
            </div>
        `;
    }

    _openBubble(): void {
        this._cancelClose();
        this._open = true;
    }

    _onRootEnter(): void {
        this._cancelClose();
        this._openBubble();
    }

    _onRootLeave(): void {
        this._scheduleClose();
    }

    _onRootFocusIn(): void {
        this._cancelClose();
        this._openBubble();
    }

    _bubbleNode(): Element | null | undefined {
        return this.renderRoot?.querySelector('.platform-help-hint-portal-bubble');
    }

    _onRootFocusOut(e: FocusEvent): void {
        const related = relatedNode(e);
        if (related && this._bubbleNode()?.contains(related)) {
            return;
        }
        this._closeNow();
    }

    _onPortalFocusOut(e: FocusEvent): void {
        const related = relatedNode(e);
        const root = this.renderRoot?.querySelector('.hint-root');
        if ((related && this._bubbleNode()?.contains(related)) || (root && related && root.contains(related))) {
            return;
        }
        this._scheduleClose();
    }

    _onRootClick(e: MouseEvent): void {
        e.stopPropagation();
        this._cancelClose();
        this._openBubble();
    }

    override render(): TemplateResult {
        return html`
            <span
                class="hint-root"
                aria-expanded=${this._open ? 'true' : 'false'}
                aria-describedby=${this._open ? this._bubbleId : ''}
                @mouseenter=${this._onRootEnter}
                @mouseleave=${this._onRootLeave}
                @focusin=${this._onRootFocusIn}
                @focusout=${this._onRootFocusOut}
                @click=${this._onRootClick}
            >
                <slot>
                    <button type="button" class="hint-btn" aria-label=${this.label}>?</button>
                </slot>
            </span>
            <platform-popover
                trigger="manual"
                role=${this._hasDocLink() ? 'dialog' : 'tooltip'}
                placement=${this.placement === 'top' ? 'top' : 'bottom'}
                offset=${PORTAL_GAP_PX}
                viewport-padding=${VIEWPORT_SIDE_INSET_PX}
                ?flip=${this.placement === 'auto'}
                .anchor=${this._anchor}
                ?open=${this._open}
                @popover-dismiss=${this._closeNow}
            >
                ${this._renderBubble()}
            </platform-popover>
        `;
    }
}

customElements.define('platform-help-hint', PlatformHelpHint);
