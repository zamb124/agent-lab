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

    async createChannel(spaceId, name) {
        return this.post('/channels/', {
            space_id: spaceId,
            type: 'topic',
            name,
            is_private: false,
            member_ids: null,
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
}
