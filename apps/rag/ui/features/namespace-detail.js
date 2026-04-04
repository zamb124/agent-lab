/**
 * Namespace Detail - просмотр и управление документами в namespace
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles, iconButtonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { RagStore } from '../store/rag.store.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import { resolveFileIconKey } from '@platform/services/icon.service.js';

export class NamespaceDetail extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        buttonStyles,
        iconButtonStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: var(--space-8);
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .menu-btn {
                display: none;
            }
            
            @media (max-width: 767px) {
                .menu-btn {
                    display: flex;
                    width: 36px;
                    height: 36px;
                    align-items: center;
                    justify-content: center;
                    border-radius: var(--radius-lg);
                    background: var(--glass-solid-strong);
                    border: 1px solid var(--glass-border-medium);
                    color: var(--text-primary);
                    cursor: pointer;
                    flex-shrink: 0;
                }
            }
            
            .title {
                font-size: var(--text-3xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                letter-spacing: var(--tracking-tight);
            }
            
            .subtitle {
                font-size: var(--text-base);
                color: var(--text-secondary);
                margin-top: var(--space-1);
            }
            
            .actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .documents-list {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .document-card {
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                transition: all var(--duration-fast);
            }
            
            .document-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
            }
            
            .document-header {
                display: flex;
                justify-content: space-between;
                align-items: start;
                margin-bottom: var(--space-2);
            }
            
            .document-name {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            
            .document-meta {
                display: flex;
                gap: var(--space-4);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .document-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .empty {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: var(--space-12);
                text-align: center;
            }
            
            .empty-icon {
                width: 80px;
                height: 80px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-bottom: var(--space-4);
                opacity: 0.3;
                color: var(--text-tertiary);
            }
            
            .empty-text {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            
            .empty-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            input[type="file"] {
                display: none;
            }
            
            .drop-zone {
                margin-top: var(--space-6);
                padding: var(--space-12);
                border: 2px dashed var(--glass-border-medium);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                text-align: center;
                transition: all var(--duration-fast);
                cursor: pointer;
            }
            
            .drop-zone:hover,
            .drop-zone.drag-over {
                border-color: var(--accent);
                background: var(--glass-solid-medium);
            }
            
            .drop-zone-content {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
            }
            
            .drop-zone-icon {
                width: 64px;
                height: 64px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                color: var(--accent);
            }
            
            .drop-zone-icon platform-icon {
                transition: transform var(--duration-fast);
            }
            
            .drop-zone:hover .drop-zone-icon platform-icon {
                transform: scale(1.1);
            }
            
            .drop-zone-text {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            
            .drop-zone-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .loading-spinner {
                width: 48px;
                height: 48px;
                border: 4px solid var(--glass-border-subtle);
                border-top: 4px solid var(--accent);
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        `
    ];
    
    constructor() {
        super();
        this.state = this.use(s => ({
            currentNamespaceId: s.namespaces.currentId,
            namespaces: s.namespaces.list,
            documents: s.namespaces.documents,
            loading: s.loading,
            uploading: s.uploading,
        }));
        this._dragOver = false;
    }
    
    connectedCallback() {
        super.connectedCallback();
        this._loadDocuments();
    }
    
    async _loadDocuments() {
        const { currentNamespaceId } = this.state.value;
        if (!currentNamespaceId) return;
        
        const ragApi = this.services.get('ragApi');
        await RagStore.loadDocuments(ragApi, currentNamespaceId);
    }
    
    _goBack() {
        RagStore.setCurrentView('namespaces');
    }
    
    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', {
            bubbles: true,
            composed: true,
        }));
    }
    
    _getCurrentNamespace() {
        const { currentNamespaceId, namespaces } = this.state.value;
        return namespaces.find(ns => ns.namespace_id === currentNamespaceId);
    }
    
    _handleFileSelect(e) {
        const file = e.target.files[0];
        if (!file) return;
        
        this._uploadFile(file);
    }
    
    async _uploadFile(file) {
        const { currentNamespaceId } = this.state.value;
        const ragApi = this.services.get('ragApi');
        
        await RagStore.uploadDocument(ragApi, currentNamespaceId, file);
        this.success(this.i18n.t('notifications.document_uploaded_named', { name: file.name }));
    }
    
    async _deleteDocument(documentId) {
        const { currentNamespaceId } = this.state.value;
        const ragApi = this.services.get('ragApi');
        
        if (!confirm(this.i18n.t('document.delete_confirm'))) return;
        
        await RagStore.deleteDocument(ragApi, currentNamespaceId, documentId);
        this.success(this.i18n.t('notifications.document_deleted'));
    }
    
    _triggerFileInput() {
        const input = this.shadowRoot.querySelector('input[type="file"]');
        input?.click();
    }
    
    _handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = true;
        this.requestUpdate();
    }
    
    _handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = false;
        this.requestUpdate();
    }
    
    _handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = false;
        this.requestUpdate();
        
        const files = Array.from(e.dataTransfer?.files || []);
        if (files.length > 0) {
            this._uploadFile(files[0]);
        }
    }
    
    _handleDropZoneClick() {
        this._triggerFileInput();
    }
    
    render() {
        const { currentNamespaceId, documents, loading, uploading } = this.state.value;
        const namespace = this._getCurrentNamespace();
        const namespaceDocuments = documents[currentNamespaceId] || [];
        
        if (!namespace) {
            return html`
                <div class="empty">
                    <div class="empty-text">${this.i18n.t('namespace_detail.not_found')}</div>
                </div>
            `;
        }
        
        return html`
            <div class="header">
                <div class="header-left">
                    <button class="menu-btn" @click=${this._openSidebar} title=${this.i18n.t('namespace_detail.open_menu')}>
                        <platform-icon name="menu" size="20"></platform-icon>
                    </button>
                    <button class="btn-icon" @click=${this._goBack}>
                        <platform-icon name="chevron-left" size="20"></platform-icon>
                    </button>
                    <div>
                        <h1 class="title">${namespace.name}</h1>
                        <p class="subtitle">${this.i18n.t('namespace_detail.documents_count', { count: namespaceDocuments.length })}</p>
                    </div>
                </div>
                <div class="actions">
                    <button class="btn btn-primary" @click=${this._triggerFileInput} ?disabled=${uploading}>
                        <platform-icon name="plus" size="18"></platform-icon>
                        <span>${uploading ? this.i18n.t('namespace_detail.uploading_short') : this.i18n.t('namespace_detail.upload_document')}</span>
                    </button>
                </div>
            </div>
            
            <input 
                type="file" 
                @change=${this._handleFileSelect} 
                accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.html,.htm,.txt,.md,.rst,.rtf,.odt,.csv,.tsv,.eml,.msg,.epub,.jpg,.jpeg,.png,.tiff,.bmp"
            />
            
            ${loading ? html`
                <div class="empty">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">${this.i18n.t('namespace_detail.loading_documents')}</div>
                </div>
            ` : html`
                ${namespaceDocuments.length === 0 ? html`
                    <div 
                        class="drop-zone ${this._dragOver ? 'drag-over' : ''}"
                        @click=${this._handleDropZoneClick}
                        @dragover=${this._handleDragOver}
                        @dragleave=${this._handleDragLeave}
                        @drop=${this._handleDrop}
                    >
                        <div class="drop-zone-content">
                            <div class="drop-zone-icon">
                                <platform-icon name="${uploading ? 'refresh' : 'cloud'}" size="32"></platform-icon>
                            </div>
                            <div class="drop-zone-text">
                                ${uploading ? this.i18n.t('namespace_detail.uploading_document') : this.i18n.t('namespace_detail.drop_here')}
                            </div>
                            <div class="drop-zone-hint">
                                ${this.i18n.t('namespace_detail.drop_or_choose')}<br>
                                ${this.i18n.t('namespace_detail.supported_formats')}
                            </div>
                        </div>
                    </div>
                ` : html`
                    <div class="documents-list">
                        ${namespaceDocuments.map(doc => html`
                            <div class="document-card">
                                <div class="document-header">
                                    <div>
                                        <div class="document-name">
                                            <platform-icon
                                                file-icon
                                                name=${resolveFileIconKey(doc.name || '', '')}
                                                size="16"
                                            ></platform-icon>
                                            ${doc.name || doc.document_id}
                                        </div>
                                        <div class="document-meta">
                                            <span>${this.i18n.t('namespace_detail.created_label')} ${new Date(doc.created_at).toLocaleDateString()}</span>
                                            ${doc.pages ? html`<span>${this.i18n.t('namespace_detail.pages_count', { count: doc.pages })}</span>` : ''}
                                        </div>
                                    </div>
                                    <div class="document-actions">
                                        <button class="btn-icon danger" @click=${() => this._deleteDocument(doc.document_id)} title=${this.i18n.t('namespace_detail.delete_title')}>
                                            <platform-icon name="trash" size="16"></platform-icon>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        `)}
                    </div>
                `}
            `}
        `;
    }
}

customElements.define('namespace-detail', NamespaceDetail);
