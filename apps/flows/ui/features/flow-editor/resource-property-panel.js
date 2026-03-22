/**
 * ResourcePropertyPanel - панель свойств выбранного ресурса
 * Оркестратор для resource-editors компонентов
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '../../components/resources/index.js';

export class ResourcePropertyPanel extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                height: 100%;
            }
        `
    ];

    static properties = {
        resource: { type: Object },
        expanded: { type: Boolean },
        config: { type: Object },
    };

    constructor() {
        super();
        this.resource = null;
        this.expanded = false;
        this.config = null;
    }

    updated(changedProperties) {
        if (changedProperties.has('resource') && this.resource) {
            this._loadResourceConfig();
        }
    }

    _loadResourceConfig() {
        const { position, resourceId, color, name, ...config } = this.resource;
        this.config = config.config || {};
    }

    _onConfigChanged(e) {
        this.config = e.detail.config;
        this.emit('resource-updated', {
            resourceId: this.resource.resourceId,
            resourceConfig: this.config,
        });
    }

    _onResourceDeleted() {
        this.emit('resource-deleted', { resourceId: this.resource.resourceId });
    }

    _renderDefaultPanel() {
        return html`
            <div style="padding: var(--space-4); text-align: center; color: var(--text-tertiary);">
                Выберите ресурс для редактирования
            </div>
        `;
    }

    render() {
        if (!this.resource) {
            return this._renderDefaultPanel();
        }
        
        if (!this.config) {
            this._loadResourceConfig();
        }

        const resourceType = this.resource.type;
        
        switch (resourceType) {
            case 'code':
                return html`<code-resource-editor
                    .resourceConfig=${this.config}
                    .resourceId=${this.resource.resourceId}
                    .resourceType=${resourceType}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @resource-delete=${this._onResourceDeleted}
                ></code-resource-editor>`;
            case 'rag':
                return html`<rag-resource-editor
                    .resourceConfig=${this.config}
                    .resourceId=${this.resource.resourceId}
                    .resourceType=${resourceType}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @resource-delete=${this._onResourceDeleted}
                ></rag-resource-editor>`;
            case 'files':
                return html`<files-resource-editor
                    .resourceConfig=${this.config}
                    .resourceId=${this.resource.resourceId}
                    .resourceType=${resourceType}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @resource-delete=${this._onResourceDeleted}
                ></files-resource-editor>`;
            case 'prompt':
                return html`<prompt-resource-editor
                    .resourceConfig=${this.config}
                    .resourceId=${this.resource.resourceId}
                    .resourceType=${resourceType}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @resource-delete=${this._onResourceDeleted}
                ></prompt-resource-editor>`;
            case 'llm':
                return html`<llm-resource-editor
                    .resourceConfig=${this.config}
                    .resourceId=${this.resource.resourceId}
                    .resourceType=${resourceType}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @resource-delete=${this._onResourceDeleted}
                ></llm-resource-editor>`;
            case 'secret':
                return html`<secret-resource-editor
                    .resourceConfig=${this.config}
                    .resourceId=${this.resource.resourceId}
                    .resourceType=${resourceType}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @resource-delete=${this._onResourceDeleted}
                ></secret-resource-editor>`;
            case 'http':
                return html`<http-resource-editor
                    .resourceConfig=${this.config}
                    .resourceId=${this.resource.resourceId}
                    .resourceType=${resourceType}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @resource-delete=${this._onResourceDeleted}
                ></http-resource-editor>`;
            case 'cache':
                return html`<cache-resource-editor
                    .resourceConfig=${this.config}
                    .resourceId=${this.resource.resourceId}
                    .resourceType=${resourceType}
                    ?expanded=${this.expanded}
                    @config-change=${this._onConfigChanged}
                    @resource-delete=${this._onResourceDeleted}
                ></cache-resource-editor>`;
            default:
                return this._renderDefaultPanel();
        }
    }
}

customElements.define('resource-property-panel', ResourcePropertyPanel);
