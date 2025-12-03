/**
 * Knowledge Base Uploader
 */

import { showNotification } from '/static/js/components/notification.js';

export class KnowledgeBaseUploader {
    constructor(kbManager) {
        this.kbManager = kbManager;
        this._setupWebSocketListener();
    }
    
    _setupWebSocketListener() {
        window.addEventListener('rag-documents-updated', (event) => {
            const { flow_id } = event.detail;
            if (window.currentFlowId === flow_id) {
                this.kbManager.loadDocuments(flow_id);
            }
        });
    }
    
    openTextModal() {
        const modal = document.getElementById('upload-text-modal');
        if (modal) {
            if (modal.parentElement !== document.body) {
                document.body.appendChild(modal);
            }
            modal.style.display = 'flex';
        }
        document.body.style.overflow = 'hidden';

        document.getElementById('upload-text-document-name').value = '';
        document.getElementById('upload-text-content').value = '';
        document.getElementById('upload-text-description').value = '';

        setTimeout(() => {
            document.getElementById('upload-text-content').focus();
        }, 100);
    }
    
    closeTextModal() {
        const modal = document.getElementById('upload-text-modal');
        if (modal) {
            modal.style.display = 'none';
        }
        document.body.style.overflow = 'auto';

        document.getElementById('upload-text-document-name').value = '';
        document.getElementById('upload-text-content').value = '';
        document.getElementById('upload-text-description').value = '';
    }
    
    async uploadText(flowId) {
        const textContent = document.getElementById('upload-text-content').value.trim();
        const documentName = document.getElementById('upload-text-document-name').value.trim();
        const description = document.getElementById('upload-text-description').value.trim();

        if (!textContent) {
            showNotification('Пожалуйста, введите текст для загрузки', 'warning');
            document.getElementById('upload-text-content').focus();
            return;
        }

        if (textContent.length > 50000) {
            showNotification('Текст слишком длинный. Максимальная длина: 50,000 символов', 'warning');
            return;
        }

        try {
            showNotification('Загрузка текста...', 'info');

            const response = await fetch(`/frontend/api/knowledge-base/flows/${flowId}/text`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: textContent,
                    document_name: documentName || undefined,
                    description: description || undefined
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Ошибка загрузки текста');
            }

            const result = await response.json();
            showNotification('Текст успешно загружен и добавлен в базу знаний', 'success');

            this.closeTextModal();

            await this.kbManager.addSearchToolToAgent(flowId);
            await this.kbManager.loadDocuments(flowId);

        } catch (error) {
            console.error('Ошибка загрузки текста:', error);
            showNotification('Не удалось загрузить текст: ' + error.message, 'danger');
        }
    }
    
    async uploadDocument(flowId) {
        if (flowId === 'new') {
            showNotification('Сначала сохраните бота, затем загрузите документы', 'warning');
            
            const saveButton = document.querySelector('.settings-actions .btn-primary');
            if (saveButton) {
                saveButton.classList.add('pulse-animation');
                setTimeout(() => saveButton.classList.remove('pulse-animation'), 2000);
            }
            return;
        }
        
        window.currentFlowId = flowId;
        
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.pdf,.txt,.docx,.html,.md,.csv';
        
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                showNotification('Загрузка документа...', 'info');
                
                const response = await fetch(`/frontend/api/knowledge-base/flows/${flowId}/documents`, {
                    method: 'POST',
                    body: formData
                });
                
                if (!response.ok) {
                    throw new Error('Ошибка загрузки документа');
                }
                
                const result = await response.json();
                showNotification('Документ загружен и обрабатывается. Вы получите уведомление когда он будет готов.', 'info');
                
                await this.kbManager.addSearchToolToAgent(flowId);
                
            } catch (error) {
                console.error('Ошибка загрузки документа:', error);
                showNotification('Не удалось загрузить документ: ' + error.message, 'danger');
            }
        };
        
        input.click();
    }
}

