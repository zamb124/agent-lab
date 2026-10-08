/**
 * platform-field-shell — единая pill-обёртка поля платформы.
 *
 * Floating label (Material outlined): label покоится внутри поля на месте
 * текста и при фокусе (`:focus-within`) или `floated` улетает на верхний
 * бордер. Бордер физически размыкается под label — notch через
 * `<fieldset>`+`<legend>` (работает с полупрозрачным glass-фоном).
 *
 * Слоты: default — контрол, `prefix`/`suffix` — адорнменты.
 * Плавающий label, notch, error-сообщение и фокус-ринг — только через этот
 * компонент; ручная разметка fieldset/legend в apps запрещена (ui_fields.mdc).
 */
import { html, css, nothing } from '../../lit-shim.js';
import { PlatformElement } from '../../platform-element/index.js';
import '../platform-help-hint.js';

const FOCUSABLE = 'input:not([type="hidden"]), textarea, select, button, [tabindex], [contenteditable="true"]';

function deepFindFocusable(root) {
    const direct = root.querySelector(FOCUSABLE);
    if (direct instanceof HTMLElement || direct instanceof SVGElement) {
        return direct;
    }
    for (const el of root.querySelectorAll('*')) {
        if (el.shadowRoot) {
            const found = deepFindFocusable(el.shadowRoot);
            if (found) return found;
        }
    }
    return null;
}

export class PlatformFieldShell extends PlatformElement {
    static properties = {
        label: { type: String },
        /** label прижат к бордеру (значение/view); фокус покрыт CSS :focus-within. */
        floated: { type: Boolean },
        density: { type: String },
        embed: { type: Boolean },
        editable: { type: Boolean },
        disabled: { type: Boolean },
        multiline: { type: Boolean },
        /** Растянуть pill на всю высоту хоста (редакторы: markdown, CodeMirror). */
        fill: { type: Boolean, reflect: true },
        error: { type: String },
        hint: { type: String },
        hintSummary: { type: String, attribute: 'hint-summary' },
        hintDetails: { type: String, attribute: 'hint-details' },
        hintDocHref: { type: String, attribute: 'hint-doc-href' },
        hintDocLabel: { type: String, attribute: 'hint-doc-label' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }

            :host([fill]) {
                display: flex;
                flex-direction: column;
            }

            :host([fill]) fieldset.field-pill {
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
            }

            :host([fill]) .field-pill-body,
            :host([fill]) .field-pill-control {
                flex: 1 1 auto;
            }

            :host([fill]) .field-pill-control {
                align-items: stretch;
            }

            :host([fill]) .field-pill-control-main {
                display: flex;
                flex-direction: column;
            }

            :host([fill]) .field-pill-control-main slot:not([name])::slotted(*) {
                flex: 1 1 auto;
                min-height: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.label = '';
        this.floated = false;
        this.density = 'default';
        this.embed = false;
        this.editable = false;
        this.disabled = false;
        this.multiline = false;
        this.fill = false;
        this.error = '';
        this.hint = '';
        this.hintSummary = '';
        this.hintDetails = '';
        this.hintDocHref = '';
        this.hintDocLabel = '';
    }

    willUpdate(changedProps) {
        super.willUpdate(changedProps);
        if (changedProps.has('density')) {
            const v = this.density;
            if (v !== 'default' && v !== 'compact' && v !== 'dense') {
                throw new Error(
                    `platform-field-shell: density must be "default", "compact" or "dense", got "${v}"`,
                );
            }
        }
    }

    _onPillClick(e) {
        if (!this.editable || this.disabled) return;
        const path = e.composedPath();
        for (const node of path) {
            if (node === this.renderRoot.querySelector('fieldset')) break;
            if (node instanceof HTMLElement
                && node.matches('input, textarea, select, button, a[href], [tabindex], [contenteditable="true"], platform-help-hint')) {
                return;
            }
        }
        const slot = this.renderRoot.querySelector('.field-pill-control-main slot:not([name])');
        if (!(slot instanceof HTMLSlotElement)) return;
        for (const el of slot.assignedElements({ flatten: true })) {
            let target = null;
            if (el.matches?.(FOCUSABLE)) {
                target = el;
            } else if (el.shadowRoot) {
                target = deepFindFocusable(el.shadowRoot);
            } else {
                target = el.querySelector?.(FOCUSABLE) ?? null;
            }
            if (target instanceof HTMLElement) {
                e.preventDefault();
                if (target instanceof HTMLButtonElement) {
                    target.click();
                } else {
                    target.focus();
                }
                return;
            }
        }
    }

    render() {
        const hasLabel = typeof this.label === 'string' && this.label !== '';
        const hasHint =
            (typeof this.hint === 'string' && this.hint !== '')
            || (typeof this.hintSummary === 'string' && this.hintSummary !== '')
            || (typeof this.hintDetails === 'string' && this.hintDetails !== '');
        const hasError = typeof this.error === 'string' && this.error !== '';
        const density =
            this.density === 'dense'
                ? 'field-pill--compact field-pill--dense'
                : this.density === 'compact'
                  ? 'field-pill--compact'
                  : '';
        const classes = [
            'field-pill',
            density,
            this.embed ? 'field-pill--embed' : '',
            this.multiline ? 'field-pill--textarea' : '',
            this.floated ? 'field-pill--float' : '',
            hasError ? 'field-pill--error' : '',
            this.disabled ? 'field-pill--disabled' : '',
        ].filter(Boolean).join(' ');
        return html`
            <fieldset
                class=${classes}
                data-mode=${this.editable ? 'edit' : 'view'}
                aria-label=${hasLabel ? this.label : nothing}
                @click=${this._onPillClick}
            >
                ${hasLabel
                    ? html`
                        <legend class="field-pill-legend"><span class="field-pill-legend-text">${this.label}</span>${hasHint
                            ? html`<span class="field-pill-legend-hint"></span>`
                            : nothing}</legend>
                    `
                    : nothing}
                <div class="field-pill-body">
                    <div class="field-pill-control">
                        <slot name="prefix"></slot>
                        <div class="field-pill-control-main">
                            ${hasLabel
                                ? html`
                                    <div class="field-pill-float" aria-hidden="true">
                                        <span class="field-pill-label">${this.label}</span>
                                        ${hasHint
                                            ? html`<platform-help-hint
                                                .text=${this.hint}
                                                .summary=${this.hintSummary}
                                                .details=${this.hintDetails}
                                                .docHref=${this.hintDocHref}
                                                .docLabel=${this.hintDocLabel}
                                            ></platform-help-hint>`
                                            : nothing}
                                    </div>
                                `
                                : nothing}
                            <slot></slot>
                        </div>
                        <slot name="suffix"></slot>
                    </div>
                </div>
            </fieldset>
            ${hasError
                ? html`<div class="field-pill-message" role="alert">${this.error}</div>`
                : nothing}
        `;
    }
}

customElements.define('platform-field-shell', PlatformFieldShell);
