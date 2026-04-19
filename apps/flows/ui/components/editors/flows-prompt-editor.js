/**
 * flows-prompt-editor — textarea с авто-resize и popover-автодополнением `@var:`.
 *
 * Property API:
 *   - value: string
 *   - flowVariables: object  // { var_name: <FlowVariableConfig> | <any> }
 *   - placeholder: string
 *   - minRows: number
 *
 * Events (emit):
 *   - 'change' { value }
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const VAR_TRIGGER_RE = /@var:([A-Za-z0-9_]*)$/;

export class FlowsPromptEditor extends PlatformElement {
    static properties = {
        value: { type: String },
        flowVariables: { type: Object },
        placeholder: { type: String },
        minRows: { type: Number },
        _suggestions: { state: true },
        _activeIndex: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; position: relative; }
            textarea {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                font-family: var(--font-mono, monospace);
                font-size: var(--text-sm);
                line-height: var(--leading-normal);
                resize: vertical;
                min-height: calc(var(--space-8) * 2);
            }
            textarea:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-subtle);
            }
            .popover {
                position: absolute;
                z-index: var(--z-dropdown);
                min-width: 220px;
                max-height: 240px;
                overflow-y: auto;
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-medium);
                padding: var(--space-1);
            }
            .item {
                display: flex; flex-direction: column;
                gap: 2px;
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .item .key { font-family: var(--font-mono, monospace); color: var(--accent); }
            .item .meta { font-size: var(--text-xs); color: var(--text-tertiary); }
            .item[active], .item:hover { background: var(--glass-solid-medium); }
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.flowVariables = null;
        this.placeholder = '';
        this.minRows = 4;
        this._suggestions = [];
        this._activeIndex = 0;
        this._popoverPos = null;
    }

    _variableEntries() {
        const vars = this.flowVariables;
        if (!vars || typeof vars !== 'object') return [];
        return Object.entries(vars).map(([key, raw]) => {
            const meta = raw && typeof raw === 'object' ? raw : { value: raw };
            return {
                key,
                title: typeof meta.title === 'string' ? meta.title : '',
                description: typeof meta.description === 'string' ? meta.description : '',
            };
        });
    }

    _onInput(e) {
        const ta = e.target;
        const v = ta.value;
        this.value = v;
        this.emit('change', { value: v });
        this._refreshSuggestions(ta);
        this._autoResize(ta);
    }

    _autoResize(ta) {
        ta.style.height = 'auto';
        ta.style.height = `${Math.max(ta.scrollHeight, this.minRows * 22)}px`;
    }

    _refreshSuggestions(ta) {
        const cursor = ta.selectionStart;
        const text = ta.value.slice(0, cursor);
        const m = text.match(VAR_TRIGGER_RE);
        if (!m) {
            this._suggestions = [];
            return;
        }
        const prefix = m[1].toLowerCase();
        const items = this._variableEntries()
            .filter((it) => it.key.toLowerCase().startsWith(prefix))
            .slice(0, 8);
        this._suggestions = items;
        this._activeIndex = 0;
    }

    _onKeydown(e) {
        if (this._suggestions.length === 0) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this._activeIndex = (this._activeIndex + 1) % this._suggestions.length;
            return;
        }
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            this._activeIndex = (this._activeIndex - 1 + this._suggestions.length) % this._suggestions.length;
            return;
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
            const pick = this._suggestions[this._activeIndex];
            if (pick) {
                e.preventDefault();
                this._insertSuggestion(pick.key);
            }
            return;
        }
        if (e.key === 'Escape') {
            e.preventDefault();
            this._suggestions = [];
        }
    }

    _insertSuggestion(key) {
        const ta = this.renderRoot.querySelector('textarea');
        if (!ta) return;
        const cursor = ta.selectionStart;
        const before = ta.value.slice(0, cursor);
        const after = ta.value.slice(cursor);
        const replaced = before.replace(VAR_TRIGGER_RE, `@var:${key}`);
        const newValue = replaced + after;
        const newCursor = replaced.length;
        this.value = newValue;
        this.emit('change', { value: newValue });
        this._suggestions = [];
        queueMicrotask(() => {
            ta.value = newValue;
            ta.focus();
            ta.setSelectionRange(newCursor, newCursor);
            this._autoResize(ta);
        });
    }

    firstUpdated() {
        const ta = this.renderRoot.querySelector('textarea');
        if (ta) this._autoResize(ta);
    }

    render() {
        const showPopover = this._suggestions.length > 0;
        return html`
            <textarea
                .value=${this.value}
                placeholder=${this.placeholder}
                rows=${this.minRows}
                @input=${this._onInput}
                @keydown=${this._onKeydown}
                @blur=${() => { setTimeout(() => { this._suggestions = []; }, 120); }}
            ></textarea>
            ${showPopover ? html`
                <div class="popover">
                    ${this._suggestions.map((it, i) => html`
                        <div
                            class="item"
                            ?active=${i === this._activeIndex}
                            @mousedown=${(e) => { e.preventDefault(); this._insertSuggestion(it.key); }}
                        >
                            <span class="key">@var:${it.key}</span>
                            ${it.title ? html`<span class="meta">${it.title}</span>` : ''}
                            ${it.description ? html`<span class="meta">${it.description}</span>` : ''}
                        </div>
                    `)}
                </div>
            ` : ''}
            <div class="hint">${this.t('prompt_editor.var_hint')}</div>
        `;
    }
}

customElements.define('flows-prompt-editor', FlowsPromptEditor);
