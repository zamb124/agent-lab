/**
 * API для работы с tools
 */

import apiClient from '/static/js/api/client.js';

export async function getTools() {
    return apiClient.get('/frontend/api/tools/');
}

export async function getTool(toolId) {
    return apiClient.get(`/frontend/api/tools/${encodeURIComponent(toolId)}`);
}

export async function createTool(toolData) {
    return apiClient.post('/frontend/api/tools/', toolData);
}

export async function updateTool(toolId, toolData) {
    return apiClient.put(`/frontend/api/tools/${encodeURIComponent(toolId)}`, toolData);
}

export async function deleteTool(toolId) {
    return apiClient.delete(`/frontend/api/tools/${encodeURIComponent(toolId)}`);
}

