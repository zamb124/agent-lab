import { BaseService } from '../lib/services/BaseService.js';

export class TeamService extends BaseService {
    async getMembers() {
        return this.get('/api/team/members');
    }

    async searchUsers(query) {
        return this.get(`/api/team/search?q=${encodeURIComponent(query)}`);
    }

    async generateInviteLink(role = 'developer') {
        return this.post('/api/invites/generate', { role });
    }

    async updateMemberRole(userId, roles) {
        return this.patch(`/api/team/members/${userId}`, { roles });
    }

    async removeMember(userId) {
        return this.delete(`/api/team/members/${userId}`);
    }
}
