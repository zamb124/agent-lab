/**
 * RAG Module - Frontend JavaScript
 */
import { showNotification } from '/static/js/components/notification.js';

export default class RAGModule {
    constructor(app) {
        this.app = app;
        this.name = 'rag';
        this.version = '1.0.0';
        this.config = window.RAG_CONFIG || {};
        this.currentProvider = this.config.currentProvider;
        this.currentNamespace = this.config.currentNamespace;
        this.apiBase = this.config.apiBase || '/frontend/api/rag';
        this.i18n = this.config.i18n || {};
        this.uploadFiles = [];
    }
    
    t(key) {
        const keys = key.split('.');
        let value = this.i18n;
        for (const k of keys) {
            if (value && typeof value === 'object') {
                value = value[k];
            } else {
                return key;
            }
        }
        return value || key;
    }
    
    async init() {
        console.log('RAG Module initialized');
        
        // Глобальные объекты для обратной совместимости
        window.ragApp = this;
        this._setupGlobalFunctions();
        
        this.bindEvents();
        await this.loadNamespaces();
        
        if (this.currentNamespace) {
            await this.loadNamespaceDocuments(this.currentNamespace);
        } else {
            await this.loadDashboard();
        }
        
        // Тема
        const theme = localStorage.getItem('rag-theme') || 'dark';
        const icon = document.querySelector('.rag-theme-toggle i');
        if (icon) {
            icon.className = `ti ti-${theme === 'light' ? 'sun' : 'moon'}`;
        }
        
        return this;
    }
    
    _setupGlobalFunctions() {
        window.showCreateNamespaceModal = () => {
            document.getElementById('create-namespace-modal').classList.add('active');
            document.getElementById('namespace-name').focus();
        };
        
        window.hideCreateNamespaceModal = () => {
            document.getElementById('create-namespace-modal').classList.remove('active');
            document.getElementById('namespace-name').value = '';
            document.getElementById('namespace-description').value = '';
        };
        
        window.createNamespace = async () => {
            const name = document.getElementById('namespace-name').value.trim();
            const description = document.getElementById('namespace-description').value.trim();
            
            if (!name) {
                this.showToast(this.t('notifications.enterNamespaceName'), 'warning');
                return;
            }
            
            try {
                const response = await fetch(
                    `${this.apiBase}/namespaces?provider=${this.currentProvider}`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name, description })
                    }
                );
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to create namespace');
                }
                
                window.hideCreateNamespaceModal();
                this.showToast(this.t('notifications.namespaceCreated'), 'success');
                await this.loadNamespaces();
                await this.loadDashboard();
            } catch (error) {
                this.showToast(error.message, 'error');
            }
        };
        
        window.hideUploadModal = () => {
            document.getElementById('upload-document-modal').classList.remove('active');
        };
        
        window.hideSearchResults = () => {
            document.getElementById('search-results-modal').classList.remove('active');
        };
        
        window.toggleTheme = () => {
            const current = document.documentElement.getAttribute('data-rag-theme') || 'light';
            const next = current === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-rag-theme', next);
            localStorage.setItem('rag-theme', next);
            
            const icon = document.querySelector('.rag-theme-toggle i');
            if (icon) {
                icon.className = `ti ti-${next === 'light' ? 'sun' : 'moon'}`;
            }
        };
        
        window.toggleSidebar = () => {
            document.querySelector('.rag-sidebar').classList.toggle('open');
        };
    }
    
    bindEvents() {
        const namespaceSearch = document.getElementById('namespace-search');
        if (namespaceSearch) {
            namespaceSearch.addEventListener('input', (e) => {
                this.filterNamespaces(e.target.value);
            });
        }
        
        const globalSearch = document.getElementById('global-search');
        if (globalSearch) {
            globalSearch.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && e.target.value.trim()) {
                    this.performGlobalSearch(e.target.value.trim());
                }
            });
        }
        
        const fileInput = document.getElementById('file-input');
        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                this.handleFileSelect(e.target.files);
            });
        }
        
        const uploadZone = document.getElementById('upload-zone');
        if (uploadZone) {
            uploadZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadZone.classList.add('dragover');
            });
            
            uploadZone.addEventListener('dragleave', () => {
                uploadZone.classList.remove('dragover');
            });
            
            uploadZone.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadZone.classList.remove('dragover');
                this.handleFileSelect(e.dataTransfer.files);
            });
        }
    }
    
    async selectProvider(providerName) {
        this.currentProvider = providerName;
        
        document.querySelectorAll('.rag-provider-card').forEach(card => {
            if (card.dataset.provider === providerName) {
                card.classList.add('active');
            } else {
                card.classList.remove('active');
            }
        });
        
        await this.loadNamespaces();
        await this.loadDashboard();
    }
    
    async loadNamespaces() {
        const container = document.getElementById('namespace-list');
        if (!container) return;
        
        container.innerHTML = `
            <div class="rag-loading">
                <i class="ti ti-loader-2 spinning"></i>
                <span>${this.t('loading.default')}</span>
            </div>
        `;
        
        try {
            const response = await fetch(
                `${this.apiBase}/namespaces?provider=${this.currentProvider}`
            );
            
            if (!response.ok) throw new Error('Failed to load namespaces');
            
            const namespaces = await response.json();
            this.namespaces = namespaces;
            this.renderNamespaceList(namespaces);
        } catch (error) {
            container.innerHTML = `
                <div class="rag-empty">
                    <p>${this.t('errors.loadNamespaces')}</p>
                </div>
            `;
            this.showToast(this.t('errors.loadNamespaces'), 'error');
        }
    }
    
    renderNamespaceList(namespaces) {
        const container = document.getElementById('namespace-list');
        if (!container) return;
        
        if (namespaces.length === 0) {
            container.innerHTML = `
                <div class="rag-empty" style="padding: 20px;">
                    <p>${this.t('empty.namespaces')}</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = namespaces.map(ns => `
            <div class="rag-namespace-item ${ns.namespace_id === this.currentNamespace ? 'active' : ''}"
                 data-namespace-id="${ns.namespace_id}"
                 onclick="ragApp.selectNamespace('${ns.namespace_id}')">
                <i class="ti ti-folder"></i>
                <div class="rag-namespace-info">
                    <div class="rag-namespace-name">${this.escapeHtml(ns.name)}</div>
                    <div class="rag-namespace-meta">${ns.document_count} ${this.t('namespace.documents')}</div>
                </div>
            </div>
        `).join('');
    }
    
    filterNamespaces(query) {
        const items = document.querySelectorAll('.rag-namespace-item');
        const lowerQuery = query.toLowerCase();
        
        items.forEach(item => {
            const name = item.querySelector('.rag-namespace-name').textContent.toLowerCase();
            item.style.display = name.includes(lowerQuery) ? '' : 'none';
        });
    }
    
    async loadDashboard() {
        const container = document.getElementById('main-content');
        if (!container) return;
        
        const pageTitle = document.getElementById('page-title');
        if (pageTitle) pageTitle.textContent = this.t('nav.dashboard');
        
        container.innerHTML = `
            <div class="rag-dashboard-view">
                <div class="rag-loading-full">
                    <i class="ti ti-loader-2 spinning"></i>
                    <span>${this.t('loading.namespaces')}</span>
                </div>
            </div>
        `;
        
        try {
            const response = await fetch(
                `${this.apiBase}/namespaces?provider=${this.currentProvider}`
            );
            
            if (!response.ok) throw new Error('Failed to load namespaces');
            
            const namespaces = await response.json();
            this.renderDashboard(namespaces);
        } catch (error) {
            container.innerHTML = `
                <div class="rag-empty">
                    <i class="ti ti-database-off"></i>
                    <h3>${this.t('errors.loadNamespaces')}</h3>
                    <p>${this.t('errors.connection')}</p>
                </div>
            `;
        }
    }
    
    renderDashboard(namespaces) {
        const container = document.getElementById('main-content');
        if (!container) return;
        
        if (namespaces.length === 0) {
            container.innerHTML = `
                <div class="rag-empty">
                    <i class="ti ti-database"></i>
                    <h3>${this.t('empty.namespaces')}</h3>
                    <p>${this.t('empty.namespacesDescription')}</p>
                    <button class="rag-btn rag-btn-primary" onclick="showCreateNamespaceModal()">
                        <i class="ti ti-plus"></i>
                        ${this.t('actions.createNamespace')}
                    </button>
                </div>
            `;
            return;
        }
        
        container.innerHTML = `
            <div class="rag-namespace-grid">
                ${namespaces.map(ns => `
                    <div class="rag-namespace-card" onclick="ragApp.selectNamespace('${ns.namespace_id}')">
                        <div class="rag-namespace-card-header">
                            <div class="rag-namespace-card-title">${this.escapeHtml(ns.name)}</div>
                            <div class="rag-namespace-card-actions">
                                <button class="rag-btn rag-btn-icon rag-btn-sm rag-btn-danger" 
                                        onclick="event.stopPropagation(); ragApp.deleteNamespace('${ns.namespace_id}')"
                                        title="${this.t('actions.delete')}">
                                    <i class="ti ti-trash"></i>
                                </button>
                            </div>
                        </div>
                        <div class="rag-namespace-card-stats">
                            <div class="rag-stat">
                                <div class="rag-stat-value">${ns.document_count}</div>
                                <div class="rag-stat-label">${this.t('namespace.documents')}</div>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    async selectNamespace(namespaceId) {
        this.currentNamespace = namespaceId;
        
        window.history.pushState({}, '', `/rag/namespace/${namespaceId}`);
        
        document.querySelectorAll('.rag-namespace-item').forEach(item => {
            item.classList.toggle('active', item.dataset.namespaceId === namespaceId);
        });
        
        await this.loadNamespaceDocuments(namespaceId);
    }
    
    async loadNamespaceDocuments(namespaceId) {
        const container = document.getElementById('main-content');
        if (!container) return;
        
        const namespace = this.namespaces?.find(ns => ns.namespace_id === namespaceId);
        const pageTitle = document.getElementById('page-title');
        if (pageTitle) {
            pageTitle.textContent = namespace?.name || namespaceId;
        }
        
        container.innerHTML = `
            <div class="rag-namespace-view">
                <div class="rag-loading-full">
                    <i class="ti ti-loader-2 spinning"></i>
                    <span>${this.t('loading.documents')}</span>
                </div>
            </div>
        `;
        
        try {
            const response = await fetch(
                `${this.apiBase}/namespaces/${namespaceId}/documents?provider=${this.currentProvider}`
            );
            
            if (!response.ok) throw new Error('Failed to load documents');
            
            const documents = await response.json();
            this.renderDocuments(namespaceId, documents);
        } catch (error) {
            container.innerHTML = `
                <div class="rag-empty">
                    <i class="ti ti-file-off"></i>
                    <h3>${this.t('errors.loadDocuments')}</h3>
                    <p>${this.t('errors.connection')}</p>
                </div>
            `;
        }
    }
    
    renderDocuments(namespaceId, documents) {
        const container = document.getElementById('main-content');
        if (!container) return;
        
        const header = `
            <div class="rag-documents-header">
                <div class="rag-documents-title">
                    <button class="rag-btn rag-btn-icon rag-btn-sm" onclick="ragApp.loadDashboard(); window.history.pushState({}, '', '/rag/');">
                        <i class="ti ti-arrow-left"></i>
                    </button>
                    <h2>${this.t('namespace.documents')}</h2>
                    <span class="rag-documents-count">${documents.length}</span>
                </div>
                <button class="rag-btn rag-btn-primary" onclick="ragApp.showUploadModal('${namespaceId}')">
                    <i class="ti ti-upload"></i>
                    ${this.t('actions.upload')}
                </button>
            </div>
        `;
        
        if (documents.length === 0) {
            container.innerHTML = `
                ${header}
                <div class="rag-empty">
                    <i class="ti ti-file-upload"></i>
                    <h3>${this.t('empty.documents')}</h3>
                    <p>${this.t('empty.documentsDescription')}</p>
                    <button class="rag-btn rag-btn-primary" onclick="ragApp.showUploadModal('${namespaceId}')">
                        <i class="ti ti-upload"></i>
                        ${this.t('actions.uploadDocument')}
                    </button>
                </div>
            `;
            return;
        }
        
        container.innerHTML = `
            ${header}
            <div class="rag-documents-grid">
                ${documents.map(doc => this.renderDocumentCard(namespaceId, doc)).join('')}
            </div>
        `;
    }
    
    renderDocumentCard(namespaceId, doc) {
        const ext = doc.metadata?.file_type || this.getFileExtension(doc.name);
        const iconClass = this.getFileIconClass(ext);
        const statusClass = doc.status || 'ready';
        
        return `
            <div class="rag-document-card">
                <div class="rag-document-icon ${iconClass}">
                    <i class="ti ti-${this.getFileIcon(ext)}"></i>
                </div>
                <div class="rag-document-info">
                    <div class="rag-document-name" title="${this.escapeHtml(doc.name)}">
                        ${this.escapeHtml(doc.name)}
                    </div>
                    <div class="rag-document-meta">
                        <span class="rag-document-status ${statusClass}">${statusClass}</span>
                    </div>
                </div>
                <div class="rag-document-actions">
                    <button class="rag-btn rag-btn-icon rag-btn-sm" 
                            onclick="ragApp.downloadDocument('${namespaceId}', '${doc.document_id}')"
                            title="${this.t('actions.download')}">
                        <i class="ti ti-download"></i>
                    </button>
                    <button class="rag-btn rag-btn-icon rag-btn-sm rag-btn-danger" 
                            onclick="ragApp.deleteDocument('${namespaceId}', '${doc.document_id}')"
                            title="${this.t('actions.delete')}">
                        <i class="ti ti-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }
    
    getFileExtension(filename) {
        return (filename || '').split('.').pop()?.toLowerCase() || '';
    }
    
    getFileIconClass(ext) {
        const classes = {
            pdf: 'pdf',
            docx: 'docx',
            doc: 'docx',
            txt: 'txt',
            md: 'md',
            csv: 'csv',
            xlsx: 'xlsx',
            xls: 'xlsx',
            html: 'html',
            json: 'json',
            xml: 'html'
        };
        return classes[ext] || 'default';
    }
    
    getFileIcon(ext) {
        const icons = {
            pdf: 'file-description',
            docx: 'file-text',
            doc: 'file-text',
            txt: 'file-text',
            md: 'markdown',
            csv: 'file-spreadsheet',
            xlsx: 'file-spreadsheet',
            xls: 'file-spreadsheet',
            html: 'brand-html5',
            json: 'file-code',
            xml: 'file-code'
        };
        return icons[ext] || 'file';
    }
    
    async performGlobalSearch(query) {
        if (!this.currentNamespace) {
            this.showToast(this.t('notifications.selectNamespaceFirst'), 'warning');
            return;
        }
        
        const modal = document.getElementById('search-results-modal');
        const container = document.getElementById('search-results-container');
        
        modal.classList.add('active');
        container.innerHTML = `
            <div class="rag-loading-full">
                <i class="ti ti-loader-2 spinning"></i>
                <span>${this.t('loading.searching')}</span>
            </div>
        `;
        
        try {
            const response = await fetch(
                `${this.apiBase}/namespaces/${this.currentNamespace}/search?provider=${this.currentProvider}`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, limit: 10 })
                }
            );
            
            if (!response.ok) throw new Error('Search failed');
            
            const results = await response.json();
            this.renderSearchResults(query, results);
        } catch (error) {
            container.innerHTML = `
                <div class="rag-empty">
                    <i class="ti ti-search-off"></i>
                    <h3>${this.t('errors.searchFailed')}</h3>
                    <p>${this.t('errors.connection')}</p>
                </div>
            `;
        }
    }
    
    renderSearchResults(query, results) {
        const container = document.getElementById('search-results-container');
        
        if (results.length === 0) {
            container.innerHTML = `
                <div class="rag-empty">
                    <i class="ti ti-search-off"></i>
                    <h3>${this.t('modals.searchResults.noResults')}</h3>
                    <p>${this.t('modals.searchResults.noResultsDescription')}</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = `
            <div class="rag-search-results">
                ${results.map(result => `
                    <div class="rag-search-result">
                        <div class="rag-search-result-header">
                            <div class="rag-search-result-source">
                                <i class="ti ti-file-text"></i>
                                <span class="rag-search-result-doc">${this.escapeHtml(result.document_name)}</span>
                                <button class="rag-btn rag-btn-icon rag-btn-sm" 
                                    onclick="ragApp.downloadDocument('${result.namespace}', '${result.document_id}')"
                                    title="${this.t('actions.download')}">
                                    <i class="ti ti-download"></i>
                                </button>
                            </div>
                            <span class="rag-search-result-score">
                                ${Math.round(result.score * 100)}% ${this.t('modals.searchResults.match')}
                            </span>
                        </div>
                        <div class="rag-search-result-content">
                            ${this.highlightQuery(result.content, query)}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    highlightQuery(text, query) {
        const escaped = this.escapeHtml(text);
        const words = query.split(/\s+/).filter(w => w.length > 2);
        
        let highlighted = escaped;
        words.forEach(word => {
            const regex = new RegExp(`(${word})`, 'gi');
            highlighted = highlighted.replace(regex, '<mark>$1</mark>');
        });
        
        return highlighted;
    }
    
    showUploadModal(namespaceId) {
        this.uploadNamespaceId = namespaceId;
        this.uploadFiles = [];
        
        const modal = document.getElementById('upload-document-modal');
        const uploadList = document.getElementById('upload-list');
        const uploadBtn = document.getElementById('upload-btn');
        const fileInput = document.getElementById('file-input');
        
        uploadList.innerHTML = '';
        uploadBtn.disabled = true;
        fileInput.value = '';
        
        modal.classList.add('active');
    }
    
    handleFileSelect(files) {
        const uploadList = document.getElementById('upload-list');
        const uploadBtn = document.getElementById('upload-btn');
        
        Array.from(files).forEach(file => {
            if (!this.uploadFiles.some(f => f.name === file.name)) {
                this.uploadFiles.push(file);
            }
        });
        
        uploadList.innerHTML = this.uploadFiles.map((file, index) => `
            <div class="rag-upload-item">
                <i class="ti ti-file"></i>
                <span class="rag-upload-item-name">${this.escapeHtml(file.name)}</span>
                <span class="rag-upload-item-remove" onclick="ragApp.removeUploadFile(${index})">
                    <i class="ti ti-x"></i>
                </span>
            </div>
        `).join('');
        
        uploadBtn.disabled = this.uploadFiles.length === 0;
    }
    
    removeUploadFile(index) {
        this.uploadFiles.splice(index, 1);
        this.handleFileSelect([]);
    }
    
    async uploadDocuments() {
        const uploadBtn = document.getElementById('upload-btn');
        uploadBtn.disabled = true;
        uploadBtn.innerHTML = `<i class="ti ti-loader-2 spinning"></i> ${this.t('loading.uploading')}`;
        
        let successCount = 0;
        let errorCount = 0;
        
        for (const file of this.uploadFiles) {
            try {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('document_name', file.name);
                
                const response = await fetch(
                    `${this.apiBase}/namespaces/${this.uploadNamespaceId}/documents?provider=${this.currentProvider}`,
                    { method: 'POST', body: formData }
                );
                
                if (response.ok) {
                    successCount++;
                } else {
                    errorCount++;
                }
            } catch (error) {
                errorCount++;
            }
        }
        
        window.hideUploadModal();
        
        if (successCount > 0) {
            this.showToast(`${successCount} ${this.t('notifications.documentUploaded')}`, 'success');
            await this.loadNamespaceDocuments(this.uploadNamespaceId);
            await this.loadNamespaces();
        }
        
        if (errorCount > 0) {
            this.showToast(`${errorCount} ${this.t('notifications.documentUploadFailed')}`, 'error');
        }
    }
    
    async downloadDocument(namespaceId, documentId) {
        try {
            const response = await fetch(
                `${this.apiBase}/namespaces/${namespaceId}/documents/${documentId}/download?provider=${this.currentProvider}`
            );
            
            if (!response.ok) throw new Error('Failed to get download URL');
            
            const data = await response.json();
            window.open(data.download_url, '_blank');
        } catch (error) {
            this.showToast(this.t('errors.downloadDocument'), 'error');
        }
    }
    
    async deleteDocument(namespaceId, documentId) {
        if (!confirm(this.t('document.deleteConfirm'))) return;
        
        try {
            const response = await fetch(
                `${this.apiBase}/namespaces/${namespaceId}/documents/${documentId}?provider=${this.currentProvider}`,
                { method: 'DELETE' }
            );
            
            if (!response.ok) throw new Error('Failed to delete document');
            
            this.showToast(this.t('notifications.documentDeleted'), 'success');
            await this.loadNamespaceDocuments(namespaceId);
            await this.loadNamespaces();
        } catch (error) {
            this.showToast(this.t('errors.deleteDocument'), 'error');
        }
    }
    
    async deleteNamespace(namespaceId) {
        if (!confirm(this.t('namespace.deleteConfirm'))) return;
        
        try {
            const response = await fetch(
                `${this.apiBase}/namespaces/${namespaceId}?provider=${this.currentProvider}`,
                { method: 'DELETE' }
            );
            
            if (!response.ok) throw new Error('Failed to delete namespace');
            
            this.showToast(this.t('notifications.namespaceDeleted'), 'success');
            
            if (this.currentNamespace === namespaceId) {
                this.currentNamespace = null;
                window.history.pushState({}, '', '/rag/');
                await this.loadDashboard();
            }
            
            await this.loadNamespaces();
        } catch (error) {
            this.showToast(this.t('errors.deleteNamespace'), 'error');
        }
    }
    
    showToast(message, type = 'info') {
        const typeMap = {
            'success': 'success',
            'error': 'danger',
            'warning': 'warning',
            'info': 'info'
        };
        showNotification(message, typeMap[type] || 'info');
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }
}
