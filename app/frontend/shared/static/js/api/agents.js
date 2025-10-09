/**
 * API для работы с agents
 */

import apiClient from '/static/js/api/client.js';

export async function getAgents() {
    return apiClient.get('/frontend/api/agents/');
}

export async function getAgent(agentId) {
    return apiClient.get(`/frontend/api/agents/${encodeURIComponent(agentId)}`);
}

export async function createAgent(agentData) {
    return apiClient.post('/frontend/api/agents/', agentData);
}

export async function updateAgent(agentId, agentData) {
    return apiClient.put(`/frontend/api/agents/${encodeURIComponent(agentId)}`, agentData);
}

export async function deleteAgent(agentId) {
    return apiClient.delete(`/frontend/api/agents/${encodeURIComponent(agentId)}`);
}

