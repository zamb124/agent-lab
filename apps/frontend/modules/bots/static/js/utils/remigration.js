/**
 * Remigration Manager
 */

export class RemigrationManager {
    constructor(app) {
        this.app = app;
        this.pendingRemigrateFlowId = null;
    }
    
    openConfirmModal(flowId) {
        this.pendingRemigrateFlowId = flowId;
        const modal = document.getElementById('remigrate-confirm-modal');
        const confirmBtn = document.getElementById('confirm-remigrate-btn');
        
        if (modal) {
            if (modal.parentElement !== document.body) {
                document.body.appendChild(modal);
            }
            modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        }
        
        if (confirmBtn) {
            confirmBtn.onclick = () => this.confirmRemigrate();
        }
    }
    
    closeModal() {
        const modal = document.getElementById('remigrate-confirm-modal');
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }
        this.pendingRemigrateFlowId = null;
    }
    
    async confirmRemigrate() {
        if (!this.pendingRemigrateFlowId) {
            return;
        }
        
        const flowId = this.pendingRemigrateFlowId;
        const modal = document.getElementById('remigrate-confirm-modal');
        
        if (modal) {
            modal.style.display = 'none';
        }
        
        if (this.app && this.app.showNotification) {
            this.app.showNotification('Выполняется сброс к коду...', 'info');
        }
        
        const response = await fetch(`/api/v1/admin/remigrate-flow-with-deps/${flowId}`, { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            if (this.app && this.app.showNotification) {
                this.app.showNotification('Ошибка: ' + (errorData.detail || `HTTP ${response.status}`), 'danger');
            }
            return;
        }
        
        const data = await response.json();
        if (this.app && this.app.showNotification) {
            this.app.showNotification(data.message, 'success');
        }
        
        setTimeout(async () => {
            const modalDetails = document.getElementById('modal-bot-details');
            if (modalDetails) {
                modalDetails.innerHTML = '<div class="loading-indicator"><div class="spinner"></div><span>Перезагрузка...</span></div>';
                
                const detailsResponse = await fetch(`/frontend/bots/${flowId}/details`);
                const html = await detailsResponse.text();
                modalDetails.innerHTML = html;
                
                if (this.app.botsModule) {
                    this.app.botsModule.initBotSettings();
                }
            }
        }, 500);
    }
}

