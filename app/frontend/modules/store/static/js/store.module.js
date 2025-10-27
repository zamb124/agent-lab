/**
 * Store Module - Магазин готовых решений
 */

import { showNotification } from '/static/js/components/notification.js';
import { renderMarkdown } from '/static/js/utils/markdown.js';

export default class StoreModule {
    constructor(app) {
        this.app = app;
        this.name = 'store';
        this.version = '1.0.0';
    }
    
    async init() {
        console.log('🏪 Инициализация Store модуля');
        
        this.setupGlobalFunctions();
        this.setupEventListeners();
        
        return this;
    }
    
    setupGlobalFunctions() {
        window.openFlowDetails = (flowId) => this.openFlowDetails(flowId);
        window.closeFlowModal = () => this.closeFlowModal();
        window.togglePassword = (inputId) => this.togglePassword(inputId);
        window.installFlow = (flowId) => this.installFlow(flowId);
        window.uninstallFlow = (flowId) => this.uninstallFlow(flowId);
    }
    
    setupEventListeners() {
        document.body.addEventListener('htmx:afterSettle', (event) => {
            if (event.target.id === 'store-list-view') {
                this.initializeStoreDescriptions();
            }
        });
        
        document.addEventListener('click', (e) => {
            if (e.target.id === 'flow-details-modal') {
                this.closeFlowModal();
            }
        });
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const modal = document.getElementById('flow-details-modal');
                if (modal && modal.style.display === 'flex') {
                    this.closeFlowModal();
                }
            }
        });
    }
    
    initializeStoreDescriptions() {
        const descriptions = document.querySelectorAll('.store-card-description[data-markdown]');
        if (descriptions.length === 0) return;
        
        descriptions.forEach(element => {
            const markdownText = element.getAttribute('data-markdown');
            if (markdownText && !element.dataset.processed) {
                element.innerHTML = renderMarkdown(markdownText);
                element.removeAttribute('data-markdown');
                element.dataset.processed = 'true';
            }
        });
    }
    
    async openFlowDetails(flowId) {
        const modal = document.getElementById('flow-details-modal');
        const modalDetails = document.getElementById('modal-flow-details');
        const listView = document.getElementById('store-list-view');
        
        if (!modal || !modalDetails) {
            console.error('Modal elements not found');
            showNotification('Ошибка: модальное окно не найдено', 'danger');
            return;
        }
        
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        
        modalDetails.innerHTML = `
            <div class="skeleton-modal" style="padding: 2rem;">
                <div class="skeleton skeleton-text skeleton-width-60" style="height: 2rem; margin-bottom: 1.5rem;"></div>
                <div class="skeleton skeleton-text" style="margin-bottom: 0.75rem;"></div>
                <div class="skeleton skeleton-text skeleton-width-90" style="margin-bottom: 0.75rem;"></div>
                <div class="skeleton skeleton-text skeleton-width-95" style="margin-bottom: 1.5rem;"></div>
                <div class="skeleton skeleton-text skeleton-width-85" style="margin-bottom: 0.75rem;"></div>
                <div class="skeleton skeleton-text skeleton-width-80" style="margin-bottom: 2rem;"></div>
                <div style="display: flex; gap: 1rem;">
                    <div class="skeleton skeleton-button" style="width: 150px;"></div>
                    <div class="skeleton skeleton-button" style="width: 120px;"></div>
                </div>
            </div>
        `;
        modal.style.display = 'flex';
        if (listView) listView.style.display = 'none';
        
        try {
            const response = await fetch(`/frontend/store/${flowId}/details`);
            const html = await response.text();
            
            modalDetails.innerHTML = html;
            
            const descriptionElement = document.getElementById('flow-description-content');
            if (descriptionElement) {
                const markdownText = descriptionElement.textContent;
                const htmlContent = renderMarkdown(markdownText);
                descriptionElement.innerHTML = htmlContent;
            }
        } catch (error) {
            console.error('Ошибка загрузки деталей flow:', error);
            modalDetails.innerHTML = '<div class="empty-state"><p>Ошибка загрузки деталей</p></div>';
        }
    }
    
    closeFlowModal() {
        const modal = document.getElementById('flow-details-modal');
        const listView = document.getElementById('store-list-view');
        
        modal.style.display = 'none';
        if (listView) listView.style.display = 'block';
    }
    
    togglePassword(inputId) {
        const input = document.getElementById(inputId);
        const button = input.parentElement.querySelector('.password-toggle');
        const icon = button.querySelector('i');

        if (input.type === 'password') {
            input.type = 'text';
            icon.className = 'bi bi-eye-slash';
            button.title = 'Скрыть пароль';
        } else {
            input.type = 'password';
            icon.className = 'bi bi-eye';
            button.title = 'Показать пароль';
        }
    }
    
    async installFlow(flowId) {
        const variablesForm = document.getElementById('variables-form');

        let variables = null;

        if (variablesForm) {
            variables = {};
            const inputs = variablesForm.querySelectorAll('input[name]');
            let hasEmptyRequired = false;

            inputs.forEach(input => {
                const value = input.value.trim();
                const isRequired = input.hasAttribute('required');

                variables[input.name] = value;

                if (isRequired && !value) {
                    hasEmptyRequired = true;
                    input.style.borderColor = 'var(--error-color)';
                } else {
                    input.style.borderColor = '';
                }
            });

            if (hasEmptyRequired) {
                showNotification('Заполните все обязательные поля', 'danger');
                variablesForm.scrollIntoView({ behavior: 'smooth', block: 'start' });
                return;
            }
        }

        const hasVariables = variablesForm && variables;

        const confirmMessage = hasVariables
            ? 'Установить этот flow? Будут созданы переменные и мигрированы flow, агенты и функции.'
            : 'Установить этот flow? Будут мигрированы flow, агенты и функции.';

        if (!confirm(confirmMessage)) {
            return;
        }

        showNotification('Установка flow...', 'info');

        const requestBody = { variables: variables };

        try {
            const response = await fetch(`/frontend/api/flows/${flowId}/install`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.app.authToken}`
                },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                showNotification('Ошибка установки: ' + (error.detail || `HTTP ${response.status}`), 'danger');
                return;
            }

            const result = await response.json();
            console.log('📦 Install result:', result);
            console.log('🔗 Additional URL:', result.additional_url);

            showNotification(result.message || 'Flow успешно установлен', 'success');

            this.closeFlowModal();

            if (result.additional_url) {
                console.log('🚀 Opening additional URL:', result.additional_url);
                window.open(result.additional_url, '_blank');
            } else {
                console.log('⚠️ No additional_url in result');
            }

            htmx.ajax('GET', '/frontend/bots/', {
                target: '#content',
                swap: 'innerHTML'
            });
        } catch (error) {
            console.error('Ошибка установки flow:', error);
            showNotification('Ошибка при установке flow: ' + error.message, 'danger');
        }
    }
    
    async uninstallFlow(flowId) {
        if (!confirm('Удалить этот flow? Это действие необратимо.')) {
            return;
        }
        
        showNotification('Удаление flow...', 'info');
        
        try {
            const response = await fetch(`/frontend/api/flows/${flowId}/uninstall`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                showNotification('Ошибка удаления: ' + (error.detail || `HTTP ${response.status}`), 'danger');
                return;
            }
            
            const result = await response.json();
            showNotification(result.message || 'Flow успешно удалён', 'success');
            
            this.closeFlowModal();
            
            htmx.ajax('GET', '/frontend/store/list', {
                target: '#store-list-view',
                swap: 'innerHTML'
            });
        } catch (error) {
            console.error('Ошибка удаления flow:', error);
            showNotification('Ошибка при удалении flow: ' + error.message, 'danger');
        }
    }
    
    destroy() {
        console.log('🧹 Store модуль выгружен');
    }
}
