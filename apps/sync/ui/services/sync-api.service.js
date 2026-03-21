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

    async getChannels(limit = 200) {
        return this.get(`/channels/?limit=${limit}`);
    }

    async getCompanyMembers() {
        return this.get('/company/members');
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
}
