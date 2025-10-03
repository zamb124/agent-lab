/**
 * JavaScript для модуля биллинга
 */

function openPaymentModal() {
    const modal = document.getElementById('payment-modal');
    if (modal) {
        modal.classList.add('active');
    }
}

function closePaymentModal() {
    const modal = document.getElementById('payment-modal');
    if (modal) {
        modal.classList.remove('active');
    }
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

