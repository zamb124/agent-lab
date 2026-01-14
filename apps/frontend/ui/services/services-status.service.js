/**
 * Services Status Service - API для проверки статуса микросервисов
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class ServicesStatusService extends BaseService {
    /**
     * Получить статус всех микросервисов
     */
    async getStatus() {
        return this.get('/api/services/status');
    }
}


