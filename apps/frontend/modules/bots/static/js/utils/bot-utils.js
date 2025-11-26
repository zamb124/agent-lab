/**
 * Bot Utilities
 */

export async function copyToClipboard(elementIdOrText, app) {
    try {
        let textToCopy = elementIdOrText;
        const element = document.getElementById(elementIdOrText);
        if (element) {
            textToCopy = element.value || element.textContent || element.innerText;
        }
        
        await navigator.clipboard.writeText(textToCopy);
        if (app) {
            app.showNotification('Скопировано в буфер обмена', 'success');
        }
    } catch (err) {
        console.error('Ошибка копирования:', err);
        if (app) {
            app.showNotification('Не удалось скопировать текст', 'danger');
        }
    }
}

export function togglePlatformCollapse(platformName) {
    const platformCard = document.querySelector(`.platform-settings[data-platform="${platformName}"]`);
    if (!platformCard) {
        console.error(`Platform card not found: ${platformName}`);
        return;
    }
    
    const content = platformCard.querySelector('.platform-content');
    const collapseBtn = platformCard.querySelector('.platform-collapse-btn i');
    
    if (!content || !collapseBtn) {
        console.error('Platform content or collapse button not found');
        return;
    }
    
    const isCollapsed = platformCard.classList.contains('collapsed');
    
    if (isCollapsed) {
        platformCard.classList.remove('collapsed');
        content.style.maxHeight = content.scrollHeight + 'px';
        collapseBtn.style.transform = 'rotate(0deg)';
        
        setTimeout(() => {
            content.style.maxHeight = 'none';
        }, 300);
    } else {
        content.style.maxHeight = content.scrollHeight + 'px';
        
        requestAnimationFrame(() => {
            content.style.maxHeight = '0';
            collapseBtn.style.transform = 'rotate(-90deg)';
        });
        
        platformCard.classList.add('collapsed');
    }
}

export async function testApiEndpoint(flowId, authToken) {
    const { showNotification } = await import('/static/js/components/notification.js');
    
    const userIdInput = document.getElementById(`api-test-user-id-${flowId}`);
    const sessionIdInput = document.getElementById(`api-test-session-id-${flowId}`);
    const messageInput = document.getElementById(`api-test-message-${flowId}`);
    const resultContainer = document.getElementById(`api-test-result-${flowId}`);
    const resultContent = document.getElementById(`api-test-result-content-${flowId}`);
    
    if (!userIdInput || !messageInput || !resultContainer || !resultContent) {
        console.error('Не найдены элементы формы для тестирования API');
        showNotification('Ошибка: элементы формы не найдены', 'danger');
        return;
    }
    
    const userId = userIdInput.value.trim();
    const sessionId = sessionIdInput ? sessionIdInput.value.trim() : '';
    const message = messageInput.value.trim();
    
    if (!userId) {
        showNotification('Введите User ID', 'warning');
        userIdInput.focus();
        return;
    }
    
    if (!message) {
        showNotification('Введите сообщение', 'warning');
        messageInput.focus();
        return;
    }
    
    const requestBody = {
        user_id: userId,
        message: message
    };
    
    if (sessionId) {
        requestBody.session_id = sessionId;
    }
    
    resultContainer.style.display = 'block';
    resultContent.textContent = 'Отправка запроса...';
    resultContent.className = '';
    
    try {
        const response = await fetch(`/api/v1/flows/${flowId}/message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify(requestBody)
        });
        
        const responseData = await response.json();
        
        if (response.ok) {
            resultContent.textContent = JSON.stringify(responseData, null, 2);
            resultContent.className = 'success';
            showNotification('Запрос успешно выполнен', 'success');
        } else {
            resultContent.textContent = JSON.stringify(responseData, null, 2);
            resultContent.className = 'error';
            showNotification('Ошибка выполнения запроса', 'danger');
        }
        
    } catch (error) {
        console.error('Ошибка тестирования API:', error);
        resultContent.textContent = `Ошибка: ${error.message}\n\nПодробности:\n${error.stack || 'Нет дополнительной информации'}`;
        resultContent.className = 'error';
        showNotification('Ошибка при отправке запроса: ' + error.message, 'danger');
    }
}

