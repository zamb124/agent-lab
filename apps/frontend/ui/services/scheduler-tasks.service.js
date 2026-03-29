import { BaseService } from '@platform/lib/services/BaseService.js';

export class SchedulerTasksService extends BaseService {
    async list(params = {}) {
        const query = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value !== null && value !== undefined && value !== '') {
                query.set(key, String(value));
            }
        });
        const suffix = query.toString() ? `?${query.toString()}` : '';
        return this.get(`/api/scheduler/schedules${suffix}`);
    }

    async create(payload) {
        return this.post('/api/scheduler/schedules', payload);
    }

    async pause(taskId) {
        return this.post(`/api/scheduler/schedules/${taskId}/pause`);
    }

    async resume(taskId) {
        return this.post(`/api/scheduler/schedules/${taskId}/resume`);
    }

    async cancel(taskId) {
        return this.post(`/api/scheduler/schedules/${taskId}/cancel`);
    }

    async runNow(taskId) {
        return this.post(`/api/scheduler/schedules/${taskId}/run-now`);
    }
}
