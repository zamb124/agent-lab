/**
 * Перемещение страницы: смена родителя и, при необходимости, пространства.
 *
 * Оба перемещения делаются одним окном, но разными операциями сервера:
 * внутри пространства меняется только родитель, а перенос между
 * пространствами затрагивает ещё и права с индексом поиска.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';

export class WikiMovePageModal extends PlatformModal {
    static modalKind = 'wiki.move_page';
    static i18nNamespace = 'wiki';

    static properties = {
        pageId: { type: String, attribute: 'page-id' },
        _namespace: { state: true },
        _parentPageId: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .form-grid {
                display: grid;
                gap: var(--space-4);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'sm';
        this.pageId = '';
        this._namespace = '';
        this._parentPageId = '';
        this._pages = this.useResource('wiki/pages');
        this._namespaces = this.useResource('wiki/namespaces');
        this._move = this.useOp('wiki/page_move');
        this._moveNamespace = this.useOp('wiki/page_move_namespace');
    }

    connectedCallback() {
        super.connectedCallback();
        const page = this._pages.byId[this.pageId];
        if (page) {
            this._namespace = page.namespace;
            this._parentPageId = page.parent_page_id === null ? '' : page.parent_page_id;
        }
    }

    _namespaceConfig() {
        return { values: this._namespaces.items.map((item) => ({ value: item.name, label: item.name })) };
    }

    /** Родителем не может быть ни сама страница, ни её потомок. */
    _parentConfig() {
        const values = [{ value: '', label: this.t('move.parent_root') }];
        const forbidden = this._descendantIds();
        for (const page of this._pages.items) {
            if (forbidden.has(page.wiki_page_id)) {
                continue;
            }
            values.push({
                value: page.wiki_page_id,
                label: page.title === '' ? this.t('page.untitled') : page.title,
            });
        }
        return { values };
    }

    _descendantIds() {
        const blocked = new Set([this.pageId]);
        let grew = true;
        while (grew) {
            grew = false;
            for (const page of this._pages.items) {
                if (page.parent_page_id !== null
                    && blocked.has(page.parent_page_id)
                    && !blocked.has(page.wiki_page_id)) {
                    blocked.add(page.wiki_page_id);
                    grew = true;
                }
            }
        }
        return blocked;
    }

    async _submit() {
        const page = this._pages.byId[this.pageId];
        const parentPageId = this._parentPageId === '' ? null : this._parentPageId;
        if (page && this._namespace !== page.namespace) {
            await this._moveNamespace.run({
                wiki_page_id: this.pageId,
                target_namespace: this._namespace,
                parent_page_id: parentPageId,
            });
        } else {
            await this._move.run({
                wiki_page_id: this.pageId,
                parent_page_id: parentPageId,
                position: 0,
            });
        }
        await this._pages.load();
        this.close();
    }

    renderHeader() {
        return this.t('move.title');
    }

    renderBody() {
        return html`
            <div class="form-grid">
                <platform-field
                    type="enum"
                    mode="edit"
                    label=${this.t('move.namespace_label')}
                    .value=${this._namespace}
                    .config=${this._namespaceConfig()}
                    @change=${(event) => { this._namespace = event.detail.value; }}
                ></platform-field>
                <platform-field
                    type="enum"
                    mode="edit"
                    label=${this.t('move.parent_label')}
                    .value=${this._parentPageId}
                    .config=${this._parentConfig()}
                    @change=${(event) => { this._parentPageId = event.detail.value; }}
                ></platform-field>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="primary" data-wiki-move-submit @click=${this._submit}>
                ${this.t('move.submit')}
            </platform-button>
        `;
    }
}

customElements.define('wiki-move-page-modal', WikiMovePageModal);
registerModalKind(WikiMovePageModal.modalKind, 'wiki-move-page-modal');
