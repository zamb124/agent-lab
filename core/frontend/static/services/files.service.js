import { BaseService } from '../lib/services/BaseService.js';

export class FilesService extends BaseService {
    async uploadFile(file) {
        if (!(file instanceof File)) {
            throw new Error('uploadFile expects browser File');
        }
        const formData = new FormData();
        formData.append('file', file);
        return this.post('/api/v1/files/', formData);
    }

    async getFile(fileId) {
        if (typeof fileId !== 'string' || fileId === '') {
            throw new Error('fileId is required');
        }
        return this.get(`/api/v1/files/${encodeURIComponent(fileId)}`);
    }

    buildDownloadUrl(fileId) {
        if (typeof fileId !== 'string' || fileId === '') {
            throw new Error('fileId is required');
        }
        return `${this.baseUrl}/api/v1/files/download/${encodeURIComponent(fileId)}`;
    }
}
