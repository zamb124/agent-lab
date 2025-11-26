/**
 * API для работы с файлами
 */

import apiClient from '/static/js/api/client.js';

export async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    return apiClient.upload('/frontend/api/admin/upload', formData);
}

export async function getFileInfo(fileId) {
    return apiClient.get(`/agents/api/v1/files/info/${fileId}`);
}

export function getFileDownloadUrl(fileId) {
    return `/agents/api/v1/files/download/${fileId}`;
}

export async function deleteFile(fileId) {
    return apiClient.delete(`/agents/api/v1/files/${fileId}`);
}

