/**
 * Сервис авторизации
 * ВАЖНО: Токен хранится в httponly cookie, JS НЕ читает его напрямую!
 * Вся проверка авторизации идет через API /api/v1/auth/me
 */
import { BaseService } from '../lib/services/BaseService.js';
import { AppEvents } from '../lib/utils/types.js';

export class AuthService extends BaseService {
    constructor(baseUrl) {
        super(baseUrl);
        this.user = null;
        this._validationPromise = null;
        this._lastValidationTime = null;
        this._validationCacheTime = 5000;
    }

    /**
     * Проверить авторизацию пользователя через API
     * Бекенд читает httponly cookie и возвращает данные юзера
     * Результат кэшируется на короткое время, чтобы избежать множественных запросов
     */
    async validateToken() {
        const now = Date.now();
        
        if (this._validationPromise) {
            return this._validationPromise;
        }
        
        if (this._lastValidationTime && (now - this._lastValidationTime) < this._validationCacheTime) {
            return this.isAuthenticated;
        }
        
        this._validationPromise = this._doValidateToken();
        
        try {
            const result = await this._validationPromise;
            return result;
        } finally {
            this._validationPromise = null;
            this._lastValidationTime = now;
        }
    }
    
    async _doValidateToken() {
        console.log('🔍 validateToken: проверяем авторизацию через /api/auth/me');
        try {
            const userData = await this.get('/api/auth/me');
            
            console.log('✅ Пользователь авторизован:', userData);
            this.user = {
                id: userData.user_id,
                company_id: userData.company_id,
                roles: userData.roles || []
            };
            this._dispatchAuthChange();
            return true;
        } catch (error) {
            console.log('❌ Ошибка при проверке авторизации:', error.message);
            this.user = null;
            this._dispatchAuthChange();
            return false;
        }
    }

    get isAuthenticated() {
        return !!this.user;
    }

    clearAuth() {
        this.user = null;
        this._validationPromise = null;
        this._lastValidationTime = null;
        this._dispatchAuthChange();
    }

    async logout() {
        try {
            await this.post('/api/auth/logout');
        } catch (e) {
            console.error('Ошибка logout:', e);
        }
        this.clearAuth();
    }

    _dispatchAuthChange() {
        window.dispatchEvent(new CustomEvent(AppEvents.AUTH_CHANGE, {
            detail: {
                isAuthenticated: this.isAuthenticated,
                user: this.user,
            }
        }));
    }

    /**
     * Начать OAuth авторизацию через провайдера
     * @param {string} provider - yandex, google или github
     */
    async startOAuth(provider) {
        const response = await this.get(`/api/auth/login/${provider}`);
        
        if (response.auth_url) {
            return response.auth_url;
        }
        
        throw new Error('Не удалось получить ссылку авторизации');
    }

    /**
     * Получить список доступных провайдеров OAuth
     */
    async getAvailableProviders() {
        try {
            const response = await this.get('/auth/providers');
            return response.providers || ['yandex', 'google', 'github'];
        } catch (e) {
            return ['yandex', 'google', 'github'];
        }
    }

    /**
     * Получить service-specific атрибуты пользователя
     * @param {string} service - Имя сервиса (agents, crm, rag, frontend)
     */
    async getServiceAttrs(service) {
        if (!service) {
            throw new Error('Service name is required');
        }
        return this.get(`/api/auth/me/attrs/${service}`);
    }

    /**
     * Обновить service-specific атрибуты пользователя
     * @param {string} service - Имя сервиса
     * @param {Object} attrs - Атрибуты для обновления (merge с существующими)
     */
    async updateServiceAttrs(service, attrs) {
        if (!service) {
            throw new Error('Service name is required');
        }
        if (!attrs || typeof attrs !== 'object') {
            throw new Error('Attrs must be an object');
        }
        return this.put(`/api/auth/me/attrs/${service}`, attrs);
    }

    /**
     * Обновить профиль пользователя
     * @param {Object} updates - Данные для обновления (name, bio, ui_preferences и т.д.)
     */
    async updateProfile(updates) {
        if (!updates || typeof updates !== 'object') {
            throw new Error('Updates must be an object');
        }
        return this.put('/api/auth/me', updates);
    }

    /**
     * Переключить активную компанию
     * @param {string} companyId - ID компании для переключения
     */
    async switchCompany(companyId) {
        if (!companyId) {
            throw new Error('Company ID is required');
        }
        return this.post('/api/auth/switch-company', { company_id: companyId });
    }
}
