import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { getCachedSortedIanaTimeZones } from '../utils/iana-timezones.js';

const LIST_MAX = 200;

function _filterZones(all, query, currentValue) {
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

    static styles = [
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
                position: absolute;
                z-index: 30;
                left: 0;
                right: 0;
                top: 100%;
                margin: 0;
                padding: var(--space-1) 0;
                list-style: none;
                max-height: min(320px, 50vh);
                overflow: auto;
                background: var(--glass-solid-elevated, var(--glass-solid-subtle));
                border: 1px solid var(--glass-border-subtle, var(--border-default));
                border-radius: var(--radius-md);
                box-shadow: var(--shadow-md, 0 8px 24px rgba(0, 0, 0, 0.15));
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

    static properties = {
        value: { type: String },
        placeholder: { type: String },
        disabled: { type: Boolean, reflect: true },
        name: { type: String },
        _inputText: { type: String, state: true },
        _listOpen: { type: Boolean, state: true },
    };

    constructor() {
        super();
        this.value = '';
        this.placeholder = '';
        this.disabled = false;
        this.name = '';
        this._allZones = getCachedSortedIanaTimeZones();
        this._inputText = '';
        this._listOpen = false;
        this._skipNextBlurChange = false;
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('value')) {
            this._inputText = this.value;
        }
    }

    get _visibleOptions() {
        return _filterZones(this._allZones, this._inputText, this.value);
    }

    _onInput(e) {
        if (this.disabled) {
            return;
        }
        this._inputText = e.target.value;
        this._listOpen = true;
        this.emit('input', { value: this._inputText });
    }

    _onFocus() {
        if (this.disabled) {
            return;
        }
        this._listOpen = true;
    }

    _onBlur() {
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

    _onOptionMouseDown(e) {
        e.preventDefault();
    }

    _onPick(zone) {
        this._inputText = zone;
        this._listOpen = false;
        this._skipNextBlurChange = true;
        this.emit('input', { value: zone });
        this.emit('change', { value: zone });
        this.requestUpdate();
    }

    render() {
        const opts = this._visibleOptions;
        const listId = 'tz-list';
        return html`
            <div class="wrap">
                <input
                    class="form-input"
                    type="text"
                    name=${this.name || nothing}
                    spellcheck="false"
                    autocomplete="off"
                    .value=${this._inputText}
                    placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    role="combobox"
                    aria-expanded=${this._listOpen ? 'true' : 'false'}
                    aria-autocomplete="list"
                    aria-controls=${listId}
                    @input=${this._onInput}
                    @focus=${this._onFocus}
                    @blur=${this._onBlur}
                />
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
            </div>
        `;
    }
}

customElements.define('platform-timezone-picker', PlatformTimezonePicker);
