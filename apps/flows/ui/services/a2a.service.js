/**
 * A2AService - HTTP-клиент к REST API сервиса flows.
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class A2AService extends BaseService {
    constructor(baseUrl) {
        super(baseUrl);
    }

    async listFlows() {
        const data = await this.get('/api/v1/flows/');
        return data.items;
    }

    async getFlow(flowId) {
        return this.getFlowConfig(flowId);
    }

    async getFlowConfig(flowId) {
        return this.get(`/api/v1/flows/${flowId}`);
    }

    async createFlow(config) {
        return this.post('/api/v1/flows/', config);
    }

    async updateFlow(flowId, config) {
        return this.put(`/api/v1/flows/${flowId}`, config);
    }

    async saveFlowConfig(flowId, config) {
        return this.updateFlow(flowId, config);
    }

    async deleteFlow(flowId) {
        return this.delete(`/api/v1/flows/${flowId}`);
    }

    async reloadFlowFromBundle(flowId) {
        return this.post(`/api/v1/flows/${encodeURIComponent(flowId)}/reload-from-bundle`, {});
    }

    async listStoreBundles() {
        return this.get('/api/v1/flows/store/bundles');
    }

    async sendMessage(flowId, message, context = {}) {
        return this.post(`/api/v1/flows/${flowId}/chat`, {
            message,
            context
        });
    }

    async getChatHistory(sessionId) {
        return this.get(`/api/v1/chat/history/${sessionId}`);
    }

    async getSessions(flowId = null, options = {}) {
        const params = new URLSearchParams();
        if (flowId) params.append('flow_id', flowId);
        if (options.limit) params.append('limit', options.limit);
        if (options.offset) params.append('offset', options.offset);
        const query = params.toString();
        const response = await this.get(`/api/v1/sessions/${query ? '?' + query : ''}`);
        return response.items || [];
    }

    async deleteSession(flowId, sessionId) {
        return this.delete(`/api/v1/sessions/${sessionId}`);
    }

    async getSessionState(sessionId) {
        return this.get(`/api/v1/tasks/state?session_id=${encodeURIComponent(sessionId)}`);
    }

    async getEditorState(flowId, skillId = 'default') {
        const params = new URLSearchParams({
            flow_id: flowId,
            skill_id: skillId || 'default',
        });
        return this.get(`/api/v1/code/editor-state?${params}`);
    }

    async getSkills() {
        return this.get('/api/v1/skills');
    }

    async getTools() {
        const data = await this.get('/api/v1/tools');
        return data.items;
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

    async validateNode(nodeType, nodeConfig, state, flowId, skillId) {
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

    async executeNode(nodeType, nodeConfig, state, flowId, skillId) {
        return this.post('/api/v1/code/execute', {
            node_type: nodeType,
            node_config: nodeConfig,
            state: state,
            flow_id: flowId,
            skill_id: skillId
        });
    }

    /**
     * Стриминг сообщения к flow (A2A).
     * @param {string} flowId
     * @param {string} message - Текст сообщения
     * @param {Object} options - Опции запроса
     * @param {Array} options.files - Файлы (опционально)
     * @param {string} options.contextId - ID контекста (опционально)
     * @param {string} options.skillId - ID skill (опционально)
     * @param {Object} options.variables - Переменные для выполнения (опционально)
     * @param {Object|Array} options.breakpoints - Breakpoints для отладки (объект nodeId -> true или массив)
     * @param {Object|null} options.mock - MockConfig для metadata.mock (опционально)
     * @param {Function} onEvent - Callback для SSE событий
     */
    async streamMessage(flowId, message, options = {}, onEvent) {
        const { 
            files = [], 
            contextId = null, 
            skillId = null,
            variables = null,
            breakpoints = null, 
            mock = null,
            signal = null,
        } = options;
        
        const url = `${this.baseUrl}/api/v1/${flowId}`;
        
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
        
        // Добавляем metadata для skill, variables, breakpoints и mock (MockConfig)
        const metadata = {};
        if (skillId) {
            metadata.skill = skillId;
        }
        if (variables) {
            metadata.variables = variables;
        }
        const hasBreakpoints =
            breakpoints != null &&
            (Array.isArray(breakpoints)
                ? breakpoints.length > 0
                : typeof breakpoints === 'object' && Object.keys(breakpoints).length > 0);
        if (hasBreakpoints) {
            metadata.breakpoints = breakpoints;
        }
        if (mock != null && typeof mock === 'object' && Object.keys(mock).length > 0) {
            metadata.mock = mock;
        }
        
        if (Object.keys(metadata).length > 0) {
            body.params.metadata = metadata;
        }
        
        return this.postStream(url, body, onEvent, { signal });
    }

    /**
     * Отмена задачи на бекенде (A2A JSON-RPC tasks/cancel).
     * @param {string} flowId
     * @param {string} taskId
     */
    async cancelTask(flowId, taskId) {
        const url = `${this.baseUrl}/api/v1/${flowId}`;
        const body = {
            jsonrpc: '2.0',
            id: Date.now().toString(),
            method: 'tasks/cancel',
            params: { id: taskId },
        };
        return this.post(url, body);
    }

    async listOperatorQueues() {
        return this.get('/api/v1/operator/queues');
    }

    async createOperatorQueue(body) {
        return this.post('/api/v1/operator/queues', body);
    }

    async addOperatorQueueMember(queueId, body) {
        return this.post(
            `/api/v1/operator/queues/${encodeURIComponent(queueId)}/members`,
            body,
        );
    }

    async removeOperatorQueueMember(queueId, memberUserId) {
        return this.delete(
            `/api/v1/operator/queues/${encodeURIComponent(queueId)}/members/${encodeURIComponent(memberUserId)}`,
        );
    }

    async listOperatorTasks(params = {}) {
        const q = new URLSearchParams();
        if (params.queue_id) q.append('queue_id', params.queue_id);
        if (params.status) q.append('status', params.status);
        if (params.limit != null) q.append('limit', String(params.limit));
        if (params.offset != null) q.append('offset', String(params.offset));
        const suffix = q.toString() ? `?${q.toString()}` : '';
        return this.get(`/api/v1/operator/tasks${suffix}`);
    }

    async getOperatorTask(taskId) {
        return this.get(`/api/v1/operator/tasks/${encodeURIComponent(taskId)}`);
    }

    async claimOperatorTask(taskId) {
        return this.post(`/api/v1/operator/tasks/${encodeURIComponent(taskId)}/claim`, {});
    }

    async postOperatorTaskMessage(taskId, text, fileIds = []) {
        const body = { text };
        if (fileIds.length > 0) body.file_ids = fileIds;
        return this.post(`/api/v1/operator/tasks/${encodeURIComponent(taskId)}/messages`, body);
    }

    async completeOperatorTask(taskId, resolution, fileIds = []) {
        const body = { resolution };
        if (fileIds.length > 0) body.file_ids = fileIds;
        return this.post(`/api/v1/operator/tasks/${encodeURIComponent(taskId)}/complete`, body);
    }

    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        return this.post('/api/v1/files/', formData);
    }

    async listIntegrationCredentials() {
        return this.get('/api/v1/integrations/credentials');
    }

    async deleteIntegrationCredential(provider, service) {
        return this.delete(
            `/api/v1/integrations/credentials/${encodeURIComponent(provider)}/${encodeURIComponent(service)}`,
        );
    }
}

