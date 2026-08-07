/**
 * Component bindings: property name → absolute JSON Pointer with suggestions
 * built from the surface data model (no free-text guessing required).
 */
import { css, html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

function collectPointerPaths(value, prefix, out, depth = 0) {
    if (depth > 4 || value == null || typeof value !== 'object' || Array.isArray(value)) return out;
    for (const key of Object.keys(value)) {
        const path = `${prefix}/${key}`;
        out.push(path);
        collectPointerPaths(value[key], path, out, depth + 1);
    }
    return out;
}

export class FlowsInterfaceBindingEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        bindings: { attribute: false },
        dataModel: { attribute: false },
        draftName: { state: true },
        draftPath: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: grid; gap: 7px; }
        .title {
            font-size: 11px; font-weight: 700; text-transform: uppercase;
            letter-spacing: .06em; color: var(--text-tertiary); margin-top: 8px;
        }
        .row, .add { display: grid; grid-template-columns: 84px 1fr auto; gap: 6px; align-items: center; }
        input {
            min-width: 0; height: 30px; border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md); background: var(--bg-elevated);
            color: inherit; padding: 0 7px; font: inherit; font-size: 12px;
        }
        .icon-action {
            height: 30px; width: 30px; border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md); color: inherit; box-sizing: border-box;
            cursor: pointer; display: inline-flex; align-items: center;
            justify-content: center;
        }
        .icon-action:hover { border-color: var(--accent); color: var(--accent); }
        .icon-action.danger:hover { border-color: var(--error); color: var(--error); }
        .icon-action:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
    `];

    constructor() {
        super();
        this.bindings = {};
        this.dataModel = null;
        this.draftName = 'value';
        this.draftPath = '/values/';
    }

    _suggestions() {
        const paths = [];
        const model = this.dataModel || {};
        collectPointerPaths(model.values, '/values', paths);
        collectPointerPaths(model.content, '/content', paths);
        paths.push('/system/tasks', '/system/activeTask', '/system/agent');
        return paths;
    }

    _emitChange(name, path) {
        this.emit('binding-change', { name, path });
    }

    _iconAction({ labelKey, icon, danger, action }) {
        const label = this.t(labelKey);
        return html`<span
            class=${danger ? 'icon-action danger' : 'icon-action'}
            role="button"
            tabindex="0"
            title=${label}
            aria-label=${label}
            @click=${() => action()}
            @keydown=${(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    action();
                }
            }}
        ><platform-icon name=${icon} size="12"></platform-icon></span>`;
    }

    _add() {
        const name = String(this.draftName || '').trim();
        const path = String(this.draftPath || '').trim();
        if (!name) {
            throw new Error('binding editor: name is required');
        }
        if (!path.startsWith('/')) {
            throw new Error('binding editor: path must be an absolute JSON Pointer');
        }
        this._emitChange(name, path);
        this.draftName = 'value';
        this.draftPath = '/values/';
    }

    render() {
        const entries = Object.entries(this.bindings || {});
        const suggestions = this._suggestions();
        return html`
            <div class="title">${this.t('interface_editor.bindings_title')}</div>
            <datalist id="flow-ui-binding-paths">
                ${suggestions.map((path) => html`<option value=${path}></option>`)}
            </datalist>
            ${entries.map(([name, path]) => html`
                <div class="row">
                    <input data-canon="inline-edit" .value=${name} readonly>
                    <input
                        data-canon="combobox"
                        list="flow-ui-binding-paths"
                        .value=${path}
                        @change=${(event) => this._emitChange(name, event.target.value)}
                    >
                    ${this._iconAction({
                        labelKey: 'interface_editor.binding_remove',
                        icon: 'close',
                        danger: true,
                        action: () => this.emit('binding-remove', { name }),
                    })}
                </div>
            `)}
            <div class="add">
                <input
                    data-canon="inline-edit"
                    .value=${this.draftName}
                    placeholder=${this.t('interface_editor.binding_name')}
                    @input=${(event) => { this.draftName = event.target.value; }}
                >
                <input
                    data-canon="combobox"
                    list="flow-ui-binding-paths"
                    .value=${this.draftPath}
                    placeholder="/values/field"
                    @input=${(event) => { this.draftPath = event.target.value; }}
                >
                ${this._iconAction({
                    labelKey: 'interface_editor.binding_add',
                    icon: 'plus',
                    danger: false,
                    action: () => this._add(),
                })}
            </div>
        `;
    }
}

if (!customElements.get('flows-interface-binding-editor')) {
    customElements.define('flows-interface-binding-editor', FlowsInterfaceBindingEditor);
}
