/**
 * Per-component kebab popover: schema-driven quick props (boolean/enum +
 * required) and structural actions. Mutations emit the same events as
 * inspector / layers / right-click menu.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import {
    FLOW_UI_QUICK_REQUIRED_NAME,
    flowUIComponentQuickProps,
} from '@platform/lib/flow-ui/editor/component-quick-props.js';
import '@platform/lib/components/fields/platform-field.js';

export class FlowsInterfaceComponentMenu extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        x: { type: Number },
        y: { type: Number },
        component: { attribute: false },
        rootId: { type: String },
        locked: { type: Boolean },
        locale: { type: String },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: contents; }
        .menu {
            position: fixed;
            z-index: 60;
            min-width: 220px;
            max-width: 280px;
            padding: 6px;
            border: 1px solid var(--border-default);
            border-radius: var(--radius-md);
            background: var(--glass-solid-strong);
            box-shadow: var(--shadow-lg);
            display: grid;
            gap: 2px;
        }
        .section {
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
            color: var(--text-tertiary);
            padding: 6px 8px 4px;
        }
        .prop {
            display: grid;
            gap: 4px;
            padding: 6px 8px;
            border-radius: 7px;
        }
        .prop:hover { background: var(--glass-solid-medium); }
        .prop-label {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-secondary);
        }
        .options {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
        }
        .option {
            border: 1px solid var(--border-subtle);
            background: var(--bg-elevated);
            color: var(--text-secondary);
            border-radius: 999px;
            font-size: 11px;
            font-weight: 650;
            padding: 3px 9px;
            cursor: pointer;
        }
        .option[data-active="true"] {
            border-color: var(--accent);
            color: var(--accent);
            background: var(--accent-subtle);
        }
        .option:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
        .item {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-primary);
            font-size: 12px;
            text-align: left;
            padding: 7px 9px;
            border-radius: 7px;
            cursor: pointer;
            width: 100%;
            box-sizing: border-box;
        }
        .item:hover { background: var(--glass-solid-medium); }
        .item:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
        .item[data-danger="true"] { color: var(--error); }
        .sep { height: 1px; background: var(--border-subtle); margin: 3px 6px; }
    `];

    constructor() {
        super();
        this.x = 0;
        this.y = 0;
        this.component = null;
        this.rootId = 'root';
        this.locked = false;
        this.locale = 'en';
        this._onKeyDown = (event) => {
            if (!this.component) return;
            if (event.key === 'Escape') {
                event.preventDefault();
                this.emit('menu-close', {});
            }
        };
        this._onPointerDown = (event) => {
            if (!this.component) return;
            const path = typeof event.composedPath === 'function' ? event.composedPath() : [];
            if (path.includes(this.renderRoot?.querySelector?.('.menu'))) return;
            this.emit('menu-close', {});
        };
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('keydown', this._onKeyDown);
        window.addEventListener('pointerdown', this._onPointerDown, true);
    }

    disconnectedCallback() {
        window.removeEventListener('keydown', this._onKeyDown);
        window.removeEventListener('pointerdown', this._onPointerDown, true);
        super.disconnectedCallback();
    }

    _isRoot() {
        return this.component?.component_id === this.rootId;
    }

    _propLabel(prop) {
        if (prop.schemaLabel) {
            return this.locale === 'ru' ? prop.schemaLabel.ru : prop.schemaLabel.en;
        }
        return this.t(prop.labelKey);
    }

    _optionLabel(option) {
        return this.locale === 'ru' ? option.label.ru : option.label.en;
    }

    _propertyValue(name) {
        const value = this.component?.properties?.[name];
        return value;
    }

    _hasRequired() {
        const checks = Array.isArray(this.component?.checks) ? this.component.checks : [];
        return checks.some((check) => check && check.function === 'required');
    }

    _setBoolean(name, value) {
        if (name === FLOW_UI_QUICK_REQUIRED_NAME) {
            const checks = Array.isArray(this.component?.checks) ? [...this.component.checks] : [];
            const index = checks.findIndex((check) => check && check.function === 'required');
            if (value) {
                if (index < 0) checks.push({ function: 'required', message: '' });
            } else if (index >= 0) {
                checks.splice(index, 1);
            }
            this.emit('checks-change', { checks });
            return;
        }
        this.emit('property-change', { name, value: value === true });
    }

    _setEnum(name, value) {
        const current = this._propertyValue(name);
        const next = name === 'level' && /^\d+$/.test(value) ? Number(value) : value;
        if (current === next) return;
        this.emit('property-change', { name, value: next });
    }

    _action(eventName) {
        this.emit(eventName, { componentId: this.component.component_id });
        this.emit('menu-close', {});
    }

    _toggleVisibility() {
        const hidden = this.component.visibility === false
            || this.component.visibility?.visible === false;
        this.emit('component-visibility', {
            componentId: this.component.component_id,
            visible: hidden,
        });
        this.emit('menu-close', {});
    }

    _toggleLock() {
        this.emit('component-lock', { componentId: this.component.component_id });
        this.emit('menu-close', {});
    }

    _activateOnKey(event, action) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            action();
        }
    }

    _renderQuickProps() {
        const type = this.component?.type;
        if (typeof type !== 'string' || type === '') return nothing;
        const props = flowUIComponentQuickProps(type);
        if (props.length === 0) return nothing;
        return html`
            <div class="section">${this.t('interface_editor.quick_section')}</div>
            ${props.map((prop) => {
                if (prop.kind === 'boolean') {
                    const value = prop.name === FLOW_UI_QUICK_REQUIRED_NAME
                        ? this._hasRequired()
                        : this._propertyValue(prop.name) === true;
                    return html`<div class="prop">
                        <platform-field
                            type="boolean"
                            .label=${this._propLabel(prop)}
                            .value=${value}
                            mode="edit"
                            @change=${(event) => this._setBoolean(prop.name, event.detail.value === true)}
                        ></platform-field>
                    </div>`;
                }
                const current = this._propertyValue(prop.name);
                const currentText = current == null ? '' : String(current);
                return html`<div class="prop">
                    <div class="prop-label">${this._propLabel(prop)}</div>
                    <div class="options" role="group" aria-label=${this._propLabel(prop)}>
                        ${(prop.options || []).map((option) => html`<span
                            class="option"
                            role="button"
                            tabindex="0"
                            data-active=${option.value === currentText ? 'true' : 'false'}
                            @click=${() => this._setEnum(prop.name, option.value)}
                            @keydown=${(event) => this._activateOnKey(
                                event,
                                () => this._setEnum(prop.name, option.value),
                            )}
                        >${this._optionLabel(option)}</span>`)}
                    </div>
                </div>`;
            })}
            <div class="sep"></div>
        `;
    }

    _item(labelKey, onClick, { danger = false } = {}) {
        return html`<span
            class="item"
            role="menuitem"
            tabindex="0"
            data-danger=${danger ? 'true' : 'false'}
            @click=${onClick}
            @keydown=${(event) => this._activateOnKey(event, onClick)}
        >${this.t(labelKey)}</span>`;
    }

    render() {
        if (!this.component) return nothing;
        const isRoot = this._isRoot();
        const hidden = this.component.visibility === false
            || this.component.visibility?.visible === false;
        return html`<div
            class="menu"
            style=${`left:${this.x}px;top:${this.y}px`}
            role="menu"
            @pointerdown=${(event) => event.stopPropagation()}
        >
            ${this._renderQuickProps()}
            <div class="section">${this.t('interface_editor.quick_actions')}</div>
            ${!isRoot ? html`
                ${this._item(
                    'interface_editor.menu_duplicate',
                    () => this._action('component-duplicate'),
                )}
                ${this._item(
                    'interface_editor.menu_copy',
                    () => this._action('component-copy'),
                )}
            ` : nothing}
            ${this._item(
                'interface_editor.menu_paste',
                () => this._action('component-paste'),
            )}
            ${!isRoot
                ? this._item(
                    'interface_editor.menu_wrap_section',
                    () => this._action('component-wrap'),
                )
                : nothing}
            ${this._item(
                hidden ? 'interface_editor.layers_show' : 'interface_editor.layers_hide',
                () => this._toggleVisibility(),
            )}
            ${this._item(
                this.locked ? 'interface_editor.layers_unlock' : 'interface_editor.layers_lock',
                () => this._toggleLock(),
            )}
            ${!isRoot ? html`
                <div class="sep"></div>
                ${this._item(
                    'interface_editor.menu_delete',
                    () => this._action('component-delete-request'),
                    { danger: true },
                )}
            ` : nothing}
        </div>`;
    }
}

if (!customElements.get('flows-interface-component-menu')) {
    customElements.define('flows-interface-component-menu', FlowsInterfaceComponentMenu);
}
