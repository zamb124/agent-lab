/**
 * JavaScript для модуля биллинга
 */

function openPaymentModal() {
    const modal = document.getElementById('payment-modal');
    if (modal) {
        modal.classList.add('active');
        document.getElementById('payment-amount').value = '1000';
    }
}

function closePaymentModal() {
    const modal = document.getElementById('payment-modal');
    if (modal) {
        modal.classList.remove('active');
    }
}

async function createPayment() {
    const amountInput = document.getElementById('payment-amount');
    const providerSelect = document.getElementById('payment-provider');
    const submitBtn = document.getElementById('payment-submit-btn');
    
    const amount = parseFloat(amountInput.value);
    
    if (!amount || amount < 100) {
        showNotification('Минимальная сумма пополнения: 100₽', 'error');
        return;
    }
    
    if (amount > 1000000) {
        showNotification('Максимальная сумма пополнения: 1,000,000₽', 'error');
        return;
    }
    
    const provider = providerSelect ? providerSelect.value : null;
    
    submitBtn.disabled = true;
    submitBtn.textContent = 'Создание платежа...';
    
    try {
        const response = await fetch('/api/v1/payments/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                amount: amount,
                provider: provider
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка создания платежа');
        }
        
        const data = await response.json();
        
        showNotification('Переход к оплате...', 'info');
        
        setTimeout(() => {
            window.location.href = data.payment_url;
        }, 500);
        
    } catch (error) {
        console.error('Ошибка создания платежа:', error);
        showNotification(`Ошибка: ${error.message}`, 'error');
        
        submitBtn.disabled = false;
        submitBtn.textContent = 'Перейти к оплате';
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    notification.style.position = 'fixed';
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.padding = '1rem 1.5rem';
    notification.style.borderRadius = '8px';
    notification.style.backgroundColor = type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#3b82f6';
    notification.style.color = '#ffffff';
    notification.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';
    notification.style.zIndex = '10000';
    notification.style.animation = 'slideIn 0.3s ease-out';
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Закрытие модального окна при клике вне его
document.addEventListener('click', (e) => {
    const modal = document.getElementById('payment-modal');
    if (modal && e.target === modal) {
        closePaymentModal();
    }
});

// Закрытие модального окна по Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closePaymentModal();
    }
});

// Автообновление статистики (каждые 30 секунд)
let statsRefreshInterval;

function startStatsRefresh() {
    statsRefreshInterval = setInterval(async () => {
        try {
            const response = await fetch('/frontend/billing/api/stats');
            if (response.ok) {
                const data = await response.json();
                updateStatsDisplay(data);
            }
        } catch (error) {
            console.error('Ошибка при обновлении статистики:', error);
        }
    }, 30000);
}

function stopStatsRefresh() {
    if (statsRefreshInterval) {
        clearInterval(statsRefreshInterval);
    }
}

function updateStatsDisplay(data) {
    // Обновление потраченной суммы
    const budgetSpent = document.querySelector('.budget-spent');
    if (budgetSpent && data.current_month_spent !== undefined) {
        budgetSpent.textContent = `${data.current_month_spent.toFixed(2)} ₽`;
    }

    // Обновление прогресс-бара
    if (data.monthly_budget > 0) {
        const progressFill = document.querySelector('.progress-fill');
        const progressLabel = document.querySelector('.progress-label');
        const percent = Math.min(100, (data.current_month_spent / data.monthly_budget) * 100);
        
        if (progressFill) {
            progressFill.style.width = `${percent}%`;
        }
        
        if (progressLabel) {
            progressLabel.textContent = `${percent.toFixed(1)}% использовано`;
        }
    }

    // Обновление общей статистики
    if (data.stats) {
        const totalCalls = document.querySelector('.stat-card:nth-child(1) .stat-value');
        const totalCost = document.querySelector('.stat-card:nth-child(2) .stat-value');
        
        if (totalCalls && data.stats.total_calls !== undefined) {
            totalCalls.textContent = data.stats.total_calls;
        }
        
        if (totalCost && data.stats.total_cost !== undefined) {
            totalCost.textContent = `${data.stats.total_cost.toFixed(2)} ₽`;
        }
    }
}

// Запуск автообновления при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    startStatsRefresh();
});

// Остановка при уходе со страницы
window.addEventListener('beforeunload', () => {
    stopStatsRefresh();
});

