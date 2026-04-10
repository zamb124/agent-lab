/**
 * Note Editor - Редактор заметок с AI анализом и подсветкой сущностей
 */
import { html, css } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { CRMStore } from '../store/crm.store.js';
import './entity-preview-tooltip.js';
import '@platform/lib/components/platform-icon.js';

export class NoteEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        buttonStyles,
        formStyles,
        css`
            :host {
                display: block;
                width: 100%;
                height: 100%;
                background: var(--crm-surface);
                backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--crm-stroke-strong);
                border-radius: var(--radius-2xl);
                overflow: hidden;
                position: relative;
            }
            
            @media (max-width: 767px) {
                :host {
                    border-radius: 0;
                    border: none;
                }
            }
            
            .header {
                padding: var(--space-4);
                border-bottom: 1px solid var(--crm-stroke);
                background: var(--crm-surface-tint);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .title-input {
                flex: 1;
                padding: var(--space-2);
                background: transparent;
                border: none;
                color: var(--text-primary);
                font-size: var(--text-xl);
                font-weight: 600;
            }
            
            .title-input:focus {
                outline: none;
            }
            
            .editor-container {
                position: relative;
                height: calc(100% - 65px);
                overflow-y: auto;
                padding: var(--space-6);
            }

            .ai-analyze-btn {
                position: absolute;
                top: var(--space-3);
                right: var(--space-3);
                z-index: 10;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                background: var(--accent-secondary-subtle);
                border: 1px solid var(--crm-info-stroke);
                border-radius: var(--radius-lg);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                box-shadow: var(--glass-shadow-subtle);
            }

            .ai-analyze-btn:hover {
                background: var(--accent-secondary-subtle);
                border-color: var(--accent-secondary);
                transform: scale(1.05);
                box-shadow: var(--glass-shadow-medium);
            }

            .ai-analyze-btn:active {
                transform: scale(0.98);
            }

            .ai-analyze-btn.analyzing {
                animation: pulse 1.5s ease-in-out infinite;
            }

            .ai-analyze-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.6; }
            }
            
            .editor {
                min-height: 400px;
                color: var(--text-primary);
                font-size: var(--text-base);
                line-height: 1.6;
                outline: none;
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            
            .editor:empty:before {
                content: var(--note-editor-empty-placeholder, '');
                color: var(--text-tertiary);
            }
            
            .analyzing-indicator {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            
            .analyzing-spinner {
                width: 16px;
                height: 16px;
                border: 2px solid var(--glass-border-subtle);
                border-top: 2px solid var(--accent);
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-tertiary);
                text-align: center;
            }
            
            .empty-icon {
                width: 80px;
                height: 80px;
                margin-bottom: var(--space-4);
                opacity: 0.6;
            }
            
            .empty-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }

            .entity-mention {
                cursor: pointer;
                padding: 1px 4px;
                border-radius: var(--radius-sm);
                transition: filter var(--duration-fast) ease;
                border-bottom: 1px dashed currentColor;
            }

            .entity-mention:hover {
                filter: brightness(0.85);
            }

            .related-entities-bar {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid var(--crm-stroke);
                background: var(--glass-tint-subtle);
            }

            .related-entity-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border: 1px solid;
                border-radius: var(--radius-md);
                font-size: var(--text-xs);
                font-weight: 500;
                cursor: pointer;
                transition: filter var(--duration-fast) ease;
            }

            .related-entity-chip:hover {
                filter: brightness(0.9);
            }

            .chip-icon {
                font-size: var(--text-sm);
            }
        `
    ];

    static properties = {
        _currentNote: { state: true },
        _currentNoteId: { state: true },
        _noteText: { state: true },
        _analyzing: { state: true },
        _isMobile: { state: true },
        _relatedEntities: { state: true },
        _entityTypes: { state: true },
        _tooltipEntity: { state: true },
        _tooltipEntityType: { state: true },
        _tooltipX: { state: true },
        _tooltipY: { state: true },
        _tooltipVisible: { state: true },
        _isEditing: { state: true },
    };

    constructor() {
        super();
        this._currentNote = null;
        this._currentNoteId = null;
        this._noteText = '';
        this._analyzing = false;
        this._isMobile = false;
        this._relatedEntities = [];
        this._entityTypes = [];
        this._highlightTimer = null;
        this._saveTimer = null;
        this._tooltipEntity = null;
        this._tooltipEntityType = null;
        this._tooltipX = 0;
        this._tooltipY = 0;
        this._tooltipVisible = false;
        this._tooltipHideTimer = null;
        this._isEditing = false;
        this._highlightingInProgress = false;
        this._unsubscribe = null;
    }
    
    connectedCallback() {
        super.connectedCallback();
        this._subscribeToStore();
        this._initFromStore();
    }
    
    _initFromStore() {
        const state = CRMStore.state;
        const { currentNoteId, notes, noteText, noteRelatedEntities, entityTypes } = state.entities;
        const { analyzingNoteId } = state.ai;
        const { isMobile } = state.ui;
        
        this._currentNoteId = currentNoteId;
        this._noteText = noteText;
        this._analyzing = typeof analyzingNoteId === 'string' && analyzingNoteId === currentNoteId;
        this._isMobile = isMobile;
        this._relatedEntities = noteRelatedEntities || [];
        this._entityTypes = entityTypes || [];
        
        if (currentNoteId) {
            this._currentNote = notes.find(n => n.entity_id === currentNoteId) || null;
            if (this._currentNote) {
                this._loadNoteContentDelayed();
                this._loadNoteRelationships(currentNoteId);
            }
        }
    }
    
    _subscribeToStore() {
        if (this._unsubscribe) return;
        
        this._unsubscribe = CRMStore.subscribe(state => {
            const { currentNoteId, notes, noteText, noteRelatedEntities, entityTypes } = state.entities;
            const { analyzingNoteId } = state.ai;
            const { isMobile } = state.ui;
            
            const prevNoteId = this._currentNoteId;
            const prevNote = this._currentNote;
            
            this._currentNoteId = currentNoteId;
            this._noteText = noteText;
            this._analyzing = typeof analyzingNoteId === 'string' && analyzingNoteId === currentNoteId;
            this._isMobile = isMobile;
            this._relatedEntities = noteRelatedEntities || [];
            this._entityTypes = entityTypes || [];
            
            if (currentNoteId) {
                this._currentNote = notes.find(n => n.entity_id === currentNoteId) || null;
                
                const noteChanged = currentNoteId !== prevNoteId;
                const noteLoaded = !prevNote && this._currentNote;
                
                if ((noteChanged || noteLoaded) && this._currentNote) {
                    this._loadNoteContentDelayed();
                    this._loadNoteRelationships(currentNoteId);
                }
            } else {
                this._currentNote = null;
            }
        });
    }
    
    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
        this._unsubscribe = null;
        clearTimeout(this._highlightTimer);
        clearTimeout(this._saveTimer);
        clearTimeout(this._tooltipHideTimer);
    }
    
    async _loadNoteRelationships(noteId) {
        const crmApi = this.services.get('crmApi');
        await CRMStore.loadNoteRelationships(crmApi, noteId);
    }
    
    _loadNoteContentDelayed() {
        requestAnimationFrame(() => {
            this._loadNoteContent();
        });
    }
    
    _loadNoteContent() {
        if (!this._currentNote) return;
        
        const editor = this.shadowRoot?.querySelector('.editor');
        if (editor) {
            editor.innerText = this._currentNote.description || '';
            CRMStore.updateNoteText(this._currentNote.description || '');
        }
    }
    
    async _onTextInput(e) {
        const text = e.target.innerText;
        CRMStore.updateNoteText(text);
        
        clearTimeout(this._highlightTimer);
        this._highlightTimer = setTimeout(async () => {
            await this._highlightMentions(text);
        }, 800);
        
        clearTimeout(this._saveTimer);
        this._saveTimer = setTimeout(() => {
            this._autoSave(text);
        }, 2000);
    }
    
    async _highlightMentions(text) {
        if (!text || text.trim().length < 3) {
            return;
        }
        
        if (this._highlightingInProgress) {
            return;
        }
        
        this._highlightingInProgress = true;
        const crmApi = this.services.get('crmApi');
        
        try {
            await CRMStore.highlightMentions(crmApi, text);
        } finally {
            this._highlightingInProgress = false;
        }
    }
    
    async _autoSave(text) {
        if (!this._currentNoteId || !this._currentNote) return;
        
        const crmApi = this.services.get('crmApi');
        await CRMStore.updateNote(crmApi, this._currentNoteId, {
            description: text
        });
    }
    
    async _onTitleChange(e) {
        if (!this._currentNoteId) return;
        
        const title = e.target.value;
        
        const crmApi = this.services.get('crmApi');
        await CRMStore.updateNote(crmApi, this._currentNoteId, {
            name: title
        });
    }
    
    async _onAnalyze() {
        if (!this._noteText || !this._currentNoteId) return;
        
        const crmApi = this.services.get('crmApi');
        await CRMStore.analyzeNote(crmApi, this._currentNoteId);
        this.emit('analysis-ready', { noteId: this._currentNoteId });
        this.success(this.i18n.t('note_editor.analysis_complete'));
    }

    _onEditorFocus() {
        this._isEditing = true;
        this._tooltipVisible = false;
    }

    _onEditorBlur() {
        this._isEditing = false;
    }

    _onHighlightedClick() {
        this._isEditing = true;
        requestAnimationFrame(() => {
            const editor = this.shadowRoot?.querySelector('.editor[contenteditable]');
            if (editor) {
                editor.innerText = this._currentNote?.description || '';
                editor.focus();
                
                const range = document.createRange();
                range.selectNodeContents(editor);
                range.collapse(false);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
            }
        });
    }

    _getEntityTypeById(typeId) {
        return this._entityTypes.find(t => t.type_id === typeId);
    }

    _getEntityTypeConfig(entity) {
        const typeId = entity.entity_subtype || entity.entity_type;
        const entityType = this._getEntityTypeById(typeId);
        if (entityType) {
            return {
                icon: entityType.icon || 'folder',
                color: entityType.color || 'var(--text-tertiary)',
                label: entityType.name || typeId,
            };
        }
        return { icon: 'folder', color: 'var(--text-tertiary)', label: entity.entity_type };
    }

    _renderTextWithHighlights() {
        const text = this._currentNote?.description || '';
        if (!text || this._relatedEntities.length === 0) {
            return text;
        }

        const sortedEntities = [...this._relatedEntities].sort(
            (a, b) => b.name.length - a.name.length
        );

        let result = this._escapeHtml(text);

        for (const entity of sortedEntities) {
            const name = entity.name;
            if (!name) continue;

            const typeConfig = this._getEntityTypeConfig(entity);
            const bgColor = this._hexToRgba(typeConfig.color, 0.2);
            const textColor = typeConfig.color;

            const escapedName = this._escapeRegex(name);
            const regex = new RegExp(`(${escapedName})`, 'gi');
            
            result = result.replace(regex, (match) => {
                return `<span 
                    class="entity-mention" 
                    data-entity-id="${entity.entity_id}"
                    style="background: ${bgColor}; color: ${textColor};"
                >${match}</span>`;
            });
        }

        return result;
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    _escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    _hexToRgba(hex, alpha) {
        if (!hex) return `rgba(148, 163, 184, ${alpha})`;
        
        const cleanHex = hex.replace('#', '');
        const r = parseInt(cleanHex.substring(0, 2), 16);
        const g = parseInt(cleanHex.substring(2, 4), 16);
        const b = parseInt(cleanHex.substring(4, 6), 16);
        
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    _resolveIconName(iconName) {
        if (iconName === 'file') {
            return 'folder';
        }
        if (typeof iconName === 'string' && /^[a-z0-9-]+$/i.test(iconName)) {
            return iconName;
        }
        return 'folder';
    }

    _onEditorMouseOver(e) {
        if (this._isMobile) {
            return;
        }
        const mention = e.target.closest('.entity-mention');
        if (!mention) {
            return;
        }

        clearTimeout(this._tooltipHideTimer);

        const entityId = mention.dataset.entityId;
        const entity = this._relatedEntities.find(ent => ent.entity_id === entityId);
        if (!entity) return;

        const rect = mention.getBoundingClientRect();
        const hostRect = this.getBoundingClientRect();
        const typeId = entity.entity_subtype || entity.entity_type;
        const entityType = this._getEntityTypeById(typeId);

        this._tooltipEntity = entity;
        this._tooltipEntityType = entityType;
        this._tooltipX = rect.left - hostRect.left + rect.width / 2;
        this._tooltipY = rect.bottom - hostRect.top;
        this._tooltipVisible = true;
    }

    _onEditorMouseOut(e) {
        if (this._isMobile) {
            return;
        }
        const mention = e.target.closest('.entity-mention');
        if (!mention) return;

        this._tooltipHideTimer = setTimeout(() => {
            this._tooltipVisible = false;
        }, 150);
    }

    _onChipMouseEnter(entity, e) {
        if (this._isMobile) {
            return;
        }
        clearTimeout(this._tooltipHideTimer);

        const rect = e.currentTarget.getBoundingClientRect();
        const hostRect = this.getBoundingClientRect();
        const typeId = entity.entity_subtype || entity.entity_type;
        const entityType = this._getEntityTypeById(typeId);

        this._tooltipEntity = entity;
        this._tooltipEntityType = entityType;
        this._tooltipX = rect.left - hostRect.left + rect.width / 2;
        this._tooltipY = rect.bottom - hostRect.top;
        this._tooltipVisible = true;
    }

    _onChipMouseLeave() {
        if (this._isMobile) {
            return;
        }
        this._tooltipHideTimer = setTimeout(() => {
            this._tooltipVisible = false;
        }, 150);
    }

    _renderRelatedEntitiesBar() {
        if (this._relatedEntities.length === 0) {
            return '';
        }

        return html`
            <div class="related-entities-bar">
                ${this._relatedEntities.map(entity => {
                    const typeConfig = this._getEntityTypeConfig(entity);
                    const bgColor = this._hexToRgba(typeConfig.color, 0.15);
                    return html`
                        <div 
                            class="related-entity-chip"
                            style="border-color: ${typeConfig.color}60; background: ${bgColor}; color: ${typeConfig.color};"
                            @mouseenter=${(e) => this._onChipMouseEnter(entity, e)}
                            @mouseleave=${this._onChipMouseLeave}
                        >
                            <span class="chip-icon">
                                <platform-icon name="${this._resolveIconName(typeConfig.icon)}" size="14"></platform-icon>
                            </span>
                            <span>${entity.name}</span>
                        </div>
                    `;
                })}
            </div>
        `;
    }

    render() {
        if (!this._currentNoteId) {
            return html`
                <div class="empty-state">
                    <div class="empty-icon">
                        <platform-icon name="book-open" size="56"></platform-icon>
                    </div>
                    <div>${this.i18n.t('note_editor.empty_select_title')}</div>
                    <div style="margin-top: var(--space-2); font-size: var(--text-sm);">
                        ${this.i18n.t('note_editor.empty_select_subtitle')}
                    </div>
                </div>
            `;
        }
        
        if (!this._currentNote) {
            return html`<div class="empty-state">${this.i18n.t('loading', {}, 'common')}</div>`;
        }

        const hasRelatedEntities = this._relatedEntities.length > 0;
        const showHighlights = hasRelatedEntities && !this._isEditing;
        const highlightedContent = showHighlights 
            ? this._renderTextWithHighlights() 
            : '';
        
        return html`
            <div class="header">
                <input 
                    type="text"
                    class="title-input"
                    placeholder=${this.i18n.t('note_editor.note_title_placeholder')}
                    .value=${this._currentNote.name || ''}
                    @change=${this._onTitleChange}
                />
            </div>
            
            ${this._renderRelatedEntitiesBar()}
            
            <div class="editor-container">
                <button 
                    class="ai-analyze-btn ${this._analyzing ? 'analyzing' : ''}"
                    @click=${this._onAnalyze}
                    ?disabled=${this._analyzing}
                    title=${this._analyzing ? this.i18n.t('note_editor.analyze_analyzing') : this.i18n.t('note_editor.analyze_ai')}
                >
                    <platform-icon name="ai" size="22"></platform-icon>
                </button>
                
                ${showHighlights ? html`
                    <div 
                        class="editor"
                        @mouseover=${this._onEditorMouseOver}
                        @mouseout=${this._onEditorMouseOut}
                        @click=${this._onHighlightedClick}
                        style="cursor: text;"
                    >${unsafeHTML(highlightedContent)}</div>
                ` : html`
                    <div 
                        class="editor"
                        contenteditable="true"
                        @input=${this._onTextInput}
                        @focus=${this._onEditorFocus}
                        @blur=${this._onEditorBlur}
                    ></div>
                `}
            </div>

            <entity-preview-tooltip
                .entity=${this._tooltipEntity}
                .entityType=${this._tooltipEntityType}
                .x=${this._tooltipX}
                .y=${this._tooltipY}
                ?visible=${this._tooltipVisible}
            ></entity-preview-tooltip>
        `;
    }
}

customElements.define('note-editor', NoteEditor);
