/**
 * Базовый HTTP клиент для API запросов
 */

import { getCookie } from '/static/js/utils/cookies.js';

class APIClient {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
        this.authToken = null;
        this.defaultHeaders = {
            'Content-Type': 'application/json'
        };
    }
    
    setAuthToken(token) {
        this.authToken = token;
    }
    
    getAuthToken() {
        if (this.authToken) return this.authToken;
        return getCookie('auth_token') || localStorage.getItem('authToken');
    }
    
    getHeaders(customHeaders = {}) {
        const headers = { ...this.defaultHeaders, ...customHeaders };
        
        const token = this.getAuthToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        
        return headers;
    }
    
    async request(url, options = {}) {
        const fullUrl = this.baseURL + url;
        
        const config = {
            ...options,
            headers: this.getHeaders(options.headers)
        };
        
        try {
            const response = await fetch(fullUrl, config);
            
            if (response.status === 401) {
                this.handleUnauthorized();
                throw new Error('Unauthorized');
            }
            
            if (!response.ok) {
                const error = await this.parseError(response);
                throw error;
            }
            
            return await this.parseResponse(response);
            
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }
    
    async parseResponse(response) {
        const contentType = response.headers.get('content-type');
        
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        }
        
        return await response.text();
    }
    
    async parseError(response) {
        try {
            const errorData = await response.json();
            return new Error(errorData.detail || errorData.message || `HTTP ${response.status}`);
        } catch (e) {
            return new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
    }
    
    handleUnauthorized() {
        localStorage.removeItem('authToken');
        document.cookie = 'auth_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        
        if (window.location.pathname !== '/frontend/auth') {
            window.location.href = '/frontend/auth';
        }
    }
    
    async get(url, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;
        
        return this.request(fullUrl, {
            method: 'GET'
        });
    }
    
    async post(url, data = null) {
        return this.request(url, {
            method: 'POST',
            body: data ? JSON.stringify(data) : null
        });
    }
    
    async put(url, data = null) {
        return this.request(url, {
            method: 'PUT',
            body: data ? JSON.stringify(data) : null
        });
    }
    
    async delete(url) {
        return this.request(url, {
            method: 'DELETE'
        });
    }
    
    async upload(url, formData) {
        return this.request(url, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.getAuthToken()}`
            },
            body: formData
        });
    }
}

const apiClient = new APIClient();

export default apiClient;
export { APIClient };

