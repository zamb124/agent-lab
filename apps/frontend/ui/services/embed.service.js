/**
 * Embed Service - API для управления встраиваемыми виджетами
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class EmbedService extends BaseService {
    /**
     * Получить список конфигураций виджетов
     */
    async list() {
        return this.get('/api/embed/configs');
    }
    
    /**
     * Создать новую конфигурацию виджета
     */
    async create(data) {
        return this.post('/api/embed/configs', data);
    }
    
    /**
     * Обновить конфигурацию виджета
     */
    async update(embedId, data) {
        return this.put(`/api/embed/configs/${embedId}`, data);
    }
    
    /**
     * Удалить конфигурацию виджета
     */
    async deleteConfig(embedId) {
        return this.delete(`/api/embed/configs/${embedId}`);
    }
    
    /**
     * Получить код для встраивания
     */
    async getCode(embedId) {
        return this.get(`/api/embed/configs/${embedId}/code`);
    }
}

