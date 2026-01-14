/**
 * Settings Service - API для настроек
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class SettingsService extends BaseService {
    /**
     * Получить настройки компании
     */
    async getCompanySettings() {
        return this.get('/api/settings/company');
    }
    
    /**
     * Обновить настройки компании
     */
    async updateCompanySettings(settings) {
        return this.patch('/api/settings/company', settings);
    }
    
    /**
     * Получить настройки безопасности
     */
    async getSecuritySettings() {
        return this.get('/api/settings/security');
    }
    
    /**
     * Получить список OAuth провайдеров
     */
    async getOAuthProviders() {
        return this.get('/api/settings/oauth-providers');
    }
    
    /**
     * Получить настройки интеграций
     */
    async getIntegrations() {
        return this.get('/api/settings/integrations');
    }
}


