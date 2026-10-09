/**
 * Перемещение страницы: смена родителя и, при необходимости, пространства.
 *
 * Оба перемещения делаются одним окном, но разными операциями сервера:
 * внутри пространства меняется только родитель, а перенос между
 * пространствами затрагивает ещё и права с индексом поиска.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { ResourceItem } from '@platform/lib/events/factories/resource-collection.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';

export class WikiMovePageModal extends PlatformModal {
    static modalKind = 'wiki.move_page';
    static i18nNamespace = 'wiki';

    declare pageId: string;
    declare _namespace: string;
    declare _parentPageId: string;
    private _pages: ResourceController;
    private _namespaces: ResourceController;
    private _move: OpController;
    private _moveNamespace: OpController;

    static override get properties() {
        return {
            ...PlatformModal.properties,
            pageId: { type: String, attribute: 'page-id' },
            _namespace: { state: true },
            _parentPageId: { state: true },
        };
    }

    static override styles = [
        PlatformModal.styles,
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

    override connectedCallback() {
        super.connectedCallback();
        const page = this._pages.byId[this.pageId];
        if (page) {
            this._namespace = String(page.namespace ?? '');
            this._parentPageId = page.parent_page_id === null ? '' : String(page.parent_page_id ?? '');
        }
    }

    private _namespaceConfig(): { values: { value: string; label: string }[] } {
        return { values: this._namespaces.items.map((item: ResourceItem) => ({ value: String(item.name ?? ''), label: String(item.name ?? '') })) };
    }

    /** Родителем не может быть ни сама страница, ни её потомок. */
    private _parentConfig(): { values: { value: string; label: unknown }[] } {
        const values: { value: string; label: unknown }[] = [{ value: '', label: this.t('move.parent_root') }];
        const forbidden = this._descendantIds();
        for (const page of this._pages.items) {
            const id = String(page.wiki_page_id ?? '');
            if (forbidden.has(id)) {
                continue;
            }
            values.push({
                value: id,
                label: page.title === '' ? this.t('page.untitled') : page.title,
            });
        }
        return { values };
    }

    private _descendantIds(): Set<string> {
        const blocked = new Set<string>([this.pageId]);
        let grew = true;
        while (grew) {
            grew = false;
            for (const page of this._pages.items) {
                const id = String(page.wiki_page_id ?? '');
                const parent = String(page.parent_page_id ?? '');
                if (page.parent_page_id !== null
                    && blocked.has(parent)
                    && !blocked.has(id)) {
                    blocked.add(id);
                    grew = true;
                }
            }
        }
        return blocked;
    }

    private async _submit(): Promise<void> {
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
        void this.close();
    }

    override renderHeader() {
        return this.t('move.title');
    }

    override renderBody() {
        return html`
            <div class="form-grid">
                <platform-field
                    type="enum"
                    mode="edit"
                    label=${this.t('move.namespace_label')}
                    .value=${this._namespace}
                    .config=${this._namespaceConfig()}
                    @change=${(event: CustomEvent<{ value?: unknown }>) => { this._namespace = String(event.detail.value ?? ''); }}
                ></platform-field>
                <platform-field
                    type="enum"
                    mode="edit"
                    label=${this.t('move.parent_label')}
                    .value=${this._parentPageId}
                    .config=${this._parentConfig()}
                    @change=${(event: CustomEvent<{ value?: unknown }>) => { this._parentPageId = String(event.detail.value ?? ''); }}
                ></platform-field>
            </div>
        `;
    }

    override renderFooter() {
        return html`
            <platform-button variant="primary" data-wiki-move-submit @click=${() => this._submit()}>
                ${this.t('move.submit')}
            </platform-button>
        `;
    }
}

customElements.define('wiki-move-page-modal', WikiMovePageModal);
registerModalKind(WikiMovePageModal.modalKind, 'wiki-move-page-modal');
