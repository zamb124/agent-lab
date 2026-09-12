/**
 * Панель «Свойства» выбранного блока: редакторы по виду свойства из JSON Schema грамматики
 * (шаблоны с автодополнением ``{path}``, пути state с подсказками, действия, условия, опции),
 * проблемы блока и превью контракта страницы (что уйдёт во flow при действии).
 *
 * События: ``property-change {blockId, property, value}``, ``block-action {blockId, action}``.
 */

import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-variable-input.js';
import '@platform/lib/components/platform-code-editor.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import { INPUT_BLOCK_TYPES } from '@platform/lib/flow-ui/protocol/constants.js';
import { catalogEntry, isFrozenPath, walkPage } from './interface-editor-domain.js';

const HIDDEN_PROPERTIES = new Set(['type', 'blocks']);
const CONVERSATION_DEF = 'FlowUIConversationSettings';

/** Значение условия: JSON-литерал (число, bool, null, объект) или строка как есть. */
function parseConditionValue(text) {
    const trimmed = text.trim();
    if (trimmed === '') return null;
    if (/^(-?\d+(\.\d+)?|true|false|null|\{.*\}|\[.*\])$/s.test(trimmed)) return JSON.parse(trimmed);
    return trimmed;
}

export class FlowsInterfacePropertiesPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        block: { attribute: false },
        page: { attribute: false },
        document: { attribute: false },
        catalog: { attribute: false },
        schema: { attribute: false },
        frozen: { attribute: false },
        statePaths: { attribute: false },
        sampleState: { attribute: false },
        problems: { attribute: false },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: block; min-height: 0; overflow: auto; padding: 12px; }
        .head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
        .head .type { font-size: 13px; font-weight: 650; color: var(--text-primary); }
        .head code { font-size: 11px; color: var(--text-tertiary); }
        .fields { display: grid; gap: 10px; }
        .row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; gap: 6px; align-items: end; }
        .row platform-button { margin-bottom: 2px; }
        .sub { display: grid; gap: 8px; padding: 10px; border: 1px solid var(--border-subtle); border-radius: 10px; background: var(--glass-solid-subtle); }
        .sub-title { display: flex; align-items: center; justify-content: space-between; font-size: 12px; font-weight: 650; color: var(--text-secondary); }
        .problem { display: flex; gap: 6px; align-items: center; font-size: 12px; color: var(--error); }
        .problem[data-severity='warning'] { color: var(--warning); }
        .contract { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-subtle); display: grid; gap: 6px; font-size: 12px; color: var(--text-secondary); }
        .contract .title { font-weight: 650; color: var(--text-primary); }
        .contract code { color: var(--text-primary); }
        .actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; }
        .empty { padding: 32px 8px; text-align: center; color: var(--text-tertiary); font-size: 12.5px; }
        .html-source { display: grid; gap: 6px; }
        .html-source platform-code-editor { --code-editor-min-height: 160px; border: 1px solid var(--border-subtle); border-radius: 10px; overflow: hidden; }
        .hint { font-size: 11px; color: var(--text-tertiary); }
    `];

    constructor() {
        super();
        this.block = null;
        this.page = null;
        this.document = null;
        this.catalog = [];
        this.schema = null;
        this.frozen = new Set();
        this.statePaths = [];
        this.sampleState = {};
        this.problems = [];
    }

    _change(property, value) {
        this.emit('property-change', { blockId: this.block.block_id, property, value });
    }

    _label(name) {
        return this.t(`interface_editor.prop_${name}`);
    }

    _pathSuggestions() {
        return this.statePaths.filter((entry) => !entry.protected).map((entry) => entry.path);
    }

    _statePreview() {
        return this.sampleState;
    }

    _problemsFor(property) {
        return this.problems.filter((problem) => problem.property === property).map((problem) => html`<div class="problem" data-severity=${problem.severity}>
            <platform-icon name=${problem.severity === 'error' ? 'notification-error' : 'alert-triangle'} size="12"></platform-icon>${this.t(`interface_editor.problem_${problem.code}`, problem.params)}
        </div>`);
    }

    // --- Редакторы по виду ----------------------------------------------------------------------

    /** Однострочный шаблон — CodeMirror с автодополнением ``{path}``; многострочный (markdown, code) — textarea. */
    _template(name, value) {
        const text = typeof value === 'string' ? value : '';
        if (name === 'markdown' || name === 'code') {
            return html`<platform-field mode="edit" type="text" .label=${this._label(name)} .value=${text} .placeholder=${this.t('interface_editor.template_placeholder')}
                @change=${(event) => this._change(name, event.detail.value)}></platform-field>`;
        }
        return html`<platform-variable-input syntax="brace" .label=${this._label(name)} .value=${text}
            .statePreview=${this._statePreview()} .statePaths=${this._pathSuggestions()} .placeholder=${this.t('interface_editor.template_placeholder')}
            @change=${(event) => this._change(name, event.detail.value)}></platform-variable-input>`;
    }

    _statePath(name, value, required, hint) {
        const text = typeof value === 'string' ? value : '';
        return html`<platform-field mode="edit" type="string" .label=${this._label(name)} .value=${text} .suggestions=${this._pathSuggestions()}
            .hint=${hint ? this.t('interface_editor.field_hint', { path: text !== '' && !isFrozenPath(text, this.frozen) ? text : 'email' }) : ''} .placeholder=${'email'}
            @change=${(event) => this._change(name, event.detail.value === '' && !required ? null : event.detail.value)}></platform-field>`;
    }

    _action(name, value, required) {
        const enabled = value !== null && value !== undefined;
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label(name)}</span>
                ${required ? nothing : html`<platform-field mode="edit" type="boolean" pill-embed .value=${enabled} @change=${(event) => this._change(name, event.detail.value ? { name: 'submit', payload: {} } : null)}></platform-field>`}
            </div>
            ${enabled ? html`
                <platform-field mode="edit" type="string" .label=${this.t('interface_editor.action_name')} .value=${value.name} .placeholder=${'submit'} .hint=${this.t('interface_editor.action_name_hint')}
                    @change=${(event) => this._change(name, { ...value, name: event.detail.value })}></platform-field>
                <platform-field mode="edit" type="object" .label=${this.t('interface_editor.action_payload')} .value=${value.payload}
                    @change=${(event) => this._change(name, { ...value, payload: event.detail.value })}></platform-field>
            ` : nothing}
        </div>`;
    }

    _condition(value) {
        const enabled = value !== null && value !== undefined;
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label('visible_when')}</span>
                <platform-field mode="edit" type="boolean" pill-embed .value=${enabled} @change=${(event) => this._change('visible_when', event.detail.value ? { path: 'status' } : null)}></platform-field>
            </div>
            ${enabled ? html`
                <platform-field mode="edit" type="string" .label=${this.t('interface_editor.condition_path')} .value=${value.path} .suggestions=${this._pathSuggestions()}
                    @change=${(event) => this._change('visible_when', { ...value, path: event.detail.value })}></platform-field>
                <platform-field mode="edit" type="string" .label=${this.t('interface_editor.condition_equals')} .hint=${this.t('interface_editor.condition_equals_hint')}
                    .value=${'equals' in value ? (typeof value.equals === 'string' ? value.equals : JSON.stringify(value.equals)) : ''}
                    @change=${(event) => { const next = { path: value.path }; const parsed = parseConditionValue(event.detail.value); if (event.detail.value.trim() !== '') next.equals = parsed; this._change('visible_when', next); }}></platform-field>
            ` : nothing}
        </div>`;
    }

    _height(name, value) {
        const auto = value === 'auto';
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label(name)}</span>
                <platform-field mode="edit" type="boolean" pill-embed .label=${this.t('interface_editor.height_auto')} .value=${auto} @change=${(event) => this._change(name, event.detail.value ? 'auto' : 320)}></platform-field>
            </div>
            ${auto ? nothing : html`<platform-field mode="edit" type="integer" .value=${value} @change=${(event) => this._change(name, event.detail.value)}></platform-field>`}
        </div>`;
    }

    _pairs(name, value, keys, labels) {
        const items = Array.isArray(value) ? value : [];
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label(name)}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.add_item')} @click=${() => this._change(name, [...items, { [keys[0]]: `${keys[0]}_${items.length + 1}`, [keys[1]]: '' }])}><platform-icon name="plus" size="14"></platform-icon></platform-button>
            </div>
            ${items.map((item, index) => html`<div class="row">
                <platform-field mode="edit" type="string" pill-embed .label=${labels[0]} .value=${item[keys[0]]} @change=${(event) => this._change(name, items.map((entry, position) => (position === index ? { ...entry, [keys[0]]: event.detail.value } : entry)))}></platform-field>
                <platform-field mode="edit" type="string" pill-embed .label=${labels[1]} .value=${item[keys[1]]} @change=${(event) => this._change(name, items.map((entry, position) => (position === index ? { ...entry, [keys[1]]: event.detail.value } : entry)))}></platform-field>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.remove_item')} @click=${() => this._change(name, items.filter((_entry, position) => position !== index))}><platform-icon name="close" size="14"></platform-icon></platform-button>
            </div>`)}
        </div>`;
    }

    _columns(value) {
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label('columns')}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.add_item')} ?disabled=${value.length >= 4} @click=${() => this._change('columns', [...value, { width: 1, blocks: [] }])}><platform-icon name="plus" size="14"></platform-icon></platform-button>
            </div>
            ${value.map((column, index) => html`<div class="row">
                <platform-field mode="edit" type="integer" pill-embed .label=${this.t('interface_editor.column_width', { index: index + 1 })} .value=${column.width}
                    @change=${(event) => this._change('columns', value.map((entry, position) => (position === index ? { ...entry, width: event.detail.value } : entry)))}></platform-field>
                <span class="hint">${this.t('interface_editor.column_blocks', { count: column.blocks.length })}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.remove_item')} ?disabled=${value.length <= 1 || column.blocks.length > 0} @click=${() => this._change('columns', value.filter((_entry, position) => position !== index))}><platform-icon name="close" size="14"></platform-icon></platform-button>
            </div>`)}
        </div>`;
    }

    _tabs(value) {
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label('tabs')}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.add_item')} @click=${() => this._change('tabs', [...value, { title: this.t('interface_editor.default_tab'), blocks: [] }])}><platform-icon name="plus" size="14"></platform-icon></platform-button>
            </div>
            ${value.map((tab, index) => html`<div class="row">
                <platform-variable-input syntax="brace" .label=${this.t('interface_editor.tab_title', { index: index + 1 })} .value=${tab.title} .statePreview=${this._statePreview()} .statePaths=${this._pathSuggestions()}
                    @change=${(event) => this._change('tabs', value.map((entry, position) => (position === index ? { ...entry, title: event.detail.value } : entry)))}></platform-variable-input>
                <span class="hint">${this.t('interface_editor.column_blocks', { count: tab.blocks.length })}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.remove_item')} ?disabled=${value.length <= 1 || tab.blocks.length > 0} @click=${() => this._change('tabs', value.filter((_entry, position) => position !== index))}><platform-icon name="close" size="14"></platform-icon></platform-button>
            </div>`)}
        </div>`;
    }

    _conversationSettings(value) {
        const definition = this.schema.$defs[CONVERSATION_DEF];
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label('settings')}</span></div>
            ${Object.entries(definition.properties).map(([name, propertySchema]) => {
                const label = this.t(`interface_editor.conversation_${name}`);
                const current = value[name];
                const set = (next) => this._change('settings', { ...value, [name]: next });
                if (propertySchema.type === 'boolean') return html`<platform-field mode="edit" type="boolean" pill-embed .label=${label} .value=${current} @change=${(event) => set(event.detail.value)}></platform-field>`;
                if (Array.isArray(propertySchema.enum)) return html`<platform-field mode="edit" type="enum" pill-embed .label=${label} .value=${current} .config=${{ values: propertySchema.enum.map((option) => ({ value: option, label: this.t(`interface_editor.enum_${option}`) })) }} @change=${(event) => set(event.detail.value)}></platform-field>`;
                if (propertySchema.type === 'array') return html`<platform-field mode="edit" type="array" pill-embed .label=${label} .value=${current} .config=${{ preserve_case: true }} @change=${(event) => set(event.detail.value)}></platform-field>`;
                return html`<platform-variable-input syntax="brace" .label=${label} .value=${current} .statePreview=${this._statePreview()} .statePaths=${this._pathSuggestions()} @change=${(event) => set(event.detail.value)}></platform-variable-input>`;
            })}
        </div>`;
    }

    _htmlSource(value) {
        return html`<div class="html-source">
            <div class="sub-title"><span>${this._label('source')}</span>
                <platform-button secondary density="compact" @click=${() => this.openModal('flows.interface_html_editor', {
                    source: value, block: this.block, sampleState: this.sampleState, statePaths: this._pathSuggestions(),
                    onApply: (source) => this._change('source', source),
                })}><platform-icon name="fullscreen" size="13"></platform-icon>${this.t('interface_editor.html_open_editor')}</platform-button>
            </div>
            <platform-code-editor language="html" line-wrapping .value=${value} @change=${(event) => this._change('source', event.detail.value)}></platform-code-editor>
            <div class="hint">${this.t('interface_editor.html_hint')}</div>
        </div>`;
    }

    _editor(property) {
        const { name, kind } = property;
        const value = this.block[name];
        const isInput = INPUT_BLOCK_TYPES.has(this.block.type);
        switch (kind) {
            case 'const': case 'blocks': return nothing;
            case 'template': return this._template(name, value);
            case 'string': return this.block.type === 'html' && name === 'source' ? this._htmlSource(value)
                : html`<platform-field mode="edit" type="string" .label=${this._label(name)} .value=${typeof value === 'string' ? value : ''} @change=${(event) => this._change(name, event.detail.value)}></platform-field>`;
            case 'state_path': return this._statePath(name, value, property.required, isInput && name === 'field');
            case 'height': return this._height(name, value);
            case 'action': return this._action(name, value, property.required);
            case 'condition': return this._condition(value);
            case 'conversation_settings': return this._conversationSettings(value);
            case 'enum': return html`<platform-field mode="edit" type="enum" .label=${this._label(name)} .value=${String(value)}
                .config=${{ values: property.enum.map((option) => ({ value: String(option), label: this.t(`interface_editor.enum_${option}`) })) }}
                @change=${(event) => this._change(name, property.enum.find((option) => String(option) === event.detail.value))}></platform-field>`;
            case 'boolean': return html`<platform-field mode="edit" type="boolean" .label=${this._label(name)} .value=${value === true} @change=${(event) => this._change(name, event.detail.value)}></platform-field>`;
            case 'integer': case 'number': return html`<platform-field mode="edit" type=${kind} .label=${this._label(name)} .value=${value} @change=${(event) => this._change(name, event.detail.value)}></platform-field>`;
            case 'json': return html`<platform-field mode="edit" type="object" .label=${this._label(name)} .value=${value} @change=${(event) => this._change(name, event.detail.value)}></platform-field>`;
            case 'columns': return this._columns(value);
            case 'tabs': return this._tabs(value);
            case 'options': return this._pairs(name, value, ['value', 'label'], [this.t('interface_editor.option_value'), this.t('interface_editor.option_label')]);
            case 'table_columns': return this._pairs(name, value, ['key', 'label'], [this.t('interface_editor.column_key'), this.t('interface_editor.option_label')]);
            case 'state_path_list': case 'template_list': case 'string_list': return html`<platform-field mode="edit" type="array" .label=${this._label(name)} .value=${Array.isArray(value) ? value : []} .config=${{ preserve_case: true }} .placeholder=${kind === 'state_path_list' ? 'email' : ''} @change=${(event) => this._change(name, event.detail.value)}></platform-field>`;
            case 'select_default': return html`<platform-field mode="edit" type=${this.block.multiple === true ? 'array' : 'string'} .label=${this._label(name)} .value=${value ?? (this.block.multiple === true ? [] : '')} .config=${{ preserve_case: true }} @change=${(event) => this._change(name, event.detail.value === '' ? null : event.detail.value)}></platform-field>`;
            default: throw new Error(`interface editor: no editor for property kind ${kind}`);
        }
    }

    _renderContract() {
        const inputs = walkPage(this.page).filter(({ block }) => INPUT_BLOCK_TYPES.has(block.type));
        const actions = [...new Set(walkPage(this.page).flatMap(({ block }) => [block.action, block.row_action].filter((action) => action && typeof action.name === 'string').map((action) => action.name)))];
        if (inputs.length === 0 && actions.length === 0) return nothing;
        return html`<div class="contract">
            <div class="title">${this.t('interface_editor.contract_title')}</div>
            ${inputs.length > 0 ? html`<div>${this.t('interface_editor.contract_fields')}: ${inputs.map(({ block }, index) => html`${index > 0 ? ', ' : ''}<code>${block.field}</code>`)}</div>` : nothing}
            ${actions.length > 0 ? html`<div>${this.t('interface_editor.contract_actions')}: ${actions.map((name, index) => html`${index > 0 ? ', ' : ''}<code>${name}</code>`)}</div>` : nothing}
            <div class="hint">${this.t('interface_editor.contract_hint')}</div>
        </div>`;
    }

    render() {
        if (this.block === null || this.page === null || this.schema === null) return html`<div class="empty">${this.t('interface_editor.properties_empty')}</div>${this.page === null ? nothing : this._renderContract()}`;
        const entry = catalogEntry(this.catalog, this.block.type);
        return html`
            <div class="head"><platform-icon name=${entry.icon} size="16"></platform-icon><span class="type">${this.t(`interface_editor.block_${this.block.type}`)}</span></div>
            <div class="fields">
                <platform-field mode="edit" type="string" .label=${this._label('block_id')} .value=${this.block.block_id} .hint=${this.t('interface_editor.block_id_hint')} @change=${(event) => this._change('block_id', event.detail.value)}></platform-field>
                ${this._problemsFor('block_id')}
                ${entry.properties.filter((property) => !HIDDEN_PROPERTIES.has(property.name) && property.name !== 'block_id').map((property) => html`${this._editor(property)}${this._problemsFor(property.name)}`)}
            </div>
            <div class="actions">
                <platform-button secondary density="compact" @click=${() => this.emit('block-action', { blockId: this.block.block_id, action: 'duplicate' })}><platform-icon name="copy" size="13"></platform-icon>${this.t('interface_editor.block_duplicate')}</platform-button>
                <platform-button secondary density="compact" @click=${() => this.emit('block-action', { blockId: this.block.block_id, action: 'wrap' })}><platform-icon name="square" size="13"></platform-icon>${this.t('interface_editor.block_wrap_section')}</platform-button>
                <platform-button danger density="compact" @click=${() => this.emit('block-action', { blockId: this.block.block_id, action: 'remove' })}><platform-icon name="trash" size="13"></platform-icon>${this.t('interface_editor.block_remove')}</platform-button>
            </div>
            ${this._renderContract()}
        `;
    }
}

if (!customElements.get('flows-interface-properties-panel')) customElements.define('flows-interface-properties-panel', FlowsInterfacePropertiesPanel);
