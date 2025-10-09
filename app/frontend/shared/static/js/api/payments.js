/**
 * API для работы с платежами
 */

import apiClient from '/static/js/api/client.js';

export async function createPayment(amount, provider = null) {
    return apiClient.post('/api/v1/payments/create', {
        amount,
        provider
    });
}

export async function getBillingStats() {
    return apiClient.get('/frontend/billing/api/stats');
}

export async function getPaymentHistory(limit = 50) {
    return apiClient.get('/api/v1/payments/history', { limit });
}

