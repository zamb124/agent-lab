/**
 * API Keys Service - API для управления API ключами
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class ApiKeysService extends BaseService {
    /**
     * Получить список API ключей
     */
    async listKeys() {
        return super.list('/api/api-keys');
    }
    
    /**
     * Создать новый API ключ
     */
    async create(name, scopes) {
        return this.post('/api/api-keys', { name, scopes });
    }
    
    /**
     * Переименовать API ключ
     */
    async update(keyId, name) {
        return this.patch(`/api/api-keys/${keyId}`, { name });
    }
    
    /**
     * Отозвать API ключ
     */
    async revoke(keyId) {
        return this.delete(`/api/api-keys/${keyId}`);
    }
}

