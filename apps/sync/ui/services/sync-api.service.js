/**
 * SyncAPIService — все REST-запросы к Sync backend
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class SyncAPIService extends BaseService {
    constructor(baseURL = '/sync/api/v1') {
        super(baseURL);
    }

    async getSpaces(limit = 50) {
        return this.get(`/spaces/?limit=${limit}`);
    }

    async createSpace(name, description) {
        return this.post('/spaces/', { name, description: description || null });
    }

    /**
     * @param {string} spaceId
     * @param {Record<string, unknown>} body
     */
    async updateSpace(spaceId, body) {
        if (typeof spaceId !== 'string' || spaceId === '') {
            throw new Error('spaceId обязателен.');
        }
        return this.patch(`/spaces/${encodeURIComponent(spaceId)}`, body);
    }

    async getChannels(limit = 200) {
        return this.get(`/channels/?limit=${limit}`);
    }

    async getMeetings(params = {}) {
        const search = new URLSearchParams();
        if (typeof params.channel_id === 'string' && params.channel_id !== '') {
            search.set('channel_id', params.channel_id);
        }
        if (typeof params.space_id === 'string' && params.space_id !== '') {
            search.set('space_id', params.space_id);
        }
        if (typeof params.limit === 'number') {
            search.set('limit', String(params.limit));
        }
        const query = search.toString();
        return this.get(`/meetings/${query ? `?${query}` : ''}`);
    }

    async getMeeting(meetingId) {
        if (typeof meetingId !== 'string' || meetingId === '') {
            throw new Error('meetingId обязателен.');
        }
        return this.get(`/meetings/${encodeURIComponent(meetingId)}`);
    }

    async getMeetingTranscript(meetingId) {
        if (typeof meetingId !== 'string' || meetingId === '') {
            throw new Error('meetingId обязателен.');
        }
        return this.get(`/meetings/${encodeURIComponent(meetingId)}/transcript`);
    }

    async exportMeetingToCrm(meetingId, namespace = null) {
        if (typeof meetingId !== 'string' || meetingId === '') {
            throw new Error('meetingId обязателен.');
        }
        return this.post(`/meetings/${encodeURIComponent(meetingId)}/export/crm`, { namespace });
    }

    async retryMeetingProcessing(meetingId) {
        if (typeof meetingId !== 'string' || meetingId === '') {
            throw new Error('meetingId обязателен.');
        }
        return this.post(`/meetings/${encodeURIComponent(meetingId)}/retry-processing`, {});
    }

    async getCallRecordings(callId) {
        if (typeof callId !== 'string' || callId === '') {
            throw new Error('callId обязателен.');
        }
        return this.get(`/calls/${encodeURIComponent(callId)}/recordings`);
    }

    async getCrmNamespaces() {
        const response = await fetch('/crm/api/v1/namespaces', { credentials: 'include' });
        if (!response.ok) {
            throw new Error(`Не удалось загрузить CRM namespaces: HTTP ${response.status}`);
        }
        const payload = await response.json();
        if (!payload || !Array.isArray(payload.namespaces)) {
            throw new Error('Некорректный ответ CRM namespaces.');
        }
        return payload.namespaces;
    }

    /**
     * @param {string} channelId
     */
    async markChannelRead(channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error('channelId обязателен.');
        }
        return this.post(`/channels/${encodeURIComponent(channelId)}/read`, {});
    }

    /**
     * @param {string} channelId
     * @param {{ notifications_muted: boolean }} body
     */
    async patchChannelNotificationSettings(channelId, body) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error('channelId обязателен.');
        }
        return this.patch(`/channels/${encodeURIComponent(channelId)}/notification-settings`, body);
    }

    /**
     * @param {string} channelId
     * @param {string} userId
     * @param {'owner'|'admin'|'member'|'viewer'} [role]
     */
    async addChannelMember(channelId, userId, role = 'member') {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error('channelId обязателен.');
        }
        if (typeof userId !== 'string' || userId === '') {
            throw new Error('userId обязателен.');
        }
        return this.post(`/channels/${encodeURIComponent(channelId)}/members`, {
            user_id: userId,
            role,
        });
    }

    /**
     * @param {string} channelId
     */
    async getChannelMembers(channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error('channelId обязателен.');
        }
        return this.get(`/channels/${encodeURIComponent(channelId)}/members`);
    }

    async getCompanyMembers() {
        return this.get('/company/members');
    }

    /**
     * Каналы, где есть и текущий пользователь, и указанный участник компании.
     * @param {string} userId
     */
    async getSharedChannelsWithMember(userId) {
        if (typeof userId !== 'string' || userId === '') {
            throw new Error('userId обязателен.');
        }
        return this.get(`/company/members/${encodeURIComponent(userId)}/shared-channels`);
    }

    async createChannel(spaceId, name) {
        return this.post('/channels/', {
            space_id: spaceId,
            type: 'topic',
            name,
            is_private: false,
            member_ids: null,
        });
    }

    /**
     * @param {string} channelId
     * @param {Record<string, unknown>} body
     */
    async updateChannel(channelId, body) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error('channelId обязателен.');
        }
        return this.patch(`/channels/${encodeURIComponent(channelId)}`, body);
    }

    /**
     * @param {string} peerUserId
     */
    async createDirectChannel(peerUserId) {
        if (typeof peerUserId !== 'string' || peerUserId.trim() === '') {
            throw new Error('peerUserId обязателен.');
        }
        return this.post('/channels/', {
            space_id: null,
            type: 'direct',
            name: null,
            is_private: false,
            member_ids: [peerUserId.trim()],
        });
    }

    async getMessages(channelId, limit = 100) {
        return this.get(`/channels/${encodeURIComponent(channelId)}/messages?limit=${limit}`);
    }

    async sendMessage(channelId, messageCreate) {
        return this.post(
            `/channels/${encodeURIComponent(channelId)}/messages`,
            messageCreate
        );
    }

    async uploadFile(file) {
        const fd = new FormData();
        fd.append('file', file);
        return this.post('/files/', fd);
    }

    async editMessage(channelId, messageId, body) {
        return this.patch(
            `/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}`,
            body
        );
    }

    async deleteMessage(channelId, messageId) {
        return this.delete(
            `/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}`
        );
    }

    async forwardMessage(channelId, messageId, toChannelId, threadId = null) {
        return this.post(
            `/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}/forward`,
            { to_channel_id: toChannelId, thread_id: threadId }
        );
    }

    async reactMessage(channelId, messageId, emoji) {
        return this.post(
            `/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}/react`,
            { emoji }
        );
    }

    async pinMessage(channelId, messageId, action) {
        return this.post(
            `/channels/${encodeURIComponent(channelId)}/pins`,
            { message_id: messageId, action }
        );
    }

    async transcribeMessage(channelId, messageId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error('channelId обязателен.');
        }
        if (typeof messageId !== 'string' || messageId === '') {
            throw new Error('messageId обязателен.');
        }
        return this.post(
            `/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}/transcribe`,
            {}
        );
    }
}
