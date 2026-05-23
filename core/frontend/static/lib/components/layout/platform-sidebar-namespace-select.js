/**
 * platform-sidebar-namespace-select — единый блок выбора платформенного namespace
 * в шапке service sidebar: подпись, platform-field enum (`pill-density="dense"`),
 * необязательный слот `trailing` между полем и кнопками edit/add, затем опционально edit/add.
 *
 * Поведение выбора и модалки — у родителя; темизация через CSS-переменные на предке.
 */
import { html, css, nothing } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../fields/platform-field.js';
import '../platform-icon.js';

export class PlatformSidebarNamespaceSelect extends PlatformElement {
    static properties = {
        label: { type: String },
        value: { type: String },
        disabled: { type: Boolean },
        config: { type: Object },
        showEdit: { type: Boolean, attribute: 'show-edit' },
        showAdd: { type: Boolean, attribute: 'show-add' },
        editTitle: { type: String, attribute: 'edit-title' },
        addTitle: { type: String, attribute: 'add-title' },
        editIcon: { type: String, attribute: 'edit-icon' },
        fieldClass: { type: String, attribute: 'field-class' },
        pillDensity: { type: String, attribute: 'pill-density' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
                --platform-namespace-add-background: var(--accent);
                --platform-namespace-add-color: var(--text-inverse);
                --platform-namespace-edit-stroke: var(--border-subtle, rgba(255, 255, 255, 0.06));
                --platform-namespace-edit-fg: var(--text-secondary);
                --platform-namespace-edit-hover-bg: var(--accent-subtle);
                --platform-namespace-edit-hover-fg: var(--accent);
                --platform-namespace-edit-hover-stroke: var(--accent);
            }

            .root {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }

            .label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-tertiary);
                line-height: 1.2;
                align-self: stretch;
            }

            .row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                width: 100%;
            }

            .row platform-field {
                flex: 1 1 0;
                min-width: 0;
                display: block;
            }

            .btn-edit,
            .btn-add {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                box-sizing: border-box;
                width: calc(
                    2px + 2 * var(--field-pill-dense-padding-y) + var(--field-pill-dense-spin-height)
                );
                height: calc(
                    2px + 2 * var(--field-pill-dense-padding-y) + var(--field-pill-dense-spin-height)
                );
                padding: 0;
                border-radius: var(--radius-full);
                cursor: pointer;
                flex-shrink: 0;
                transition:
                    background var(--duration-fast),
                    color var(--duration-fast),
                    border-color var(--duration-fast),
                    transform var(--duration-fast);
            }

            .btn-edit {
                border: 1px solid var(--platform-namespace-edit-stroke);
                background: transparent;
                color: var(--platform-namespace-edit-fg);
            }

            .btn-edit:hover {
                background: var(--platform-namespace-edit-hover-bg);
                color: var(--platform-namespace-edit-hover-fg);
                border-color: var(--platform-namespace-edit-hover-stroke);
            }

            .btn-add {
                border: none;
                background: var(--platform-namespace-add-background);
                color: var(--platform-namespace-add-color);
            }

            .btn-add:hover {
                transform: scale(1.05);
            }

            .btn-edit:disabled,
            .btn-add:disabled {
                opacity: 0.45;
                cursor: not-allowed;
                transform: none;
            }

            ::slotted([slot='trailing']) {
                flex-shrink: 0;
                min-width: 0;
            }

            ::slotted(.platform-namespace-trailing-action-btn) {
                box-sizing: border-box;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: calc(
                    2px + 2 * var(--field-pill-dense-padding-y) + var(--field-pill-dense-spin-height)
                );
                height: calc(
                    2px + 2 * var(--field-pill-dense-padding-y) + var(--field-pill-dense-spin-height)
                );
                padding: 0;
                border: none;
                border-radius: var(--radius-full);
                cursor: pointer;
                background: var(--accent);
                color: var(--text-inverse);
                transition:
                    background var(--duration-fast),
                    opacity var(--duration-fast),
                    transform var(--duration-fast),
                    box-shadow var(--duration-fast);
                box-shadow: 0 2px 6px var(--accent-subtle, rgba(153, 166, 249, 0.16));
            }

            ::slotted(.platform-namespace-trailing-action-btn:hover:not(:disabled)) {
                filter: brightness(1.06);
                transform: translateY(-1px);
            }

            ::slotted(.platform-namespace-trailing-action-btn:active:not(:disabled)) {
                transform: translateY(0);
            }

            ::slotted(.platform-namespace-trailing-action-btn:disabled) {
                opacity: 0.55;
                cursor: not-allowed;
                transform: none;
                filter: none;
                box-shadow: none;
            }
        `,
    ];

    constructor() {
        super();
        this.label = '';
        this.value = '';
        this.disabled = false;
        this.config = {};
        this.showEdit = false;
        this.showAdd = true;
        this.editTitle = '';
        this.addTitle = '';
        this.editIcon = 'edit';
        this.fieldClass = '';
        this.pillDensity = 'dense';
    }

    _onFieldChange(e) {
        e.stopPropagation();
        this.dispatchEvent(
            new CustomEvent('change', {
                detail: e.detail,
                bubbles: true,
                composed: true,
            }),
        );
    }

    _onEditClick(e) {
        e.stopPropagation();
        this.dispatchEvent(
            new CustomEvent('edit-request', {
                bubbles: true,
                composed: true,
            }),
        );
    }

    _onAddClick(e) {
        e.stopPropagation();
        this.dispatchEvent(
            new CustomEvent('add-request', {
                bubbles: true,
                composed: true,
            }),
        );
    }

    render() {
        const fc =
            typeof this.fieldClass === 'string' && this.fieldClass.trim().length > 0
                ? this.fieldClass.trim()
                : nothing;
        return html`
            <div class="root" part="root">
                <span class="label">${this.label}</span>
                <div class="row" part="row">
                    <platform-field
                        type="enum"
                        mode="edit"
                        label=""
                        pill-density=${this.pillDensity}
                        class=${fc}
                        .value=${this.value}
                        .config=${this.config}
                        ?disabled=${this.disabled}
                        @change=${this._onFieldChange}
                    ></platform-field>
                    <slot name="trailing"></slot>
                    ${this.showEdit
                        ? html`
                              <button
                                  type="button"
                                  class="btn-edit"
                                  title=${this.editTitle}
                                  aria-label=${this.editTitle}
                                  ?disabled=${this.disabled}
                                  @click=${this._onEditClick}
                              >
                                  <platform-icon name=${this.editIcon} size="16"></platform-icon>
                              </button>
                          `
                        : ''}
                    ${this.showAdd
                        ? html`
                              <button
                                  type="button"
                                  class="btn-add"
                                  title=${this.addTitle}
                                  aria-label=${this.addTitle}
                                  ?disabled=${this.disabled}
                                  @click=${this._onAddClick}
                              >
                                  <platform-icon name="plus" size="16"></platform-icon>
                              </button>
                          `
                        : ''}
                </div>
            </div>
        `;
    }
}

customElements.define('platform-sidebar-namespace-select', PlatformSidebarNamespaceSelect);
