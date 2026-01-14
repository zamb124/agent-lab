/**
 * Team Service - API для управления командой
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class TeamService extends BaseService {
    /**
     * Получить список участников команды
     */
    async getMembers() {
        return this.get('/api/team/members');
    }
    
    /**
     * Пригласить нового участника
     */
    async inviteMember(email, role) {
        return this.post('/api/team/invite', { email, role });
    }
    
    /**
     * Обновить роли участника
     */
    async updateMemberRole(userId, roles) {
        return this.patch(`/api/team/members/${userId}`, { roles });
    }
    
    /**
     * Удалить участника из команды
     */
    async removeMember(userId) {
        return this.delete(`/api/team/members/${userId}`);
    }
}

