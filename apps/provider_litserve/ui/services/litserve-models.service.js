import { BaseService } from '@platform/lib/services/BaseService.js';

export class LitserveModelsService extends BaseService {
    constructor(baseUrl = '/litserve/api') {
        super(baseUrl);
    }

    async list() {
        return this.get('/models');
    }

    async add(payload) {
        return this.post('/models', payload);
    }

    async retry(modelId) {
        if (!modelId) {
            throw new Error('modelId is required');
        }
        return this.post(`/models/${encodeURIComponent(modelId)}/retry`);
    }

    async remove(modelId) {
        if (!modelId) {
            throw new Error('modelId is required');
        }
        return this.delete(`/models/${encodeURIComponent(modelId)}`);
    }
}
