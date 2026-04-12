/**
 * Billing Service - API для биллинга
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class BillingService extends BaseService {
    async getSubscription() {
        return this.get('/api/billing/subscription');
    }

    async getUsageStats() {
        return this.get('/api/billing/usage');
    }

    async changePlan(plan) {
        return this.patch('/api/billing/plan', { plan });
    }

    async topup(amount) {
        return this.post('/api/billing/topup', { amount });
    }

    async getHistory() {
        return this.get('/api/billing/history');
    }
}
