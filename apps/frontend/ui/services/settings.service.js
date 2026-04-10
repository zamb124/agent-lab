/**
 * Settings Service - API для настроек
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class SettingsService extends BaseService {
    async getCompanySettings() {
        return this.get('/api/settings/company');
    }

    async updateCompanySettings(settings) {
        return this.patch('/api/settings/company', settings);
    }
}
