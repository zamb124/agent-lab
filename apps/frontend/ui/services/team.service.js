/**
 * Team Service - API для управления командой
 */
import { BaseService } from '@platform/lib/services/BaseService.js';

export class TeamService extends BaseService {
    /**
     * Получить список участников команды
     */
    async getMembers() {
        const response = await this.get('/api/team/members');
        return response.items || [];
    }
    
    /**
     * Создать ссылку-приглашение в компанию
     */
    async generateInviteLink(role = 'developer') {
        return this.post('/api/invites/generate', { role });
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

