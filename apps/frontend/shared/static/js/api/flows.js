/**
 * API для работы с flows
 */

import apiClient from '/static/js/api/client.js';

export async function getFlows() {
    return apiClient.get('/frontend/api/flows/');
}

export async function getFlow(flowId) {
    return apiClient.get(`/frontend/api/flows/${encodeURIComponent(flowId)}`);
}

export async function getFlowInfo(flowId) {
    return apiClient.get(`/agents/api/v1/flows/${encodeURIComponent(flowId)}/info`);
}

export async function getFlowCanvas(flowId) {
    return apiClient.get(`/frontend/api/flows/${encodeURIComponent(flowId)}/canvas`);
}

export async function createFlow(flowData) {
    return apiClient.post('/frontend/api/flows/', flowData);
}

export async function updateFlow(flowId, flowData) {
    return apiClient.put(`/frontend/api/flows/${encodeURIComponent(flowId)}`, flowData);
}

export async function updateFlowCanvas(flowId, canvasData) {
    return apiClient.put(`/frontend/api/flows/${encodeURIComponent(flowId)}/canvas`, canvasData);
}

export async function deleteFlow(flowId) {
    return apiClient.delete(`/frontend/api/flows/${encodeURIComponent(flowId)}`);
}

export async function remigrateFlow(flowId) {
    return apiClient.post(`/frontend/api/admin/remigrate-flow-with-deps/${flowId}`);
}

