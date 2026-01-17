/**
 * A2AService - Сервис для работы с Agents API
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class A2AService extends BaseService {
    constructor(baseUrl) {
        super(baseUrl);
    }

    async getAgents() {
        return this.get('/api/v1/agents/');
    }

    async getAgent(agentId) {
        return this.getAgentConfig(agentId);
    }

    async getAgentConfig(agentId) {
        return this.get(`/api/v1/agents/${agentId}`);
    }

    async createAgent(config) {
        return this.post('/api/v1/agents/', config);
    }

    async updateAgent(agentId, config) {
        return this.put(`/api/v1/agents/${agentId}`, config);
    }

    async saveAgentConfig(agentId, config) {
        return this.updateAgent(agentId, config);
    }

    async deleteAgent(agentId) {
        return this.delete(`/api/v1/agents/${agentId}`);
    }

    async sendMessage(agentId, message, context = {}) {
        return this.post(`/api/v1/agents/${agentId}/chat`, {
            message,
            context
        });
    }

    async getChatHistory(sessionId) {
        return this.get(`/api/v1/chat/history/${sessionId}`);
    }

    async getSessions(agentId = null, options = {}) {
        const params = new URLSearchParams();
        if (agentId) params.append('agent_id', agentId);
        if (options.limit) params.append('limit', options.limit);
        if (options.offset) params.append('offset', options.offset);
        const query = params.toString();
        const response = await this.get(`/api/v1/sessions/${query ? '?' + query : ''}`);
        return response.sessions || [];
    }

    async deleteSession(agentId, sessionId) {
        return this.delete(`/api/v1/sessions/${sessionId}`);
    }

    async getSessionState(sessionId) {
        return this.get(`/api/v1/tasks/state?session_id=${encodeURIComponent(sessionId)}`);
    }

    async getSkills() {
        return this.get('/api/v1/skills');
    }

    async getTools() {
        return this.get('/api/v1/tools');
    }

    // Resources API
    async getResources(type = null) {
        const url = type 
            ? `/api/v1/resources/?type=${type}`
            : '/api/v1/resources/';
        return this.get(url);
    }

    async getResource(resourceId) {
        return this.get(`/api/v1/resources/${resourceId}`);
    }

    async createResource(config) {
        return this.post('/api/v1/resources/', config);
    }

    async updateResource(resourceId, config) {
        return this.put(`/api/v1/resources/${resourceId}`, config);
    }

    async deleteResource(resourceId) {
        return this.delete(`/api/v1/resources/${resourceId}`);
    }

    async getAvailableModels(provider = null) {
        const url = provider 
            ? `/api/v1/registry/models/values?provider=${provider}`
            : '/api/v1/registry/models/values';
        return this.get(url);
    }

    async validateNode(nodeType, nodeConfig, state, agentId, skillId) {
        // TODO: Implement backend /api/v1/nodes/validate endpoint
        // For now, return success stub
        console.warn('[A2AService] validateNode: Backend endpoint not implemented, returning success stub');
        return { valid: true, success: true };
    }

    async generatePromptAI(prompt, context = {}) {
        // TODO: Implement backend /api/v1/prompts/enhance or similar endpoint
        // For now, just return the original prompt
        console.warn('[A2AService] generatePromptAI: Backend endpoint not implemented, returning original prompt');
        return prompt;
    }

    async executeNode(nodeType, nodeConfig, state, agentId, skillId) {
        return this.post('/api/v1/code/execute', {
            node_type: nodeType,
            node_config: nodeConfig,
            state: state,
            agent_id: agentId,
            skill_id: skillId
        });
    }

    /**
     * Отправить сообщение агенту со стримингом
     * @param {string} agentId - ID агента
     * @param {string} message - Текст сообщения
     * @param {Object} options - Опции запроса
     * @param {Array} options.files - Файлы (опционально)
     * @param {string} options.contextId - ID контекста (опционально)
     * @param {string} options.skillId - ID skill (опционально)
     * @param {Object} options.variables - Переменные для выполнения (опционально)
     * @param {Array} options.breakpoints - Breakpoints для отладки (опционально)
     * @param {Object} options.mocks - Моки для тестирования (опционально)
     * @param {Function} onEvent - Callback для SSE событий
     */
    async streamMessage(agentId, message, options = {}, onEvent) {
        const { 
            files = [], 
            contextId = null, 
            skillId = null,
            variables = null,
            breakpoints = [], 
            mocks = {} 
        } = options;
        
        const url = `${this.baseUrl}/api/v1/${agentId}`;
        
        // A2A Message format (a2a-sdk)
        const a2aMessage = {
            messageId: Date.now().toString() + Math.random().toString(36).substr(2, 9),
            role: 'user',
            parts: [
                { kind: 'text', text: message },
                ...files
            ]
        };
        
        if (contextId) {
            a2aMessage.contextId = contextId;
        }
        
        // A2A JSON-RPC формат
        const body = {
            jsonrpc: '2.0',
            id: Date.now().toString(),
            method: 'message/stream',
            params: {
                message: a2aMessage
            }
        };
        
        // Добавляем metadata для skill, variables, breakpoints и mocks
        const metadata = {};
        if (skillId) {
            metadata.skill = skillId;
        }
        if (variables) {
            metadata.variables = variables;
        }
        if (breakpoints && breakpoints.length > 0) {
            metadata.breakpoints = breakpoints;
        }
        if (mocks && Object.keys(mocks).length > 0) {
            metadata.mocks = mocks;
        }
        
        if (Object.keys(metadata).length > 0) {
            body.params.metadata = metadata;
        }
        
        return this.postStream(url, body, onEvent);
    }
}

