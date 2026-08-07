/**
 * Pages panel: select, create, rename (double click), duplicate and delete.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsInterfacePagesPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        document: { attribute: false },
        _renamingId: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: block; }
        .head {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 6px 8px;
        }
        .title {
            font-size: 11px;
            color: var(--text-tertiary);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
        }
        .add {
            color: var(--accent);
            cursor: pointer;
            width: 22px;
            height: 22px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 6px;
        }
        .add:hover { background: var(--glass-solid-subtle); }
        .page {
            width: 100%;
            display: flex;
            align-items: center;
            gap: 6px;
            color: inherit;
            padding: 6px 8px;
            border-radius: var(--radius-md);
            cursor: pointer;
            font-size: 12px;
            min-width: 0;
            box-sizing: border-box;
        }
        .page[data-active="true"] {
            background: var(--accent-subtle);
            color: var(--accent);
            font-weight: 650;
        }
        .page:hover { background: var(--glass-solid-subtle); }
        .page .name {
            flex: 1;
            min-width: 0;
            text-align: left;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .page .route { color: var(--text-tertiary); font-size: 11px; flex-shrink: 0; }
        .tool {
            width: 20px;
            height: 20px;
            display: none;
            align-items: center;
            justify-content: center;
            border-radius: 5px;
            color: var(--text-tertiary);
            cursor: pointer;
            flex-shrink: 0;
        }
        .page:hover .tool { display: inline-flex; }
        .tool:hover { color: var(--text-primary); background: var(--glass-solid-medium); }
        .tool:focus-visible, .add:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
        .rename-input {
            flex: 1;
            min-width: 0;
            height: 22px;
            border: 1px solid var(--accent);
            border-radius: 6px;
            background: var(--bg-elevated);
            color: inherit;
            font: inherit;
            font-size: 12px;
            padding: 0 4px;
        }
    `];

    constructor() {
        super();
        this.document = null;
        this._renamingId = '';
    }

    _tool({ labelKey, icon, action }) {
        const label = this.t(labelKey);
        return html`<span
            class="tool"
            role="button"
            tabindex="0"
            title=${label}
            aria-label=${label}
            @click=${(event) => { event.stopPropagation(); action(); }}
            @keydown=${(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    event.stopPropagation();
                    action();
                }
            }}
        ><platform-icon name=${icon} size="12"></platform-icon></span>`;
    }

    _commitRename(page, raw) {
        this._renamingId = '';
        const title = String(raw || '').trim();
        if (!title || title === page.title?.default) return;
        this.emit('page-rename', { pageId: page.page_id, title });
    }

    render() {
        const doc = this.document || {};
        const pages = Object.values(doc.pages || {});
        return html`
            <div class="head">
                <span class="title">${this.t('interface_editor.pages_title')}</span>
                <span
                    class="add"
                    role="button"
                    tabindex="0"
                    title=${this.t('interface_editor.page_add')}
                    aria-label=${this.t('interface_editor.page_add')}
                    @click=${() => this.emit('page-add', {})}
                    @keydown=${(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            this.emit('page-add', {});
                        }
                    }}
                ><platform-icon name="plus" size="14"></platform-icon></span>
            </div>
            ${pages.map((page) => html`
                <div
                    class="page"
                    role="button"
                    tabindex="0"
                    data-active=${page.page_id === doc.active_page_id ? 'true' : 'false'}
                    @click=${() => this.emit('page-select', { pageId: page.page_id })}
                    @keydown=${(event) => {
                        if (event.key === 'Enter') this.emit('page-select', { pageId: page.page_id });
                    }}
                >
                    ${this._renamingId === page.page_id
                        ? html`<input
                            class="rename-input"
                            data-canon="inline-edit"
                            .value=${page.title?.default || page.page_id}
                            @click=${(event) => event.stopPropagation()}
                            @keydown=${(event) => {
                                if (event.key === 'Enter') this._commitRename(page, event.target.value);
                                if (event.key === 'Escape') this._renamingId = '';
                            }}
                            @blur=${(event) => this._commitRename(page, event.target.value)}
                        >`
                        : html`<span
                            class="name"
                            @dblclick=${(event) => {
                                event.stopPropagation();
                                this._renamingId = page.page_id;
                                this.updateComplete.then(() => {
                                    this.renderRoot.querySelector('.rename-input')?.focus();
                                });
                            }}
                        >${page.title?.default || page.page_id}</span>`}
                    <span class="route">${page.route || ''}</span>
                    ${this._tool({
                        labelKey: 'interface_editor.page_duplicate',
                        icon: 'copy',
                        action: () => this.emit('page-duplicate', { pageId: page.page_id }),
                    })}
                    ${pages.length > 1 ? this._tool({
                        labelKey: 'interface_editor.page_delete',
                        icon: 'trash',
                        action: () => this.emit('page-delete', { pageId: page.page_id }),
                    }) : nothing}
                </div>
            `)}
        `;
    }
}

if (!customElements.get('flows-interface-pages-panel')) {
    customElements.define('flows-interface-pages-panel', FlowsInterfacePagesPanel);
}
