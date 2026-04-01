/**
 * SyncAPIService — все REST-запросы к Sync backend
 */
import { BaseService } from '@platform/lib/services/BaseService.js';
import { t } from '@platform/services/i18n/i18n.service.js';

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
            throw new Error(t('channel_settings.err_space_id', {}));
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
            throw new Error(t('sync_api.err_meeting_id', {}));
        }
        return this.get(`/meetings/${encodeURIComponent(meetingId)}`);
    }

    async getMeetingTranscript(meetingId) {
        if (typeof meetingId !== 'string' || meetingId === '') {
            throw new Error(t('sync_api.err_meeting_id', {}));
        }
        return this.get(`/meetings/${encodeURIComponent(meetingId)}/transcript`);
    }

    async exportMeetingToCrm(meetingId, namespace = null) {
        if (typeof meetingId !== 'string' || meetingId === '') {
            throw new Error(t('sync_api.err_meeting_id', {}));
        }
        return this.post(`/meetings/${encodeURIComponent(meetingId)}/export/crm`, { namespace });
    }

    async retryMeetingProcessing(meetingId) {
        if (typeof meetingId !== 'string' || meetingId === '') {
            throw new Error(t('sync_api.err_meeting_id', {}));
        }
        return this.post(`/meetings/${encodeURIComponent(meetingId)}/retry-processing`, {});
    }

    async getCallRecordings(callId) {
        if (typeof callId !== 'string' || callId === '') {
            throw new Error(t('sync_api.err_call_id', {}));
        }
        return this.get(`/calls/${encodeURIComponent(callId)}/recordings`);
    }

    async getCrmNamespaces() {
        const response = await fetch('/crm/api/v1/namespaces', { credentials: 'include' });
        if (!response.ok) {
            throw new Error(t('sync_api.err_crm_ns_http', { status: response.status }));
        }
        const payload = await response.json();
        if (!payload || !Array.isArray(payload.namespaces)) {
            throw new Error(t('sync_api.err_crm_ns_payload', {}));
        }
        return payload.namespaces;
    }

    /**
     * @param {string} channelId
     */
    async markChannelRead(channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        return this.post(`/channels/${encodeURIComponent(channelId)}/read`, {});
    }

    /**
     * @param {string} channelId
     * @param {{ notifications_muted: boolean }} body
     */
    async patchChannelNotificationSettings(channelId, body) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
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
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (typeof userId !== 'string' || userId === '') {
            throw new Error(t('sync_api.err_user_id', {}));
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
            throw new Error(t('channel_settings.err_channel_id', {}));
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
            throw new Error(t('sync_api.err_user_id', {}));
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
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        return this.patch(`/channels/${encodeURIComponent(channelId)}`, body);
    }

    /**
     * @param {string} peerUserId
     */
    async createDirectChannel(peerUserId) {
        if (typeof peerUserId !== 'string' || peerUserId.trim() === '') {
            throw new Error(t('sync_api.err_peer_user_id', {}));
        }
        return this.post('/channels/', {
            space_id: null,
            type: 'direct',
            name: null,
            is_private: false,
            member_ids: [peerUserId.trim()],
        });
    }

    /**
     * @param {string} channelId
     * @param {{ limit?: number, before?: string | null, after?: string | null }} [pagination]
     * @returns {Promise<{items: object[], next_cursor: string | null, prev_cursor: string | null}>}
     */
    async getMessages(channelId, pagination = {}) {
        if (typeof channelId !== 'string' || channelId === '') {
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        const search = new URLSearchParams();
        const limit = pagination.limit ?? 20;
        if (typeof limit !== 'number' || !Number.isInteger(limit) || limit < 1) {
            throw new Error(t('sync_api.err_limit', {}));
        }
        search.set('limit', String(limit));
        if (pagination.before !== undefined && pagination.before !== null) {
            if (typeof pagination.before !== 'string' || pagination.before === '') {
                throw new Error(t('sync_api.err_before', {}));
            }
            search.set('before', pagination.before);
        }
        if (pagination.after !== undefined && pagination.after !== null) {
            if (typeof pagination.after !== 'string' || pagination.after === '') {
                throw new Error(t('sync_api.err_after', {}));
            }
            search.set('after', pagination.after);
        }
        if (search.has('before') && search.has('after')) {
            throw new Error(t('sync_api.err_before_after', {}));
        }
        const payload = await this.get(
            `/channels/${encodeURIComponent(channelId)}/messages?${search.toString()}`
        );
        if (!payload || typeof payload !== 'object') {
            throw new Error(t('sync_api.err_messages_payload', {}));
        }
        if (!Array.isArray(payload.items)) {
            throw new Error(t('sync_api.err_messages_items', {}));
        }
        return payload;
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
            throw new Error(t('channel_settings.err_channel_id', {}));
        }
        if (typeof messageId !== 'string' || messageId === '') {
            throw new Error(t('sync_api.err_message_id', {}));
        }
        return this.post(
            `/channels/${encodeURIComponent(channelId)}/messages/${encodeURIComponent(messageId)}/transcribe`,
            {}
        );
    }
}
