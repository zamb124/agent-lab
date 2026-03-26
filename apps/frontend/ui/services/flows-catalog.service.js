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
        return this.get('/flows/api/v1/flows/');
    }
}
