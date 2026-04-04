/**
 * Список документов: интеграция, открытие редактора; новый/загрузка — shell-actions + сайдбар.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { OfficeStore } from '../store/office.store.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/glass-input.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class DocumentsListPage extends PlatformElement {
    static properties = {
        _items: { state: true },
        _loading: { state: true },
        _integrationOk: { state: true },
        _integrationDetail: { state: true },
        _renameOpen: { state: true },
        _renameId: { state: true },
        _renameTitle: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: block;
                width: 100%;
            }
            .integration-banner {
                padding: var(--space-3) var(--space-4);
                margin-bottom: var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-subtle);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .integration-banner.warn {
                border-color: rgba(245, 158, 11, 0.45);
                background: rgba(245, 158, 11, 0.08);
            }
            .doc-page-heading {
                margin: 0 0 var(--space-4);
                font-size: 42px;
                line-height: 1;
                font-weight: 700;
                background: var(
                    --documents-title-gradient,
                    linear-gradient(105deg, #3ec9d8 0%, #6cb1e1 42%, #737ce9 100%)
                );
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
                color: transparent;
            }
            .doc-table {
                width: 100%;
                border-collapse: collapse;
                font-size: var(--text-sm);
            }
            .doc-table th,
            .doc-table td {
                padding: var(--space-3) var(--space-2);
                text-align: left;
                border-bottom: 1px solid var(--documents-stroke);
                vertical-align: middle;
            }
            .doc-table th {
                color: var(--text-tertiary);
                font-size: 13px;
                font-weight: 500;
            }
            .doc-title-cell {
                max-width: 0;
                width: 32%;
            }
            .doc-created-cell {
                font-size: 13px;
                font-weight: 500;
                line-height: 18px;
                color: var(--text-secondary);
                white-space: nowrap;
            }
            .doc-creator-cell {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }
            .doc-creator-avatar {
                position: relative;
                flex: 0 0 28px;
                width: 28px;
                height: 28px;
                border-radius: var(--radius-full);
                overflow: hidden;
                background: var(--glass-solid-medium);
                border: 1px solid var(--documents-stroke);
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .doc-creator-initial {
                font-size: 11px;
                font-weight: 700;
                color: var(--text-secondary);
                line-height: 1;
            }
            .doc-creator-img {
                position: absolute;
                inset: 0;
                z-index: 1;
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }
            .doc-creator-name {
                font-size: 15px;
                font-weight: 600;
                line-height: 20px;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
            }
            .doc-title-link {
                display: block;
                width: 100%;
                margin: 0;
                padding: 0;
                border: none;
                background: none;
                font: inherit;
                font-size: 15px;
                line-height: 20px;
                font-weight: 700;
                color: color-mix(in srgb, var(--documents-selected-text) 58%, white 42%);
                text-align: left;
                cursor: pointer;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                transition: color var(--duration-fast) var(--easing-default);
            }
            .doc-title-link:hover:not(:disabled) {
                color: var(--documents-link-hover);
            }
            .doc-title-link:focus-visible {
                outline: none;
                border-radius: var(--radius-sm);
                box-shadow: var(--focus-ring);
            }
            .doc-title-link:disabled {
                cursor: default;
                color: var(--text-secondary);
                opacity: 0.85;
            }
            .doc-title-static {
                display: block;
                font-size: 15px;
                line-height: 20px;
                font-weight: 700;
                color: color-mix(in srgb, var(--documents-selected-text) 45%, var(--text-secondary) 55%);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .doc-type-cell {
                display: flex;
                align-items: center;
                justify-content: flex-start;
            }
            .doc-actions {
                display: flex;
                gap: var(--space-1);
                flex-wrap: wrap;
                align-items: center;
            }
            .doc-action-btn {
                box-sizing: border-box;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                margin: 0;
                padding: 0;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                transition:
                    background var(--duration-fast) var(--easing-default),
                    color var(--duration-fast) var(--easing-default);
            }
            .doc-action-btn:hover:not(:disabled) {
                background: var(--glass-solid-subtle);
                color: var(--accent);
            }
            .doc-action-btn:focus-visible {
                outline: none;
                box-shadow: var(--focus-ring);
            }
            .doc-action-btn:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
            .doc-action-btn--danger:hover:not(:disabled) {
                color: var(--error);
            }
            .modal-actions-inner {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                flex-wrap: wrap;
            }
            .doc-list-body {
                flex: 1;
                display: flex;
                flex-direction: column;
                min-height: min(52vh, 440px);
            }
            .doc-empty-wrap {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-8) var(--space-4);
                box-sizing: border-box;
            }
            .doc-empty {
                text-align: center;
                max-width: 26rem;
            }
            .doc-empty-icon-wrap {
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto var(--space-5);
                width: 88px;
                height: 88px;
                border-radius: var(--radius-2xl);
                background: color-mix(in srgb, var(--documents-selected-text) 12%, transparent);
                border: 1px solid color-mix(in srgb, var(--documents-stroke) 55%, transparent);
            }
            .doc-empty-icon-wrap platform-icon {
                opacity: 0.42;
                color: var(--documents-selected-text);
            }
            .doc-empty-title {
                margin: 0 0 var(--space-2);
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.25;
            }
            .doc-empty-hint {
                margin: 0 0 var(--space-5);
                font-size: var(--text-base);
                line-height: 1.5;
                color: var(--text-secondary);
            }
            .doc-empty-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: center;
                flex-wrap: wrap;
            }
        `,
    ];

    constructor() {
        super();
        this._items = [];
        this._loading = true;
        this._integrationOk = true;
        this._integrationDetail = '';
        this._renameOpen = false;
        this._renameId = '';
        this._renameTitle = '';
        this._unsub = null;
        this._onListReload = () => {
            void this._loadAll();
        };
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsub = OfficeStore.subscribe(() => this._syncFromStore());
        window.addEventListener(AppEvents.AUTH_CHANGE, this._boundReload);
        window.addEventListener('storage', this._boundReload);
        window.addEventListener('office-documents-list-reload', this._onListReload);
        this._syncFromStore();
        void this._loadAll();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsub?.();
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._boundReload);
        window.removeEventListener('storage', this._boundReload);
        window.removeEventListener('office-documents-list-reload', this._onListReload);
    }

    _boundReload = () => {
        void this._loadAll();
    };

    _syncFromStore() {
        const s = OfficeStore.state;
        this._items = s.documents.items;
        this._loading = s.documents.loading;
        if (s.integration.loaded) {
            this._integrationOk = s.integration.configured;
            this._integrationDetail = s.integration.detail;
        }
    }

    async _loadAll() {
        const api = this.services.officeApi;
        if (!api) {
            return;
        }
        OfficeStore.setDocumentsLoading(true);
        try {
            const st = await api.getIntegrationStatus();
            OfficeStore.setIntegrationStatus(!!st.configured, st.detail || '');
            this._integrationOk = !!st.configured;
            this._integrationDetail = st.detail || '';
            if (!st.configured) {
                OfficeStore.setDocumentsItems([]);
                return;
            }
            const list = await api.listDocuments();
            const items = list.items || [];
            OfficeStore.setDocumentsItems(items);
            this._items = items;
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            OfficeStore.setDocumentsError(msg);
            this.error(this.i18n.t('list.loadError', { message: msg }));
        } finally {
            OfficeStore.setDocumentsLoading(false);
            this._loading = false;
            this.requestUpdate();
        }
    }

    /**
     * @param {string} documentType
     */
    _fileIconName(documentType) {
        const t = String(documentType || '').trim().toLowerCase();
        if (t === 'word' || t === 'cell' || t === 'slide') {
            return t;
        }
        return '';
    }

    /**
     * @param {string} displayName
     */
    _creatorInitial(displayName) {
        const s = String(displayName || '').trim();
        if (s.length === 0) {
            return '?';
        }
        const ch = s.charAt(0);
        return ch.toUpperCase();
    }

    /**
     * @param {string | undefined} iso
     */
    _formatDocumentCreatedAt(iso) {
        if (typeof iso !== 'string' || iso.trim() === '') {
            return '';
        }
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) {
            return '';
        }
        const loc = this.i18n.getCurrentLocale() === 'ru' ? 'ru-RU' : 'en-GB';
        return new Intl.DateTimeFormat(loc, {
            dateStyle: 'medium',
            timeStyle: 'short',
        }).format(d);
    }

    /**
     * @param {Record<string, unknown>} row
     * @param {(k: string, p?: Record<string, string>) => string} tr
     */
    _renderCreatorCell(row, tr) {
        const name =
            typeof row.created_by_display_name === 'string'
                ? row.created_by_display_name
                : String(row.created_by_user_id ?? '');
        const rawUrl = row.created_by_avatar_url;
        const url = typeof rawUrl === 'string' && rawUrl.trim() !== '' ? rawUrl.trim() : '';
        const initial = this._creatorInitial(name);
        const aria = tr('list.creatorAria', { name });
        return html`
            <div class="doc-creator-cell" role="group" aria-label=${aria}>
                <div class="doc-creator-avatar" aria-hidden="true">
                    <span class="doc-creator-initial">${initial}</span>
                    ${url
                        ? html`
                              <img
                                  class="doc-creator-img"
                                  src=${url}
                                  alt=""
                                  @error=${(e) => {
                                      const el = e.target;
                                      if (el instanceof HTMLImageElement) {
                                          el.style.display = 'none';
                                      }
                                  }}
                              />
                          `
                        : null}
                </div>
                <span class="doc-creator-name">${name}</span>
            </div>
        `;
    }

    _goEdit(bindingId) {
        window.history.pushState({}, '', `/documents/edit/${encodeURIComponent(bindingId)}`);
        window.dispatchEvent(new Event('popstate'));
    }

    _openRename(bindingId, title) {
        this._renameId = bindingId;
        this._renameTitle = title;
        this._renameOpen = true;
    }

    _closeRename() {
        this._renameOpen = false;
        this._renameId = '';
        this._renameTitle = '';
    }

    async _saveRename() {
        const api = this.services.officeApi;
        const id = this._renameId;
        const title = (this._renameTitle || '').trim();
        if (!api || !id || title.length === 0) {
            return;
        }
        try {
            await api.renameDocument(id, title);
            this.success(this.i18n.t('list.renamed'));
            this._closeRename();
            await this._loadAll();
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
    }

    _emitOpenEmpty() {
        window.dispatchEvent(new CustomEvent('office-documents-open-empty'));
    }

    _emitPickUpload() {
        window.dispatchEvent(new CustomEvent('office-documents-pick-file'));
    }

    async _deleteDoc(bindingId, title) {
        const t = (k, p) => this.i18n.t(k, p);
        const confirmed = await platformConfirm(t('list.deleteConfirm', { title }), {
            title: t('list.deleteConfirmTitle'),
            confirmText: t('list.delete'),
            cancelText: t('list.cancel'),
            variant: 'danger',
            confirmVariant: 'danger',
        });
        if (!confirmed) {
            return;
        }
        const api = this.services.officeApi;
        if (!api) {
            return;
        }
        try {
            await api.deleteDocument(bindingId);
            this.success(this.i18n.t('list.deleted'));
            await this._loadAll();
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(msg);
        }
    }

    render() {
        const t = (k, p) => this.i18n.t(k, p);
        return html`
            <h1 class="doc-page-heading">${t('list.heading')}</h1>

            ${!this._integrationOk
                ? html`
                      <div class="integration-banner warn" role="status">
                          ${this._integrationDetail
                              ? this._integrationDetail
                              : t('integration.notConfigured')}
                      </div>
                  `
                : null}

            ${this._loading
                ? html`<p>${t('list.loading')}</p>`
                : (this._items || []).length > 0
                  ? html`
                        <table class="doc-table" aria-label=${t('list.tableAria')}>
                            <thead>
                                <tr>
                                    <th>${t('list.colTitle')}</th>
                                    <th>${t('list.colType')}</th>
                                    <th>${t('list.colActions')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${(this._items || []).map(
                                    (row) => html`
                                        <tr>
                                            <td class="doc-title-cell">
                                                ${this._integrationOk
                                                    ? html`
                                                          <button
                                                              type="button"
                                                              class="doc-title-link"
                                                              aria-label=${t('list.openDocument', {
                                                                  title: row.title,
                                                              })}
                                                              @click=${() => this._goEdit(row.binding_id)}
                                                          >
                                                              ${row.title}
                                                          </button>
                                                      `
                                                    : html`
                                                          <span class="doc-title-static">${row.title}</span>
                                                      `}
                                            </td>
                                            <td class="doc-created-cell">
                                                ${this._formatDocumentCreatedAt(
                                                    typeof row.created_at === 'string'
                                                        ? row.created_at
                                                        : '',
                                                )}
                                            </td>
                                            <td>${this._renderCreatorCell(row, t)}</td>
                                            <td>
                                                ${this._fileIconName(row.document_type)
                                                    ? html`
                                                          <div
                                                              class="doc-type-cell"
                                                              role="img"
                                                              aria-label=${t(
                                                                  `list.docType.${row.document_type}`,
                                                              )}
                                                              title=${t(
                                                                  `list.docType.${row.document_type}`,
                                                              )}
                                                          >
                                                              <platform-icon
                                                                  file-icon
                                                                  name=${row.document_type}
                                                                  .size=${28}
                                                                  colored
                                                              ></platform-icon>
                                                          </div>
                                                      `
                                                    : html`<span>${row.document_type}</span>`}
                                            </td>
                                            <td>
                                                <div class="doc-actions">
                                                    <button
                                                        type="button"
                                                        class="doc-action-btn"
                                                        aria-label=${t('list.rename')}
                                                        @click=${() =>
                                                            this._openRename(row.binding_id, row.title)}
                                                    >
                                                        <platform-icon
                                                            name="edit"
                                                            .size=${20}
                                                        ></platform-icon>
                                                    </button>
                                                    <button
                                                        type="button"
                                                        class="doc-action-btn doc-action-btn--danger"
                                                        aria-label=${t('list.delete')}
                                                        @click=${() =>
                                                            this._deleteDoc(row.binding_id, row.title)}
                                                    >
                                                        <platform-icon
                                                            name="trash"
                                                            .size=${20}
                                                        ></platform-icon>
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    `,
                                )}
                            </tbody>
                        </table>
                    `
                  : html`
                        <div
                            class="doc-list-body"
                            role="region"
                            aria-label=${t('list.emptyStateAria')}
                        >
                            <div class="doc-empty-wrap">
                                <div class="doc-empty">
                                    <div class="doc-empty-icon-wrap" aria-hidden="true">
                                        <platform-icon name="doc-detail" size="44"></platform-icon>
                                    </div>
                                    <h2 class="doc-empty-title">${t('list.emptyStateTitle')}</h2>
                                    <p class="doc-empty-hint">${t('list.emptyStateHint')}</p>
                                    <div class="doc-empty-actions">
                                        <platform-button
                                            variant="primary"
                                            ?disabled=${!this._integrationOk}
                                            @click=${this._emitOpenEmpty}
                                        >
                                            ${t('list.newEmpty')}
                                        </platform-button>
                                        <platform-button
                                            variant="secondary"
                                            ?disabled=${!this._integrationOk}
                                            @click=${this._emitPickUpload}
                                        >
                                            ${t('list.upload')}
                                        </platform-button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `}

            <glass-modal
                .open=${this._renameOpen}
                heading=${t('list.renameHeading')}
                @modal-closed=${() => this._closeRename()}
            >
                <div slot="content" style="width:100%;box-sizing:border-box;">
                    <label
                        for="doc-rename-title-input"
                        style="display:block;margin-bottom:var(--space-2);font-size:var(--text-xs);font-weight:500;color:var(--text-secondary);"
                    >${t('list.renameLabel')}</label>
                    <glass-input
                        id="doc-rename-title-input"
                        .value=${this._renameTitle}
                        @input=${(e) => {
                            const v = e.detail?.value;
                            if (typeof v === 'string') {
                                this._renameTitle = v;
                            }
                        }}
                    ></glass-input>
                </div>
                <div slot="actions" class="modal-actions-inner">
                    <platform-button variant="secondary" @click=${this._closeRename}>
                        ${t('list.cancel')}
                    </platform-button>
                    <platform-button variant="primary" @click=${() => void this._saveRename()}>
                        ${t('list.save')}
                    </platform-button>
                </div>
            </glass-modal>
        `;
    }
}

customElements.define('documents-list-page', DocumentsListPage);
