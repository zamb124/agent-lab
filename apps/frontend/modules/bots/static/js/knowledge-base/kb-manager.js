/**
 * Knowledge Base Manager
 */

import { showNotification } from '/static/js/components/notification.js';

export class KnowledgeBaseManager {
    constructor(authToken) {
        this.authToken = authToken;
    }
    
    async loadDocuments(flowId) {
        const listContainer = document.getElementById('knowledge-base-docs-list');
        if (!listContainer) return;
        
        listContainer.innerHTML = '<div class="loading-indicator"><div class="spinner"></div></div>';
        
        try {
            const response = await fetch(`/agents/api/v1/knowledge-base/flows/${flowId}/documents`);
            
            if (!response.ok) {
                throw new Error('Ошибка получения списка документов');
            }
            
            const data = await response.json();
            const documents = data.documents || [];
            
            if (documents.length === 0) {
                listContainer.innerHTML = `
                    <div class="empty-state">
                        <i class="ti ti-inbox"></i>
                        <p>В базе знаний пока нет документов</p>
                        <p class="text-muted">Загрузите документы чтобы бот мог использовать их для ответов</p>
                    </div>
                `;
                return;
            }
            
            const escapeAttr = (value) => String(value)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;');
            
            let html = '<div class="documents-grid">';
            
            documents.forEach(doc => {
                const statusIcon = {
                    'ready': '<i class="ti ti-check-circle-fill text-success"></i>',
                    'processing': '<i class="ti ti-hourglass-split text-warning"></i>',
                    'failed': '<i class="ti ti-x-circle-fill text-danger"></i>'
                }[doc.status] || '<i class="ti ti-question-circle"></i>';
                
                const downloadUrl = doc.metadata && (doc.metadata.source_url || doc.metadata.signed_url) ? (doc.metadata.source_url || doc.metadata.signed_url) : null;
                const safeDownloadAttr = downloadUrl ? escapeAttr(downloadUrl) : '';
                const cardClasses = downloadUrl ? 'document-card document-card-clickable' : 'document-card';
                const dataDownloadAttr = downloadUrl ? ` data-download-url="${safeDownloadAttr}"` : '';
                
                html += `
                    <div class="${cardClasses}"${dataDownloadAttr}>
                        <div class="document-header">
                            <div class="document-icon">
                                <i class="ti ti-file-earmark-pdf"></i>
                            </div>
                            <div class="document-info">
                                <div class="document-name">${doc.name}</div>
                                <div class="document-meta">
                                    ${statusIcon}
                                    <span class="status-text">${doc.status}</span>
                                    ${doc.created_at ? `• ${new Date(doc.created_at).toLocaleDateString('ru')}` : ''}
                                </div>
                            </div>
                        </div>
                        <div class="document-actions">
                            <button class="btn btn-sm btn-outline-danger" 
                                    onclick="deleteKnowledgeBaseDocument('${flowId}', '${doc.document_id}', event)"
                                    title="Удалить">
                                <i class="ti ti-trash"></i>
                            </button>
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
            listContainer.innerHTML = html;
            
            listContainer.querySelectorAll('.document-card-clickable').forEach(card => {
                card.addEventListener('click', (e) => {
                    const url = card.dataset.downloadUrl;
                    if (!url) {
                        return;
                    }
                    const withinActions = e.target.closest('.document-actions');
                    if (withinActions) {
                        return;
                    }
                    window.open(url, '_blank', 'noopener');
                });
            });
            
        } catch (error) {
            console.error('Ошибка загрузки документов:', error);
            listContainer.innerHTML = `
                <div class="error-state">
                    <i class="ti ti-exclamation-triangle"></i>
                    <p>Не удалось загрузить документы</p>
                </div>
            `;
        }
    }
    
    async deleteDocument(flowId, documentId, event) {
        if (event) {
            event.stopPropagation();
        }
        if (!confirm('Удалить этот документ из базы знаний?')) {
            return;
        }
        
        try {
            const response = await fetch(`/agents/api/v1/knowledge-base/flows/${flowId}/documents/${documentId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                throw new Error('Ошибка удаления документа');
            }
            
            showNotification('Документ удален из базы знаний', 'success');
            await this.loadDocuments(flowId);
            
        } catch (error) {
            console.error('Ошибка удаления документа:', error);
            showNotification('Не удалось удалить документ: ' + error.message, 'danger');
        }
    }
    
    async addSearchToolToAgent(flowId) {
        try {
            const storage = await (await fetch('/frontend/api/flows/' + encodeURIComponent(flowId))).json();
            const entryPoint = storage.entry_point_agent;
            
            if (!entryPoint) return;
            
            const agentResponse = await fetch(`/frontend/api/agents/${encodeURIComponent(entryPoint)}`);
            if (!agentResponse.ok) return;
            
            const agentData = await agentResponse.json();
            const currentTools = agentData.tools || [];
            
            const searchToolId = 'app.tools.misc.rag_tools.search_knowledge_base';
            const listToolId = 'app.tools.misc.rag_tools.list_documents_in_knowledge_base';
            
            const hasSearchTool = currentTools.some(t => t.tool_id === searchToolId);
            const hasListTool = currentTools.some(t => t.tool_id === listToolId);
            
            if (hasSearchTool && hasListTool) return;
            
            const toolsToAdd = [];
            
            if (!hasSearchTool) {
                toolsToAdd.push({
                    tool_id: searchToolId,
                    params: {},
                    code_mode: "code_reference",
                    is_public: true
                });
            }
            
            if (!hasListTool) {
                toolsToAdd.push({
                    tool_id: listToolId,
                    params: {},
                    code_mode: "code_reference",
                    is_public: true
                });
            }
            
            if (toolsToAdd.length === 0) return;
            
            const updatedTools = [...currentTools, ...toolsToAdd];
            
            await fetch(`/frontend/api/agents/${encodeURIComponent(entryPoint)}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.authToken}`
                },
                body: JSON.stringify({
                    tools: updatedTools
                })
            });
            
            const toolsSelector = document.getElementById('bot-tools-selector');
            if (toolsSelector) {
                toolsSelector.dataset.loaded = '';
            }
            
        } catch (error) {
            console.error('Ошибка автодобавления тула поиска:', error);
        }
    }
}

