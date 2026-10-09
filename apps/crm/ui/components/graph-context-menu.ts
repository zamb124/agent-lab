/**
 * graph-context-menu — контекстное меню для нод/рёбер графа.
 *
 * Композиционный child-компонент: шлёт DOM-событие `ctx-action`
 * с detail = { action, nodeId, edgeId } через `this.emit(...)`.
 * Родитель (graph-page) сам диспатчит bus-события по этим действиям.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
    TemplateResult,
} from 'lit';

export class CRMGraphContextMenu extends PlatformElement {
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        x: { type: Number },
        y: { type: Number },
        nodeId: { type: String, attribute: 'node-id' },
        edgeId: { type: String, attribute: 'edge-id' },
        visible: { type: Boolean, reflect: true },
    };
    declare x: number;
    declare y: number;
    declare nodeId: string;
    declare edgeId: string;
    declare visible: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                z-index: 20;
                display: none;
                min-width: 180px;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: 10px;
                backdrop-filter: blur(12px);
                padding: 4px;
                box-shadow: var(--glass-shadow-medium);
                pointer-events: auto;
            }

            :host([visible]) {
                display: block;
            }

            .ctx-item {
                display: flex;
                align-items: center;
                gap: 8px;
                width: 100%;
                padding: 7px 12px;
                border: none;
                border-radius: 7px;
                background: none;
                color: var(--text-primary);
                font-size: 13px;
                cursor: pointer;
                text-align: left;
            }

            .ctx-item:hover {
                background: var(--glass-solid-medium);
            }

            .separator {
                height: 1px;
                background: var(--glass-border-subtle);
                margin: 3px 8px;
            }
        `,
    ];

    constructor() {
        super();
        this.x = 0;
        this.y = 0;
        this.nodeId = '';
        this.edgeId = '';
        this.visible = false;
    }

    override updated(changed: PropertyValues<this>): void {
        if (changed.has('x') || changed.has('y')) {
            this.style.left = `${this.x}px`;
            this.style.top = `${this.y}px`;
        }
    }

    _onAction(action: string) {
        this.emit('ctx-action', {
            action,
            nodeId: this.nodeId,
            edgeId: this.edgeId,
        });
    }

    override render(): TemplateResult {
        if (!this.nodeId && !this.edgeId) {
            return html``;
        }

        if (this.nodeId) {
            return html`
                <button class="ctx-item" type="button" @click=${() => this._onAction('open-entity')}>
                    <platform-icon name="share" size="16"></platform-icon>
                    ${this.t('graph.context_open_entity')}
                </button>
                <button class="ctx-item" type="button" @click=${() => this._onAction('focus')}>
                    <platform-icon name="search" size="16"></platform-icon>
                    ${this.t('graph.zoom_in')}
                </button>
                <div class="separator"></div>
                <button class="ctx-item" type="button" @click=${() => this._onAction('path-from')}>
                    <platform-icon name="workflow" size="16"></platform-icon>
                    ${this.t('graph.context_path_from')}
                </button>
                <button class="ctx-item" type="button" @click=${() => this._onAction('graph-from')}>
                    <platform-icon name="expand" size="16"></platform-icon>
                    ${this.t('graph.context_graph_from')}
                </button>
            `;
        }

        return html`
            <button class="ctx-item" type="button" @click=${() => this._onAction('edge-info')}>
                <platform-icon name="info" size="16"></platform-icon>
                ${this.t('graph.context_edge_info')}
            </button>
        `;
    }
}

customElements.define('crm-graph-context-menu', CRMGraphContextMenu);
