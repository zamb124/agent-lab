/**
 * API для работы с переменными
 */

import apiClient from '/static/js/api/client.js';

export async function getVariables() {
    return apiClient.get('/frontend/api/variables/admin/variables');
}

export async function getFlowVariables(flowId) {
    return apiClient.get(`/frontend/api/variables/flow/${encodeURIComponent(flowId)}`);
}

export async function createVariable(key, value, options = {}) {
    return apiClient.post('/frontend/api/variables/admin/variables', {
        key,
        value,
        ...options
    });
}

export async function updateVariable(key, value, options = {}) {
    return apiClient.put(`/frontend/api/variables/admin/variables/${key}`, {
        value,
        ...options
    });
}

export async function deleteVariable(key) {
    return apiClient.delete(`/frontend/api/variables/admin/variables/${key}`);
}

