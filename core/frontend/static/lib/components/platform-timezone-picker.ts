import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { getCachedSortedIanaTimeZones } from '../utils/iana-timezones.js';
import { PlatformPopover } from './platform-popover.js';

function zoneQuery(event: Event): string {
    const target = event.composedPath()[0];
    if (!(target instanceof HTMLInputElement)) {
        throw new Error('platform-timezone-picker: query target must be an input');
    }
    return target.value;
}
import './fields/platform-field-shell.js';

const LIST_MAX = 200;

function _filterZones(all: string[], query: unknown, currentValue: unknown): string[] {
    const q = (query == null ? '' : String(query)).trim().toLowerCase();
    const out = [];
    if (
        typeof currentValue === 'string' &&
        currentValue.length > 0 &&
        !all.includes(currentValue) &&
        (q.length === 0 || currentValue.toLowerCase().includes(q))
    ) {
        out.push(currentValue);
    }
    for (const z of all) {
        if (z.toLowerCase().includes(q)) {
            out.push(z);
        }
        if (out.length >= LIST_MAX) {
            break;
        }
    }
    return out;
}

export class PlatformTimezonePicker extends PlatformElement {
    static i18nNamespace = 'platform';
    declare value: string;
    declare label: string;
    declare error: string;
    declare placeholder: string;
    declare disabled: boolean;
    declare name: string;
    declare _inputText: string;
    declare _listOpen: boolean;
    declare _anchor: HTMLElement | null;
    private _allZones: string[];
    private _skipNextBlurChange: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        formStyles,
        css`
            :host {
                display: block;
                width: 100%;
            }
            .wrap {
                position: relative;
            }
            .list {
                margin: 0;
                padding: var(--space-1) 0;
                list-style: none;
            }
            .opt {
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .opt:hover,
            .opt:focus {
                background: var(--accent-soft, rgba(99, 102, 241, 0.12));
                outline: none;
            }
            .empty {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        value: { type: String },
        label: { type: String },
        error: { type: String },
        placeholder: { type: String },
        disabled: { type: Boolean, reflect: true },
        name: { type: String },
        _inputText: { type: String, state: true },
        _listOpen: { type: Boolean, state: true },
        _anchor: { state: true },
    };

    constructor() {
        super();
        this.value = '';
        this.label = '';
        this.error = '';
        this.placeholder = '';
        this.disabled = false;
        this.name = '';
        this._allZones = getCachedSortedIanaTimeZones();
        this._inputText = '';
        this._listOpen = false;
        this._skipNextBlurChange = false;
        /** @type {HTMLElement | null} */
        this._anchor = null;
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (changed.has('value')) {
            this._inputText = this.value;
        }
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (this._anchor === null) {
            const input = this.renderRoot?.querySelector?.('input.form-input');
            if (input instanceof HTMLElement) {
                this._anchor = input;
            }
        }
        if (this._listOpen && !this.disabled) {
            const popover = this.renderRoot.querySelector('platform-popover');
            if (!(popover instanceof PlatformPopover)) {
                throw new Error('platform-timezone-picker: open list popover is missing');
            }
            popover.reposition();
        }
    }

    _onPopoverDismiss(): void {
        this._listOpen = false;
    }

    get _visibleOptions(): string[] {
        return _filterZones(this._allZones, this._inputText, this.value);
    }

    _onInput(e: Event) {
        if (this.disabled) {
            return;
        }
        this._inputText = zoneQuery(e);
        this._listOpen = true;
        this.emit('input', { value: this._inputText });
    }

    _onFocus(): void {
        if (this.disabled) {
            return;
        }
        this._listOpen = true;
    }

    _onBlur(): void {
        window.setTimeout(() => {
            this._listOpen = false;
            if (this._skipNextBlurChange) {
                this._skipNextBlurChange = false;
                this.requestUpdate();
                return;
            }
            const v = this._inputText.trim();
            this.emit('change', { value: v });
            this.requestUpdate();
        }, 150);
    }

    _onOptionMouseDown(e: Event): void {
        e.preventDefault();
    }

    _onPick(zone: string): void {
        this._inputText = zone;
        this._listOpen = false;
        this._skipNextBlurChange = true;
        this.emit('input', { value: zone });
        this.emit('change', { value: zone });
        this.requestUpdate();
    }

    override render(): TemplateResult {
        const opts = this._visibleOptions;
        const listId = 'tz-list';
        const hasLabel = typeof this.label === 'string' && this.label.length > 0;
        const floated = this._inputText.length > 0 || this._listOpen;
        return html`
            <div class="wrap">
                <platform-field-shell
                    .label=${this.label}
                    .error=${this.error}
                    ?floated=${floated}
                    ?editable=${!this.disabled}
                    ?disabled=${this.disabled}
                >
                    <input
                        class="form-input"
                        type="text"
                        name=${this.name || nothing}
                        spellcheck="false"
                        autocomplete="off"
                        .value=${this._inputText}
                        placeholder=${floated || !hasLabel ? this.placeholder : ''}
                        ?disabled=${this.disabled}
                        role="combobox"
                        aria-expanded=${this._listOpen ? 'true' : 'false'}
                        aria-autocomplete="list"
                        aria-controls=${listId}
                        @input=${this._onInput}
                        @focus=${this._onFocus}
                        @blur=${this._onBlur}
                    />
                </platform-field-shell>
                <platform-popover
                    trigger="manual"
                    role="listbox"
                    placement="bottom-start"
                    match-width
                    offset="4"
                    .anchor=${this._anchor}
                    ?open=${this._listOpen && !this.disabled}
                    @popover-dismiss=${this._onPopoverDismiss}
                >
                    ${this._listOpen && !this.disabled
                        ? html`
                              <ul
                                  id=${listId}
                                  class="list"
                                  role="listbox"
                                  aria-label=${this.t('timezone_picker.aria_list')}
                              >
                                  ${opts.length === 0
                                      ? html`<li class="empty">${this.t('timezone_picker.empty')}</li>`
                                      : opts.map(
                                            (z) => html`
                                                <li
                                                    class="opt"
                                                    role="option"
                                                    @mousedown=${this._onOptionMouseDown}
                                                    @click=${() => this._onPick(z)}
                                                >
                                                    ${z}
                                                </li>
                                            `,
                                        )}
                              </ul>
                          `
                        : nothing}
                </platform-popover>
            </div>
        `;
    }
}

customElements.define('platform-timezone-picker', PlatformTimezonePicker);
