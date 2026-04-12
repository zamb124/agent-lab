/**
 * Каталог flows с сервиса flows (тот же origin, /flows/api/v1).
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class FlowsCatalogService extends BaseService {
    constructor() {
        super('');
    }

    /**
     * Список flows компании (как в flows UI).
     */
    async listFlows() {
        const data = await this.get('/flows/api/v1/flows/');
        return data.items;
    }

    async listTools() {
        const data = await this.get('/flows/api/v1/tools/');
        return data.items;
    }
}
