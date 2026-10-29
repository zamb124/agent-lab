/**
 * Дерево JSON для инспектора результата ноды. Дети свёрнуты; корень сразу
 * показывает ключи первого уровня.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { jsonTreeChildPath, nodeRunValueKindLabel, classifyNodeRunValue } from '../_helpers/flows-node-run-result.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsJsonTree extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        value: { attribute: false },
        rootPath: { type: String, attribute: 'root-path' },
        selectedPath: { type: String, attribute: 'selected-path' },
        _expanded: { state: true },
    }
    declare value: unknown;
    declare rootPath: string;
    declare selectedPath: string;
    declare _expanded: Set<string>;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                font-family: var(--font-sans);
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .empty {
                margin: 0;
                padding: var(--space-4);
                color: var(--text-tertiary);
            }
            .row {
                display: flex;
                align-items: flex-start;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-sm);
                cursor: pointer;
                min-width: 0;
            }
            .row:hover {
                background: var(--glass-solid-subtle);
            }
            .row[data-selected='true'] {
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .chevron {
                flex-shrink: 0;
                width: 16px;
                height: 16px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
            }
            .chevron[data-leaf='true'] {
                visibility: hidden;
            }
            .key {
                font-family: var(--font-mono);
                font-weight: var(--font-semibold);
                min-width: 0;
                word-break: break-word;
            }
            .kind {
                flex-shrink: 0;
                margin-left: auto;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .children {
                padding-left: var(--space-4);
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.rootPath = '';
        this.selectedPath = '';
        this._expanded = new Set<string>();
    }

    /**
     * @param {KeyboardEvent} event
     * @param {() => void} handler
     */
    _onSelectableKeydown(event: KeyboardEvent, handler: () => void) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        event.preventDefault();
        handler.call(this);
    }

    /**
     * @param {unknown} value
     */
    _isExpandable(value: unknown) {
        if (value === null || typeof value !== 'object') {
            return false;
        }
        if (Array.isArray(value)) {
            return value.length > 0;
        }
        return Object.keys(value).length > 0;
    }

    /**
     * @param {string} path
     * @param {unknown} value
     */
    _select(path: string, value: unknown) {
        this.emit('select', { path, value });
        if (!this._isExpandable(value)) {
            return;
        }
        const next = new Set(this._expanded);
        if (next.has(path)) {
            next.delete(path);
        } else {
            next.add(path);
        }
        this._expanded = next;
    }

    /**
     * @param {string} label
     * @param {unknown} childValue
     * @param {string} path
     */
    _renderRow(label: string, childValue: unknown, path: string) {
        const expandable = this._isExpandable(childValue);
        const expanded = this._expanded.has(path);
        const classified = classifyNodeRunValue(childValue);
        const kindLabel = nodeRunValueKindLabel(classified, (key: string, params?: Record<string, string | number> | null) => this.t(key, params));
        const selected = this.selectedPath === path;
        return html`
            <article
                class="row"
                role="button"
                tabindex="0"
                data-path=${path}
                data-selected=${selected ? 'true' : 'false'}
                @click=${() => this._select(path, childValue)}
                @keydown=${(event: KeyboardEvent) => this._onSelectableKeydown(event, () => this._select(path, childValue))}
            >
                <span class="chevron" data-leaf=${expandable ? 'false' : 'true'}>
                    <platform-icon name=${expanded ? 'chevron-down' : 'chevron-right'} size="12"></platform-icon>
                </span>
                <span class="key">${label}</span>
                <span class="kind">${kindLabel}</span>
            </article>
            ${expandable && expanded ? html`<div class="children">${this._renderChildren(childValue, path)}</div>` : nothing}
        `;
    }

    /**
     * @param {unknown} value
     * @param {string} parentPath
     */
    _renderChildren(value: unknown, parentPath: string): TemplateResult[] {
        if (Array.isArray(value)) {
            const items: unknown[] = [];
            for (const item of value) items.push(item);
            return items.map((item, index) => this._renderRow(
                String(index),
                item,
                jsonTreeChildPath(parentPath, index, true),
            ));
        }
        if (!isPlainRecord(value)) {
            throw new Error('flows-json-tree: children require object or array');
        }
        return Object.keys(value).map((key) => this._renderRow(
            key,
            value[key],
            jsonTreeChildPath(parentPath, key, false),
        ));
    }

    override render(): TemplateResult {
        const value = this.value;
        if (value === null || typeof value !== 'object') {
            throw new Error('flows-json-tree: value must be an object or array');
        }
        const empty = Array.isArray(value) ? value.length === 0 : Object.keys(value).length === 0;
        if (empty) {
            return html`<p class="empty">${this.t('node_run_result_modal.empty_value')}</p>`;
        }
        const rootPath = typeof this.rootPath === 'string' ? this.rootPath : '';
        return html`${this._renderChildren(value, rootPath)}`;
    }
}

customElements.define('flows-json-tree', FlowsJsonTree);
