/**
 * Notes List - Список заметок (левая панель split view)
 * Наследует CRMPanel для поддержки сворачивания
 */
import { html, css } from 'lit';
import { buttonStyles, iconButtonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { CRMPanel } from './crm-panel.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

function getLocalIsoDate() {
    const now = new Date();
    const year = String(now.getFullYear());
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

export class NotesList extends CRMPanel {
    static styles = [
        CRMPanel.panelStyles,
        buttonStyles,
        iconButtonStyles,
        formStyles,
        css`
            .search-row {
                display: flex;
                gap: var(--space-2);
                padding: 0 var(--space-4) var(--space-3);
            }
            
            .search-box {
                flex: 1;
                padding: var(--space-2) var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-sm);
                transition: all var(--duration-fast);
            }
            
            .search-box:focus {
                outline: none;
                border-color: var(--accent);
                background: var(--crm-surface);
            }
            
            .notes-container {
                flex: 1;
                overflow-y: auto;
                padding: var(--space-2);
            }
            
            .note-card {
                position: relative;
                padding: var(--space-3);
                margin-bottom: var(--space-2);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            
            .note-card:hover {
                background: var(--crm-surface);
                border-color: var(--accent-subtle);
                transform: translateX(4px);
            }
            
            .note-card.active {
                background: var(--crm-selected-bg);
                border-color: var(--crm-selected-stroke);
            }
            
            .delete-btn {
                position: absolute;
                top: var(--space-2);
                right: var(--space-2);
                width: 24px;
                height: 24px;
                padding: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                border: none;
                border-radius: var(--radius-sm);
                color: var(--text-tertiary);
                cursor: pointer;
                opacity: 0;
                transition: all var(--duration-fast);
            }
            
            .note-card:hover .delete-btn {
                opacity: 1;
            }

            .note-card:focus-within .delete-btn {
                opacity: 1;
            }
            
            .delete-btn:hover {
                color: var(--error);
                background: var(--crm-danger-bg);
            }
            
            .note-title {
                font-size: var(--text-base);
                font-weight: 500;
                color: var(--text-primary);
                margin-bottom: var(--space-2);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            
            .note-preview {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.4;
                overflow: hidden;
                text-overflow: ellipsis;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
            }
            
            .note-meta {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-top: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            
            .note-tags {
                display: flex;
                gap: var(--space-1);
                flex-wrap: wrap;
            }
            
            .note-tag {
                padding: 2px 8px;
                background: var(--crm-surface-tint);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
            }
            
            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-tertiary);
                padding: var(--space-8);
                text-align: center;
            }
            
            .empty-icon {
                width: 64px;
                height: 64px;
                margin-bottom: var(--space-4);
                opacity: 0.6;
            }
            
            .empty-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
            
            .loading {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-secondary);
            }

            @media (max-width: 767px) {
                .delete-btn {
                    opacity: 1;
                }
            }
        `
    ];

    constructor() {
        super();
        this.panelId = 'notes-list';
        this.panelTitle = '';
        this.panelIcon = 'doc-detail';
        
        this.state = this.use(s => ({
            notes: s.entities.notes,
            currentNoteId: s.entities.currentNoteId,
            searchQuery: s.ui.searchQuery,
            loading: s.loading,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        this.panelTitle = this.i18n.t('notes.title');
    }

    _formatDate(dateString) {
        if (!dateString) return '';
        
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);
        
        if (diffMins < 1) return this.i18n.t('notes_list.time_just_now');
        if (diffMins < 60) {
            return this.i18n.t('notes_list.time_mins_ago', { count: String(diffMins) });
        }
        if (diffHours < 24) {
            return this.i18n.t('notes_list.time_hours_ago', { count: String(diffHours) });
        }
        if (diffDays < 7) {
            return this.i18n.t('notes_list.time_days_ago', { count: String(diffDays) });
        }

        const loc = this.i18n.getCurrentLocale() === 'ru' ? 'ru-RU' : 'en-US';
        return date.toLocaleDateString(loc, {
            day: 'numeric',
            month: 'short',
        });
    }

    _getPreview(description) {
        if (!description) return this.i18n.t('notes_list.preview_empty');
        return description.substring(0, 100);
    }
    
    _onSelectNote(noteId) {
        CRMStore.setCurrentNote(noteId);
        this.emit('note-selected', { noteId });
    }
    
    async _onNewNote() {
        const crmApi = this.services.get('crmApi');
        await CRMStore.createNote(crmApi, {
            name: this.i18n.t('notes_list.new_note_default_name'),
            description: '',
            note_date: getLocalIsoDate(),
        });

        this.success(this.i18n.t('notes_list.success_created'));
    }
    
    _onSearchInput(e) {
        CRMStore.setSearchQuery(e.target.value);
    }
    
    async _onDeleteNote(e, noteId) {
        e.stopPropagation();
        
        if (!confirm(this.i18n.t('notes_list.confirm_delete'))) return;

        const crmApi = this.services.get('crmApi');
        await CRMStore.deleteNote(crmApi, noteId);
        this.success(this.i18n.t('notes_list.success_deleted'));
    }
    
    _filterNotes(notes, searchQuery) {
        if (!searchQuery) return notes;
        
        const query = searchQuery.toLowerCase();
        return notes.filter(note => 
            note.name?.toLowerCase().includes(query) ||
            note.description?.toLowerCase().includes(query)
        );
    }
    
    renderHeaderActions() {
        return html`
            <button 
                class="btn-icon primary"
                @click=${this._onNewNote}
                title=${this.i18n.t('notes_list.new_note_tooltip')}
            >
                <platform-icon name="plus" size="16"></platform-icon>
            </button>
        `;
    }

    renderContent() {
        const { notes, currentNoteId, searchQuery, loading } = this.state.value;
        
        if (loading) {
            return html`
                <div class="loading">
                    <div>${this.i18n.t('notes_list.loading_notes')}</div>
                </div>
            `;
        }
        
        const filteredNotes = this._filterNotes(notes, searchQuery);
        
        return html`
            <div class="search-row">
                <input 
                    type="text"
                    class="search-box"
                    placeholder=${this.i18n.t('notes_list.search_placeholder')}
                    .value=${searchQuery}
                    @input=${this._onSearchInput}
                />
            </div>
            
            <div class="notes-container">
                ${filteredNotes.length === 0 ? html`
                    <div class="empty-state">
                        <div class="empty-icon">
                            <platform-icon name="book-open" size="56"></platform-icon>
                        </div>
                        <div>${this.i18n.t('notes_list.empty')}</div>
                        <div style="margin-top: var(--space-2); font-size: var(--text-sm);">
                            ${this.i18n.t('notes_list.empty_cta')}
                        </div>
                    </div>
                ` : filteredNotes.map(note => html`
                    <div 
                        class="note-card ${note.entity_id === currentNoteId ? 'active' : ''}"
                        @click=${() => this._onSelectNote(note.entity_id)}
                    >
                        <button 
                            class="delete-btn" 
                            title=${this.i18n.t('notes_list.delete_tooltip')}
                            @click=${(e) => this._onDeleteNote(e, note.entity_id)}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                        </button>
                        <div class="note-title">${note.name}</div>
                        <div class="note-preview">${this._getPreview(note.description)}</div>
                        <div class="note-meta">
                            <span>${this._formatDate(note.updated_at)}</span>
                            ${note.tags && note.tags.length > 0 ? html`
                                <div class="note-tags">
                                    ${note.tags.slice(0, 2).map(tag => html`
                                        <span class="note-tag">${tag}</span>
                                    `)}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `)}
            </div>
        `;
    }
}

customElements.define('notes-list', NotesList);
