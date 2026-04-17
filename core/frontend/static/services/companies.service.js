/**
 * Сервис для работы с компаниями
 */
import { BaseService } from '../lib/services/BaseService.js';

export class CompaniesService extends BaseService {
    /**
     * Получить список компаний текущего пользователя
     * @returns {Promise<Array>}
     */
    async getMyCompanies() {
        const response = await this.get('/api/companies/me');
        if (!response || typeof response !== 'object' || !Array.isArray(response.items)) {
            throw new Error('Некорректный ответ /api/companies/me: ожидался объект с массивом items');
        }
        return response.items;
    }
    
    /**
     * Проверить доступность slug для компании
     * @param {string} slug - slug для проверки
     * @returns {Promise<{available: boolean}>}
     */
    async checkSlugAvailability(slug) {
        return this.post('/api/companies/check-slug', { slug });
    }
    
    /**
     * Создать новую компанию
     * @param {string} name - название компании
     * @param {string} slug - slug компании
     * @returns {Promise<Object>}
     */
    async createCompany(name, slug) {
        return this.post('/api/companies', { name, slug });
    }
}

