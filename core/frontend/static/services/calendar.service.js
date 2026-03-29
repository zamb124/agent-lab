import { BaseService } from '../lib/services/BaseService.js';

export class CalendarService extends BaseService {
    getGoogleConnectUrl(returnPath = '/') {
        const encodedReturnPath = encodeURIComponent(returnPath);
        return `${this.baseUrl}/api/calendar/integrations/google/start?return_path=${encodedReturnPath}`;
    }

    async listEvents({ startAt, endAt, includeSources = null, limit = 1000 }) {
        return this.post('/api/calendar/events/list', {
            start_at: startAt,
            end_at: endAt,
            include_sources: includeSources,
            limit,
        });
    }

    async createEvent(payload) {
        return this.post('/api/calendar/events', payload);
    }

    async updateEvent(eventId, payload) {
        return this.put(`/api/calendar/events/${eventId}`, payload);
    }

    async deleteEvent(eventId) {
        return this.delete(`/api/calendar/events/${eventId}`);
    }

    async listIntegrations() {
        return this.get('/api/calendar/integrations');
    }

    async connectIntegration(payload) {
        return this.post('/api/calendar/integrations/connect', payload);
    }

    async disconnectIntegration(provider) {
        return this.delete(`/api/calendar/integrations/${encodeURIComponent(provider)}`);
    }

    async runSync(payload) {
        return this.post('/api/calendar/sync', payload);
    }
}
