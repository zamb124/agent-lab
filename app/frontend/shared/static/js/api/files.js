/**
 * API для работы с файлами
 */

import apiClient from '/static/js/api/client.js';

export async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    return apiClient.upload('/api/v1/admin/upload', formData);
}

export async function getFileInfo(fileId) {
    return apiClient.get(`/api/v1/files/info/${fileId}`);
}

export function getFileDownloadUrl(fileId) {
    return `/api/v1/files/download/${fileId}`;
}

export async function deleteFile(fileId) {
    return apiClient.delete(`/api/v1/files/${fileId}`);
}

