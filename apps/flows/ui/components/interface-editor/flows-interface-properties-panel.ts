/**
 * Панель «Свойства» выбранного блока: редакторы по виду свойства из JSON Schema грамматики
 * (шаблоны с автодополнением ``{path}``, пути state с подсказками, действия, условия, опции),
 * проблемы блока и превью контракта страницы (что уйдёт во flow при действии).
 *
 * События: ``property-change {blockId, property, value}``, ``page-property-change {property, value}``,
 * ``block-action {blockId, action}``, ``image-upload {blockId, property, file}`` — файл иконки; хост грузит и пишет URL.
 */

import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-variable-input.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import { INPUT_BLOCK_TYPES } from '@platform/lib/flow-ui/protocol/constants.js';
import { catalogEntry, isFrozenPath, walkPage } from './interface-editor-domain.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

function documentPages(document: unknown): unknown[] {
    if (!isPlainRecord(document)) return [];
    const pages = document.pages;
    if (pages === undefined || pages === null) return [];
    if (!Array.isArray(pages)) throw new Error('interface editor: document.pages must be an array');
    return pages;
}

function actionField(action: unknown, field: string): unknown {
    if (!isPlainRecord(action)) return undefined;
    return action[field];
}

function objectValue(value: unknown): Record<string, unknown> {
    if (!isPlainRecord(value)) {
        throw new Error('flows-interface-properties-panel: object value required');
    }
    return value;
}

function conditionEqualsText(value: Record<string, unknown>): string {
    if (!('equals' in value)) return '';
    const equals = value.equals;
    if (typeof equals === 'string') return equals;
    return JSON.stringify(equals);
}

const HIDDEN_PROPERTIES = new Set(['type', 'blocks']);
const CONVERSATION_DEF = 'FlowUIConversationSettings';

/** Значение условия: JSON-литерал (число, bool, null, объект) или строка как есть. */
function parseConditionValue(text: any) {
    const trimmed = text.trim();
    if (trimmed === '') return null;
    if (/^(-?\d+(\.\d+)?|true|false|null|\{.*\}|\[.*\])$/s.test(trimmed)) return JSON.parse(trimmed);
    return trimmed;
}

function clickKindValue(kinds: readonly { value: string }[]): string {
    const first = kinds[0];
    if (first === undefined) {
        throw new Error('flows-interface-properties-panel: click kind missing');
    }
    return first.value;
}

export class FlowsInterfacePropertiesPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        block: { attribute: false },
        page: { attribute: false },
        document: { attribute: false },
        catalog: { attribute: false },
        schema: { attribute: false },
        frozen: { attribute: false },
        statePaths: { attribute: false },
        sampleState: { attribute: false },
        problems: { attribute: false },
    }
    declare block: any;
    declare page: any;
    declare document: any;
    declare catalog: any;
    declare schema: any;
    declare frozen: any;
    declare statePaths: any;
    declare sampleState: any;
    declare problems: any;
;

    static override styles: CSSResultGroup = [PlatformElement.styles, css`
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
        .actions {
            display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px;
            margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--border-subtle);
        }
        .actions platform-button {
            display: flex; width: 100%; min-width: 0; max-width: 100%; overflow: hidden;
            --btn-padding: 6px 8px; --btn-font-size: 12px;
        }
        .empty { padding: 32px 8px; text-align: center; color: var(--text-tertiary); font-size: 12.5px; }
        .html-open {
            display: flex; align-items: center; gap: 12px; width: 100%; box-sizing: border-box;
            margin: 0 0 12px; padding: 12px 14px 12px 12px; border: 0; border-radius: 16px;
            background: var(--accent);
            color: var(--text-on-accent); text-align: left; cursor: pointer; font: inherit;
            box-shadow: var(--accent-glow);
        }
        .html-open:hover { filter: brightness(1.06); }
        .html-open:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
        .html-open-mark {
            width: 36px; height: 36px; flex: none; display: grid; place-items: center;
            border-radius: 11px; background: var(--glass-tint-strong);
        }
        .html-open-copy { display: grid; gap: 1px; min-width: 0; flex: 1; }
        .html-open-copy strong { font-size: 13.5px; font-weight: 750; letter-spacing: -.02em; }
        .html-open-copy span { font-size: 11px; opacity: .84; font-weight: 450; }
        .html-source { display: grid; gap: 6px; }
        .html-source .html-preview {
            margin: 0; max-height: 8.5em; overflow: hidden; padding: 8px 10px;
            border: 1px solid var(--border-subtle); border-radius: 10px;
            font-size: 11.5px; font-family: var(--font-mono); color: var(--text-secondary);
            white-space: pre-wrap; background: var(--glass-solid-subtle);
        }
        .hint { font-size: 11px; color: var(--text-tertiary); }
        .image-field { display: grid; gap: 8px; padding: 10px; border: 1px solid var(--border-subtle); border-radius: 10px; background: var(--glass-solid-subtle); }
        .image-row { display: flex; align-items: center; gap: 10px; }
        .image-preview {
            width: 56px; height: 56px; flex: 0 0 auto; padding: 0; border-radius: 50%;
            border: 1px solid var(--border-subtle); background: var(--bg-primary);
            display: grid; place-items: center; cursor: pointer; overflow: hidden; color: var(--text-tertiary);
        }
        .image-preview:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
        .image-preview img { width: 100%; height: 100%; object-fit: contain; }
        .image-actions { display: flex; flex-wrap: wrap; gap: 6px; }
        .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); border: 0; }
        .align-field { display: grid; gap: 6px; }
        .align-label { font-size: 12px; font-weight: 550; color: var(--text-secondary); }
        .align-picker {
            display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2px; padding: 3px;
            border-radius: 999px; border: 1px solid var(--border-subtle); background: var(--glass-solid-subtle);
        }
        .align-picker platform-button { width: 100%; min-width: 0; color: var(--text-secondary); }
        .align-picker platform-button[aria-pressed='true'] {
            background: var(--accent-subtle); color: var(--accent); border-radius: 999px;
            box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 24%, transparent);
        }
        .align-glyph { width: 16px; height: 14px; display: grid; gap: 2px; pointer-events: none; }
        .align-glyph i { display: block; background: currentColor; border-radius: 1px; }
        .align-glyph[data-axis='align'] { align-content: center; }
        .align-glyph[data-axis='align'] i { height: 2px; }
        .align-glyph[data-axis='align'] i:nth-child(1) { width: 100%; }
        .align-glyph[data-axis='align'] i:nth-child(2) { width: 62%; }
        .align-glyph[data-axis='align'] i:nth-child(3) { width: 80%; }
        .align-glyph[data-axis='align'][data-value='start'] i { justify-self: start; }
        .align-glyph[data-axis='align'][data-value='center'] i { justify-self: center; }
        .align-glyph[data-axis='align'][data-value='end'] i { justify-self: end; }
        .align-glyph[data-axis='valign'] { display: flex; justify-content: center; gap: 2px; width: 16px; height: 16px; }
        .align-glyph[data-axis='valign'] i { width: 3px; }
        .align-glyph[data-axis='valign'] i:nth-child(1) { height: 16px; }
        .align-glyph[data-axis='valign'] i:nth-child(2) { height: 10px; }
        .align-glyph[data-axis='valign'] i:nth-child(3) { height: 13px; }
        .align-glyph[data-axis='valign'][data-value='start'] { align-items: start; }
        .align-glyph[data-axis='valign'][data-value='center'] { align-items: center; }
        .align-glyph[data-axis='valign'][data-value='end'] { align-items: end; }
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

    _change(property: any, value: unknown, blockId = (this.block.block_id as any)) {
        this.emit('property-change', { blockId, property, value });
    }

    _pageChange(property: any, value: unknown) {
        this.emit('page-property-change', { property, value });
    }

    _label(name: string) {
        return this.t(`interface_editor.prop_${name}`);
    }

    _pathSuggestions() {
        return (this.statePaths.filter as any)((entry: any) => !entry.protected).map((entry: any) => entry.path);
    }

    _statePreview() {
        return this.sampleState;
    }

    _problemsFor(property: any) {
        return (this.problems.filter as any)((problem: any) => problem.property === property).map((problem: any) => html`<div class="problem" data-severity=${problem.severity}>
            <platform-icon name=${problem.severity === 'error' ? 'notification-error' : 'alert-triangle'} size="12"></platform-icon>${this.t(`interface_editor.problem_${problem.code}`, problem.params)}
        </div>`);
    }

    // --- Редакторы по виду ----------------------------------------------------------------------

    /** Однострочный шаблон — CodeMirror с автодополнением ``{path}``; многострочный (markdown, code) — textarea. */
    _template(name: string, value: unknown) {
        const text = typeof value === 'string' ? value : '';
        if (name === 'markdown' || name === 'code') {
            return html`<platform-field mode="edit" type="text" .label=${this._label(name)} .value=${text} .placeholder=${this.t('interface_editor.template_placeholder')}
                @change=${(event: CustomEvent) => this._change(name, event.detail.value)}></platform-field>`;
        }
        return html`<platform-variable-input syntax="brace" .label=${this._label(name)} .value=${text}
            .statePreview=${this._statePreview()} .statePaths=${this._pathSuggestions()} .placeholder=${this.t('interface_editor.template_placeholder')}
            @change=${(event: CustomEvent) => this._change(name, event.detail.value)}></platform-variable-input>`;
    }

    _statePath(name: string, value: unknown, required: any, hint: any) {
        const text = typeof value === 'string' ? value : '';
        return html`<platform-field mode="edit" type="string" .label=${this._label(name)} .value=${text} .suggestions=${this._pathSuggestions()}
            .hint=${hint ? this.t('interface_editor.field_hint', { path: text !== '' && !isFrozenPath(text, this.frozen) ? text : 'email' }) : ''} .placeholder=${'email'}
            @change=${(event: CustomEvent) => this._change(name, event.detail.value === '' && !required ? null : event.detail.value)}></platform-field>`;
    }

    _action(name: string, value: unknown, required: any) {
        const enabled = value !== null && value !== undefined;
        const action = enabled ? objectValue(value) : null;
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label(name)}</span>
                ${required ? nothing : html`<platform-field mode="edit" type="boolean" pill-embed .value=${enabled} @change=${(event: CustomEvent) => this._change(name, event.detail.value ? { name: 'submit', payload: {} } : null)}></platform-field>`}
            </div>
            ${action !== null ? html`
                <platform-field mode="edit" type="string" .label=${this.t('interface_editor.action_name')} .value=${action.name} .placeholder=${'submit'} .hint=${this.t('interface_editor.action_name_hint')}
                    @change=${(event: CustomEvent) => this._change(name, { ...action, name: event.detail.value })}></platform-field>
                <platform-field mode="edit" type="object" .label=${this.t('interface_editor.action_payload')} .value=${action.payload}
                    @change=${(event: CustomEvent) => this._change(name, { ...action, payload: event.detail.value })}></platform-field>
            ` : nothing}
        </div>`;
    }

    _clickKind() {
        if (typeof (this.block.page_id as any) === 'string' && (this.block.page_id as any) !== '') return 'page';
        if (typeof (this.block.url as any) === 'string' && (this.block.url as any) !== '') return 'url';
        return 'action';
    }

    _pageOptions() {
        const pages = documentPages(this.document);
        const options = pages.map((page: any) => ({
            value: page.page_id,
            label: page.title !== '' ? page.title : page.page_id,
        }));
        const current = (this.block.page_id as any);
        if (typeof current === 'string' && current !== '' && !options.some((item: any) => item.value === current)) {
            options.push({ value: current, label: current });
        }
        return options;
    }

    _defaultPageId() {
        const current = isPlainRecord(this.page) ? this.page.page_id : undefined;
        const other = documentPages(this.document).find((page) => isPlainRecord(page) && page.page_id !== current);
        if (isPlainRecord(other) && other.page_id !== undefined && other.page_id !== null) {
            return missingAsEmpty(other.page_id);
        }
        return missingAsEmpty(current);
    }

    _setClickKind(kind: string) {
        if (kind === 'page') {
            this._change('click_target', { action: null, page_id: (this.block.page_id as any) || this._defaultPageId(), url: '' });
            return;
        }
        if (kind === 'url') {
            this._change('click_target', { action: null, page_id: null, url: (this.block.url as any) || 'https://' });
            return;
        }
        this._change('click_target', { action: (this.block.action as any) ?? { name: 'submit', payload: {} }, page_id: null, url: '' });
    }

    _clickTarget() {
        const isButton = (this.block.type as any) === 'button';
        const kind = this._clickKind();
        const kinds = (isButton ? ['action', 'page', 'url'] : ['page', 'url']).map((value) => ({
            value,
            label: this.t(`interface_editor.click_${value}`),
        }));
        const pages = this._pageOptions();
        return html`<div class="sub" data-click-target=${kind}>
            <platform-field mode="edit" type="enum" .label=${this.t('interface_editor.click_target')}
                .value=${kinds.some((item: any) => item.value === kind) ? kind : clickKindValue(kinds)}
                .config=${{ values: kinds }}
                @change=${(event: CustomEvent) => this._setClickKind(event.detail.value)}></platform-field>
            ${kind === 'action' ? html`
                <platform-field mode="edit" type="string" .label=${this.t('interface_editor.action_name')} .value=${missingAsEmpty(actionField(this.block.action, 'name'))} .placeholder=${'submit'} .hint=${this.t('interface_editor.action_name_hint')}
                    @change=${(event: CustomEvent) => {
                        const payload = actionField(this.block.action, 'payload');
                        this._change('click_target', { action: { name: event.detail.value, payload: payload === undefined || payload === null ? {} : payload }, page_id: null, url: '' });
                    }}></platform-field>
                <platform-field mode="edit" type="object" .label=${this.t('interface_editor.action_payload')} .value=${(() => {
                    const payload = actionField(this.block.action, 'payload');
                    return payload === undefined || payload === null ? {} : payload;
                })()}
                    @change=${(event: CustomEvent) => this._change('click_target', { action: { name: (this.block.action as any)?.name ?? 'submit', payload: event.detail.value }, page_id: null, url: '' })}></platform-field>
            ` : nothing}
            ${kind === 'page' ? html`
                <platform-field mode="edit" type="enum" .label=${this._label('page_id')} .value=${missingAsEmpty(this.block.page_id)}
                    .config=${{ values: pages }} .hint=${pages.length < 2 ? this.t('interface_editor.click_page_add') : this.t('interface_editor.click_page_hint')}
                    @change=${(event: CustomEvent) => this._change('click_target', { action: null, page_id: event.detail.value, url: '' })}></platform-field>
            ` : nothing}
            ${kind === 'url' ? html`
                <platform-variable-input syntax="brace" .label=${this._label('url')} .value=${missingAsEmpty(this.block.url)}
                    .statePreview=${this._statePreview()} .statePaths=${this._pathSuggestions()} .placeholder=${'https://'}
                    @change=${(event: CustomEvent) => this._change('click_target', { action: null, page_id: null, url: event.detail.value })}></platform-variable-input>
            ` : nothing}
            ${this._problemsFor('action')}${this._problemsFor('page_id')}${this._problemsFor('url')}
        </div>`;
    }

    _condition(value: unknown) {
        const enabled = value !== null && value !== undefined;
        const condition = enabled ? objectValue(value) : null;
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label('visible_when')}</span>
                <platform-field mode="edit" type="boolean" pill-embed .value=${enabled} @change=${(event: CustomEvent) => this._change('visible_when', event.detail.value ? { path: 'status' } : null)}></platform-field>
            </div>
            ${condition !== null ? html`
                <platform-field mode="edit" type="string" .label=${this.t('interface_editor.condition_path')} .value=${condition.path} .suggestions=${this._pathSuggestions()}
                    @change=${(event: CustomEvent) => this._change('visible_when', { ...condition, path: event.detail.value })}></platform-field>
                <platform-field mode="edit" type="string" .label=${this.t('interface_editor.condition_equals')} .hint=${this.t('interface_editor.condition_equals_hint')}
                    .value=${conditionEqualsText(condition)}
                    @change=${(event: CustomEvent) => { const next: Record<string, unknown> = { path: condition.path }; const parsed = parseConditionValue(event.detail.value); if (event.detail.value.trim() !== '') next.equals = parsed; this._change('visible_when', next); }}></platform-field>
            ` : nothing}
        </div>`;
    }

    _height(name: string, value: unknown) {
        const auto = value === 'auto';
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label(name)}</span>
                <platform-field mode="edit" type="boolean" pill-embed .label=${this.t('interface_editor.height_auto')} .value=${auto} @change=${(event: CustomEvent) => this._change(name, event.detail.value ? 'auto' : 320)}></platform-field>
            </div>
            ${auto ? nothing : html`<platform-field mode="edit" type="integer" .value=${value} @change=${(event: CustomEvent) => this._change(name, event.detail.value)}></platform-field>`}
        </div>`;
    }

    _pairs(name: string, value: unknown, keys: any, labels: any) {
        const items = Array.isArray(value) ? value : [];
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label(name)}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.add_item')} @click=${() => this._change(name, [...items, { [keys[0]]: `${keys[0]}_${items.length + 1}`, [keys[1]]: '' }])}><platform-icon name="plus" size="14"></platform-icon></platform-button>
            </div>
            ${items.map((item, index) => html`<div class="row">
                <platform-field mode="edit" type="string" pill-embed .label=${labels[0]} .value=${item[keys[0]]} @change=${(event: CustomEvent) => this._change(name, items.map((entry, position) => (position === index ? { ...entry, [keys[0]]: event.detail.value } : entry)))}></platform-field>
                <platform-field mode="edit" type="string" pill-embed .label=${labels[1]} .value=${item[keys[1]]} @change=${(event: CustomEvent) => this._change(name, items.map((entry, position) => (position === index ? { ...entry, [keys[1]]: event.detail.value } : entry)))}></platform-field>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.remove_item')} @click=${() => this._change(name, items.filter((_entry, position) => position !== index))}><platform-icon name="close" size="14"></platform-icon></platform-button>
            </div>`)}
        </div>`;
    }

    _columns(value: unknown) {
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label('columns')}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.add_item')} ?disabled=${(value as any).length >= 4} @click=${() => this._change('columns', [...(value as any[]), { width: 1, blocks: [] }])}><platform-icon name="plus" size="14"></platform-icon></platform-button>
            </div>
            ${(value as any).map((column: any, index: number) => html`<div class="row">
                <platform-field mode="edit" type="integer" pill-embed .label=${this.t('interface_editor.column_width', { index: index + 1 })} .value=${column.width}
                    @change=${(event: CustomEvent) => this._change('columns', (value as any).map((entry: any, position: any) => (position === index ? { ...entry, width: event.detail.value } : entry)))}></platform-field>
                <span class="hint">${this.t('interface_editor.column_blocks', { count: column.blocks.length })}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.remove_item')} ?disabled=${(value as any).length <= 1 || column.blocks.length > 0} @click=${() => this._change('columns', (value as any).filter((_entry: any, position: any) => position !== index))}><platform-icon name="close" size="14"></platform-icon></platform-button>
            </div>`)}
        </div>`;
    }

    _tabs(value: unknown) {
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label('tabs')}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.add_item')} @click=${() => this._change('tabs', [...(value as any[]), { title: this.t('interface_editor.default_tab'), blocks: [] }])}><platform-icon name="plus" size="14"></platform-icon></platform-button>
            </div>
            ${(value as any).map((tab: any, index: number) => html`<div class="row">
                <platform-variable-input syntax="brace" .label=${this.t('interface_editor.tab_title', { index: index + 1 })} .value=${tab.title} .statePreview=${this._statePreview()} .statePaths=${this._pathSuggestions()}
                    @change=${(event: CustomEvent) => this._change('tabs', (value as any).map((entry: any, position: any) => (position === index ? { ...entry, title: event.detail.value } : entry)))}></platform-variable-input>
                <span class="hint">${this.t('interface_editor.column_blocks', { count: tab.blocks.length })}</span>
                <platform-button ghost density="compact" icon-only aria-label=${this.t('interface_editor.remove_item')} ?disabled=${(value as any).length <= 1 || tab.blocks.length > 0} @click=${() => this._change('tabs', (value as any).filter((_entry: any, position: any) => position !== index))}><platform-icon name="close" size="14"></platform-icon></platform-button>
            </div>`)}
        </div>`;
    }

    _conversationSettings(value: unknown) {
        const definition = (this.schema.$defs as any)[CONVERSATION_DEF];
        const settings = objectValue(value);
        return html`<div class="sub">
            <div class="sub-title"><span>${this._label('settings')}</span></div>
            ${Object.entries(definition.properties).map(([name, propertySchema]) => {
                const label = this.t(`interface_editor.conversation_${name}`);
                const current = settings[name];
                const set = (next: any) => this._change('settings', { ...settings, [name]: next });
                if ((propertySchema as any).type === 'boolean') return html`<platform-field mode="edit" type="boolean" pill-embed .label=${label} .value=${current} @change=${(event: CustomEvent) => set(event.detail.value)}></platform-field>`;
                if (Array.isArray((propertySchema as any).enum)) return html`<platform-field mode="edit" type="enum" pill-embed .label=${label} .value=${current} .config=${{ values: (propertySchema as any).enum.map((option: any) => ({ value: option, label: this.t(`interface_editor.enum_${option}`) })) }} @change=${(event: CustomEvent) => set(event.detail.value)}></platform-field>`;
                if ((propertySchema as any).type === 'array') return html`<platform-field mode="edit" type="array" pill-embed .label=${label} .value=${current} .config=${{ preserve_case: true }} @change=${(event: CustomEvent) => set(event.detail.value)}></platform-field>`;
                return html`<platform-variable-input syntax="brace" .label=${label} .value=${current} .statePreview=${this._statePreview()} .statePaths=${this._pathSuggestions()} @change=${(event: CustomEvent) => set(event.detail.value)}></platform-variable-input>`;
            })}
        </div>`;
    }

    _pickImage() {
        const input = this.renderRoot.querySelector('[data-image-input]');
        if (input instanceof HTMLInputElement) input.click();
    }

    _onImagePreviewKey(event: KeyboardEvent) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        this._pickImage();
    }

    _onImageFile(name: string, event: Event) {
        const input = event.currentTarget;
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('flows-interface-properties-panel: image input required');
        }
        const files = input.files;
        const file = files === null ? undefined : files[0];
        input.value = '';
        if (!file) return;
        if (typeof file.type !== 'string' || !file.type.startsWith('image/')) {
            this.toast('interface_editor.toast_image_type', { type: 'error' });
            return;
        }
        this.emit('image-upload', { blockId: (this.block.block_id as any), property: name, file });
    }

    _imageUrl(name: string, value: unknown) {
        const url = typeof value === 'string' ? value.trim() : '';
        return html`<div class="image-field">
            <div class="sub-title"><span>${this._label(name)}</span></div>
            <div class="image-row">
                <article class="image-preview" role="button" tabindex="0" aria-label=${this.t('interface_editor.image_upload')}
                    @click=${() => this._pickImage()} @keydown=${(event: KeyboardEvent) => this._onImagePreviewKey(event)}>
                    ${url !== '' ? html`<img src=${url} alt="">` : html`<platform-icon name="image" size="22"></platform-icon>`}
                </article>
                <div class="image-actions">
                    <input type="file" accept="image/*" class="visually-hidden" data-image-input @change=${(event: KeyboardEvent) => this._onImageFile(name, event)}>
                    <platform-button secondary density="compact" @click=${() => this._pickImage()}>
                        <platform-icon name="image" size="13"></platform-icon>${this.t('interface_editor.image_upload')}
                    </platform-button>
                    ${url !== '' ? html`<platform-button ghost density="compact" @click=${() => this._change(name, '')}>${this.t('interface_editor.image_clear')}</platform-button>` : nothing}
                </div>
            </div>
            <div class="hint">${this.t('interface_editor.image_hint')}</div>
        </div>`;
    }

    _onHtmlOpenKey(event: KeyboardEvent) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        this._blockAction('edit_html');
    }

    _htmlOpenHero() {
        return html`<article class="html-open" role="button" tabindex="0"
            aria-label=${this.t('interface_editor.html_open_editor')}
            @click=${() => this._blockAction('edit_html')}
            @keydown=${(event: KeyboardEvent) => this._onHtmlOpenKey(event)}>
            <span class="html-open-mark"><platform-icon name="code" size="18"></platform-icon></span>
            <span class="html-open-copy">
                <strong>${this.t('interface_editor.html_open_editor')}</strong>
                <span>${this.t('interface_editor.html_open_editor_hint')}</span>
            </span>
            <platform-icon name="fullscreen" size="16"></platform-icon>
        </article>`;
    }

    _htmlSource(value: unknown) {
        const preview = missingAsEmpty(value).split('\n').slice(0, 8).join('\n');
        return html`<div class="html-source">
            <div class="sub-title"><span>${this._label('source')}</span></div>
            <pre class="html-preview">${preview}</pre>
            <div class="hint">${this.t('interface_editor.html_hint')}</div>
        </div>`;
    }

    _alignPicker(property: any) {
        const axis = property.name;
        const current = (this.block as any)[axis] === 'center' || (this.block as any)[axis] === 'end' ? (this.block as any)[axis] : 'start';
        const items = ['start', 'center', 'end'].map((value) => ({
            value,
            title: this.t(`interface_editor.${axis}_${value}`),
        }));
        return html`<div class="align-field" data-align-axis=${axis}>
            <div class="align-label">${this._label(axis)}</div>
            <div class="align-picker" role="group" aria-label=${this._label(axis)}>
                ${items.map((item) => html`<platform-button ghost density="compact" data-value=${item.value}
                    aria-pressed=${current === item.value ? 'true' : 'false'}
                    aria-label=${item.title} title=${item.title}
                    @click=${() => this._change(axis, item.value)}>
                    <span class="align-glyph" data-axis=${axis} data-value=${item.value}><i></i><i></i><i></i></span>
                </platform-button>`)}
            </div>
            ${axis === 'valign' ? html`<div class="hint">${this.t('interface_editor.prop_valign_hint')}</div>` : nothing}
        </div>`;
    }

    _editor(property: any) {
        const { name, kind } = property;
        const value = (this.block as any)[name];
        const isInput = INPUT_BLOCK_TYPES.has((this.block.type as any));
        if (name === 'align' || name === 'valign') return this._alignPicker(property);
        if (((this.block.type as any) === 'button' && name === 'action') || ((this.block.type as any) === 'link' && name === 'page_id')) return this._clickTarget();
        if (((this.block.type as any) === 'button' && (name === 'page_id' || name === 'url')) || ((this.block.type as any) === 'link' && name === 'url')) return '';
        switch (kind) {
            case 'const': case 'blocks': return '';
            case 'template': return this._template(name, value);
            case 'image_url': return this._imageUrl(name, value);
            case 'string': return (this.block.type as any) === 'html' && name === 'source' ? this._htmlSource(value)
                : html`<platform-field mode="edit" type="string" .label=${this._label(name)} .value=${typeof value === 'string' ? value : ''} @change=${(event: CustomEvent) => this._change(name, event.detail.value)}></platform-field>`;
            case 'state_path': return this._statePath(name, value, property.required, isInput && name === 'field');
            case 'height': return this._height(name, value);
            case 'action': return this._action(name, value, property.required);
            case 'condition': return this._condition(value);
            case 'conversation_settings': return this._conversationSettings(value);
            case 'enum': return html`<platform-field mode="edit" type="enum" .label=${this._label(name)} .value=${String(value)}
                .config=${{ values: property.enum.map((option: any) => ({ value: String(option), label: this.t(`interface_editor.enum_${option}`) })) }}
                @change=${(event: CustomEvent) => this._change(name, property.enum.find((option: any) => String(option) === event.detail.value))}></platform-field>`;
            case 'boolean': return html`<platform-field mode="edit" type="boolean" .label=${this._label(name)} .value=${value === true} @change=${(event: CustomEvent) => this._change(name, event.detail.value)}></platform-field>`;
            case 'integer': case 'number': return html`<platform-field mode="edit" type=${kind} .label=${this._label(name)} .value=${value} @change=${(event: CustomEvent) => this._change(name, event.detail.value)}></platform-field>`;
            case 'json': return html`<platform-field mode="edit" type="object" .label=${this._label(name)} .value=${value} @change=${(event: CustomEvent) => this._change(name, event.detail.value)}></platform-field>`;
            case 'columns': return this._columns(value);
            case 'tabs': return this._tabs(value);
            case 'options': return this._pairs(name, value, ['value', 'label'], [this.t('interface_editor.option_value'), this.t('interface_editor.option_label')]);
            case 'table_columns': return this._pairs(name, value, ['key', 'label'], [this.t('interface_editor.column_key'), this.t('interface_editor.option_label')]);
            case 'state_path_list': case 'template_list': case 'string_list': return html`<platform-field mode="edit" type="array" .label=${this._label(name)} .value=${Array.isArray(value) ? value : []} .config=${{ preserve_case: true }} .placeholder=${kind === 'state_path_list' ? 'email' : ''} @change=${(event: CustomEvent) => this._change(name, event.detail.value)}></platform-field>`;
            case 'select_default': return html`<platform-field mode="edit" type=${(this.block.multiple as any) === true ? 'array' : 'string'} .label=${this._label(name)} .value=${value ?? ((this.block.multiple as any) === true ? [] : '')} .config=${{ preserve_case: true }} @change=${(event: CustomEvent) => this._change(name, event.detail.value === '' ? null : event.detail.value)}></platform-field>`;
            default: throw new Error(`interface editor: no editor for property kind ${kind}`);
        }
    }

    _renderPage() {
        const shown = (this.page.show_title as any) !== false;
        return html`
            <div class="head"><platform-icon name="layers" size="16"></platform-icon><span class="type">${this.t('interface_editor.page_properties')}</span></div>
            <div class="fields">
                <platform-variable-input syntax="brace" .label=${this.t('interface_editor.page_title')} .value=${missingAsEmpty(this.page.title)}
                    .statePreview=${this._statePreview()} .statePaths=${this._pathSuggestions()} .placeholder=${this.t('interface_editor.template_placeholder')}
                    @change=${(event: CustomEvent) => this._pageChange('title', event.detail.value)}></platform-variable-input>
                <platform-field mode="edit" type="boolean" .label=${this.t('interface_editor.page_show_title')} .value=${shown}
                    @change=${(event: CustomEvent) => this._pageChange('show_title', event.detail.value)}></platform-field>
                <div class="hint">${this.t('interface_editor.page_show_title_hint')}</div>
            </div>
        `;
    }

    _renderContract() {
        const inputs = walkPage(this.page).filter(({ block }) => INPUT_BLOCK_TYPES.has(block.type));
        const actions = [...new Set(walkPage(this.page).flatMap(({ block }) => [block.action, block.row_action].filter((action) => action && typeof action.name === 'string').map((action) => action.name)))];
        if (inputs.length === 0 && actions.length === 0) return '';
        return html`<div class="contract">
            <div class="title">${this.t('interface_editor.contract_title')}</div>
            ${inputs.length > 0 ? html`<div>${this.t('interface_editor.contract_fields')}: ${inputs.map(({ block }, index) => html`${index > 0 ? ', ' : ''}<code>${block.field}</code>`)}</div>` : nothing}
            ${actions.length > 0 ? html`<div>${this.t('interface_editor.contract_actions')}: ${actions.map((name, index) => html`${index > 0 ? ', ' : ''}<code>${name}</code>`)}</div>` : nothing}
            <div class="hint">${this.t('interface_editor.contract_hint')}</div>
        </div>`;
    }

    _blockAction(action: any) {
        this.emit('block-action', { blockId: (this.block.block_id as any), action });
    }

    _renderBlockActions() {
        const items = [
            { action: 'duplicate', icon: 'copy', caption: this.t('interface_editor.block_duplicate'), label: this.t('interface_editor.block_duplicate') },
            { action: 'wrap', icon: 'square', caption: this.t('interface_editor.block_wrap'), label: this.t('interface_editor.block_wrap_section') },
            { action: 'remove', icon: 'trash', caption: this.t('interface_editor.block_remove'), label: this.t('interface_editor.block_remove'), danger: true },
        ];
        return html`<div class="actions" role="group" aria-label=${this.t('interface_editor.block_menu')}>
            ${items.map((item) => html`<platform-button ghost density="compact" block data-action=${item.action} ?danger=${item.danger === true}
                title=${item.label} aria-label=${item.label} @click=${() => this._blockAction(item.action)}>
                <platform-icon name=${item.icon} size="15"></platform-icon><span>${item.caption}</span>
            </platform-button>`)}
        </div>`;
    }

    override render(): TemplateResult {
        if (this.page === null) return html`<div class="empty">${this.t('interface_editor.properties_empty')}</div>`;
        if (this.block === null) return html`${this._renderPage()}${this._renderContract()}`;
        if (this.schema === null) return html`<div class="empty">${this.t('interface_editor.properties_empty')}</div>`;
        const blockType = this.block.type;
        const entry = catalogEntry(this.catalog, blockType);
        return html`
            <div class="head"><platform-icon name=${entry.icon} size="16"></platform-icon><span class="type">${this.t(`interface_editor.block_${blockType}`)}</span></div>
            ${blockType === 'html' ? this._htmlOpenHero() : nothing}
            <div class="fields">
                <platform-field mode="edit" type="string" .label=${this._label('block_id')} .value=${this.block.block_id} .hint=${this.t('interface_editor.block_id_hint')} @change=${(event: CustomEvent) => this._change('block_id', event.detail.value)}></platform-field>
                ${this._problemsFor('block_id')}
                ${entry.properties.filter((property: any) => !HIDDEN_PROPERTIES.has(property.name) && property.name !== 'block_id').map((property: any) => html`${this._editor(property)}${this._problemsFor(property.name)}`)}
            </div>
            ${this._renderBlockActions()}
            ${this._renderContract()}
        `;
    }
}

if (!customElements.get('flows-interface-properties-panel')) customElements.define('flows-interface-properties-panel', FlowsInterfacePropertiesPanel);
