/**
 * Store модуль - установка и удаление flows
 */

import { showNotification } from '/static/js/components/notification.js';
import { renderMarkdown } from '/static/js/utils/markdown.js';

(function() {
    'use strict';
    
    function initializeStoreDescriptions() {
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
    
    document.body.addEventListener('htmx:afterSettle', (event) => {
        if (event.target.id === 'store-list-view') {
            initializeStoreDescriptions();
        }
    });
    
    window.openFlowDetails = async function(flowId) {
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
        
        modalDetails.innerHTML = '<div class="loading-indicator"><div class="spinner"></div><span>Загрузка...</span></div>';
        modal.style.display = 'flex';
        if (listView) listView.style.display = 'none';
        
        try {
            const response = await fetch(`/frontend/store/${flowId}/details`);
            const html = await response.text();
            
            modalDetails.innerHTML = html;
            
            // Парсим description как Markdown
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
    };
    
    window.closeFlowModal = function() {
        const modal = document.getElementById('flow-details-modal');
        const listView = document.getElementById('store-list-view');
        
        modal.style.display = 'none';
        if (listView) listView.style.display = 'block';
    };
    
    window.togglePassword = function(inputId) {
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
    };

    window.installFlow = async function(flowId) {
        // Собираем переменные из формы
        const variablesForm = document.getElementById('variables-form');

        let variables = null;

        if (variablesForm) {
            variables = {};
            const inputs = variablesForm.querySelectorAll('input[name]');
            let hasEmptyRequired = false;

            inputs.forEach(input => {
                const value = input.value.trim();
                const isRequired = input.hasAttribute('required');

                // Собираем все переменные, включая пустые
                variables[input.name] = value;

                // Проверяем обязательные поля
                if (isRequired && !value) {
                    hasEmptyRequired = true;
                    input.style.borderColor = 'var(--error-color)';
                } else {
                    input.style.borderColor = '';
                }
            });

            // Если есть пустые обязательные поля, показываем ошибку
            if (hasEmptyRequired) {
                showNotification('Заполните все обязательные поля', 'danger');
                // Прокручиваем к форме в sidebar
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

        const response = await fetch(`/frontend/api/flows/${flowId}/install`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${window.app.authToken}`
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

        closeFlowModal();

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
    };
    
    window.uninstallFlow = async function(flowId) {
        if (!confirm('Удалить этот flow? Это действие необратимо.')) {
            return;
        }
        
        showNotification('Удаление flow...', 'info');
        
        const response = await fetch(`/frontend/api/flows/${flowId}/uninstall`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${window.app.authToken}`
            }
        });
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            showNotification('Ошибка удаления: ' + (error.detail || `HTTP ${response.status}`), 'danger');
            return;
        }
        
        const result = await response.json();
        showNotification(result.message || 'Flow успешно удалён', 'success');
        
        closeFlowModal();
        
        htmx.ajax('GET', '/frontend/store/list', {
            target: '#store-list-view',
            swap: 'innerHTML'
        });
    };
    
    document.addEventListener('click', (e) => {
        if (e.target.id === 'flow-details-modal') {
            closeFlowModal();
        }
    });
    
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const modal = document.getElementById('flow-details-modal');
            if (modal && modal.style.display === 'flex') {
                closeFlowModal();
            }
        }
    });
    
})();

