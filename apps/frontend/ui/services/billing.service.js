/**
 * Billing Service - API для биллинга
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class BillingService extends BaseService {
    /**
     * Получить информацию о подписке
     */
    async getSubscription() {
        return this.get('/api/billing/subscription');
    }
    
    /**
     * Получить статистику использования
     */
    async getUsageStats() {
        return this.get('/api/billing/usage');
    }
    
    /**
     * Пополнить баланс
     */
    async topUp(amount, paymentMethod = 'card') {
        return this.post('/api/billing/topup', { 
            amount, 
            payment_method: paymentMethod 
        });
    }
    
    /**
     * Сменить тарифный план
     */
    async changePlan(plan) {
        return this.patch('/api/billing/plan', { plan });
    }
    
    /**
     * Получить историю платежей
     */
    async getPaymentHistory() {
        return this.get('/api/billing/history');
    }
}


