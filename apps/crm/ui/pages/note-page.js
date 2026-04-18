import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';
import '../components/note-editor.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-breadcrumbs.js';

export class NotePage extends PlatformElement {
    static properties = {
        itemId: { type: String },
        _note: { state: true },
        _noteId: { state: true },
        _draftMode: { state: true },
        _loading: { state: true },
        _notFound: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }

            .page-header {
                flex-shrink: 0;
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                margin-bottom: var(--space-4);
            }

            .page-title {
                font-size: 32px;
                line-height: 1.2;
                font-weight: 700;
                color: var(--text-primary);
                margin: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .note-editor-container {
                flex: 1;
                min-height: 0;
                overflow: hidden;
            }

            .loading {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-secondary);
            }

            .not-found {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                gap: var(--space-4);
                color: var(--text-secondary);
            }

            .not-found-icon {
                width: 64px;
                height: 64px;
                color: var(--text-tertiary);
            }

            .not-found-text {
                font-size: var(--text-lg);
            }

            .back-btn {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background var(--duration-fast);
            }

            .back-btn:hover {
                background: var(--glass-tint-medium);
            }

            @media (max-width: 767px) {
                .page-header {
                    padding: var(--space-3) var(--space-4) var(--space-2);
                    margin-bottom: var(--space-3);
                }

                .breadcrumbs {
                    margin-bottom: var(--space-1);
                }

                .page-title {
                    font-size: 24px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._note = null;
        this._noteId = null;
        this._draftMode = false;
        this._loading = true;
        this._notFound = false;
        this._storeUnsub = null;
        this._breadcrumbs = null;
        this._draftTitle = '';
    }

    connectedCallback() {
        super.connectedCallback();
        this._storeUnsub = CRMStore.subscribe(() => {
            const newNoteId = CRMStore.getCurrentNoteId();
            // Перезагружаем заметку только если изменился currentNoteId
            if (newNoteId !== this._noteId) {
                this._syncFromStore();
            }
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._storeUnsub?.();
        this._storeUnsub = null;
    }

    async firstUpdated() {
        super.firstUpdated?.();
        await this._syncFromStore();

        // Получаем ссылку на хлебные крошки
        this._breadcrumbs = this.shadowRoot?.querySelector('platform-breadcrumbs');
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        
        // Если заметка загружена и есть ссылка на хлебные крошки, обновляем заголовок
        if (changedProperties.has('_note') && this._note && this._breadcrumbs) {
            this._breadcrumbs.updateCurrentLabel(this._note?.name || 'Заметка');
        }
    }

    async _syncFromStore() {
        // Получаем noteId из свойств компонента (роутер передаёт itemId через Object.assign)
        const noteIdFromProps = this.itemId;
        
        // Если noteId нет в свойствах, пробуем получить из URL напрямую
        let noteIdFromUrl = noteIdFromProps;
        if (!noteIdFromUrl) {
            const pathname = window.location.pathname;
            const match = pathname.match(/\/crm\/notes\/([^\/]+)/);
            if (match && match[1]) {
                noteIdFromUrl = match[1];
            }
        }
        
        // Используем noteId из props/URL или из store, не меняя store (чтобы избежать цикла)
        const noteId = noteIdFromUrl || CRMStore.getCurrentNoteId();
        
        if (noteId === 'new' || (typeof noteId === 'string' && noteId.startsWith('draft-'))) {
            this._noteId = noteId;
            this._draftMode = true;
            this._draftTitle = '';
            const focusDate = CRMStore.getDailyNotesFocusDate();
            this._note = {
                entity_id: noteId === 'new' ? `draft-${Date.now()}` : noteId,
                entity_type: 'note',
                entity_subtype: null,
                name: '',
                description: '',
                note_date: focusDate,
                attributes: {},
            };
            this._loading = false;
            this._notFound = false;
            return;
        }

        if (typeof noteId !== 'string' || noteId.trim().length === 0) {
            this._notFound = true;
            this._loading = false;
            return;
        }

        this._noteId = noteId;
        this._draftMode = false;

        try {
            const crmApi = this.crmApi;
            const note = await CRMStore.getEntityById(crmApi, noteId);
            if (!note) {
                this._notFound = true;
                this._loading = false;
                return;
            }
            this._note = note;
            this._notFound = false;
            this._loading = false;
            this._draftTitle = note?.name || '';
            
            // Обновляем хлебные крошки с названием заметки
            if (this._breadcrumbs) {
                this._breadcrumbs.updateCurrentLabel(note?.name || 'Заметка');
            }
        } catch (error) {
            console.error('Failed to load note:', error);
            this._notFound = true;
            this._loading = false;
        }
    }

    _handleBack() {
        CRMStore.setCurrentView('notes');
    }

    _handleNoteCreated(event) {
        const noteId = event.detail?.noteId;
        if (typeof noteId === 'string' && noteId.trim().length > 0) {
            CRMStore.setCurrentNoteId(noteId);
            this._syncFromStore();
        }
    }

    _handleClose() {
        CRMStore.setCurrentView('notes');
    }

    render() {
        if (this._loading) {
            return html`
                <div class="loading">
                    <span>${this.i18n.t('note_page.loading', {}, 'crm')}</span>
                </div>
            `;
        }

        if (this._notFound) {
            return html`
                <div class="not-found">
                    <span class="not-found-text">${this.i18n.t('note_page.not_found', {}, 'crm')}</span>
                    <button class="back-btn" @click=${this._handleBack}>
                        <platform-icon name="arrow-left" size="16"></platform-icon>
                        ${this.i18n.t('note_page.back_to_notes', {}, 'crm')}
                    </button>
                </div>
            `;
        }

        return html`
            <div class="page-header">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <div class="note-editor-container">
                <note-editor
                    .note=${this._note}
                    .draftMode=${this._draftMode}
                    .startInEditMode=${this._draftMode}
                    .showTitle=${true}
                    @note-created=${this._handleNoteCreated}
                    @close=${this._handleClose}
                ></note-editor>
            </div>
        `;
    }
}

customElements.define('note-page', NotePage);
