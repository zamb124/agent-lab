import { BaseService } from '@platform/lib/services/BaseService.js';

export class SchedulerTasksService extends BaseService {
    async listSchedules(params = {}) {
        return super.list('/api/scheduler/schedules', params);
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

    async getRedisSnapshot(taskId) {
        return this.get(`/api/scheduler/schedules/${taskId}/redis`);
    }
}
