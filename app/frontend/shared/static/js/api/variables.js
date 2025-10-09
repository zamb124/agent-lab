/**
 * API для работы с переменными
 */

import apiClient from '/static/js/api/client.js';

export async function getVariables() {
    return apiClient.get('/api/v1/admin/variables');
}

export async function getFlowVariables(flowId) {
    return apiClient.get(`/frontend/api/variables/flow/${encodeURIComponent(flowId)}`);
}

export async function createVariable(key, value, options = {}) {
    return apiClient.post('/api/v1/admin/variables', {
        key,
        value,
        ...options
    });
}

export async function updateVariable(key, value, options = {}) {
    return apiClient.put(`/api/v1/admin/variables/${key}`, {
        value,
        ...options
    });
}

export async function deleteVariable(key) {
    return apiClient.delete(`/api/v1/admin/variables/${key}`);
}

