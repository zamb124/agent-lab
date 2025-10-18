/**
 * Store Module - Магазин готовых решений
 */

export default class StoreModule {
    constructor(app) {
        this.app = app;
        this.name = 'store';
        this.version = '1.0.0';
    }
    
    async init() {
        console.log('🏪 Инициализация Store модуля');
        
        this.setupGlobalFunctions();
        
        return this;
    }
    
    setupGlobalFunctions() {
        window.installFlow = (flowId) => this.installFlow(flowId);
        window.viewFlowDetails = (flowId) => this.viewFlowDetails(flowId);
    }
    
    async installFlow(flowId) {
        console.log('Installing flow:', flowId);
        
        try {
            const response = await fetch(`/api/v1/store/flows/${flowId}/install`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                this.app.showNotification('Flow успешно установлен', 'success');
            } else {
                throw new Error('Ошибка установки');
            }
        } catch (error) {
            console.error('Ошибка установки flow:', error);
            this.app.showNotification('Ошибка при установке flow', 'danger');
        }
    }
    
    async viewFlowDetails(flowId) {
        console.log('Viewing flow details:', flowId);
    }
    
    destroy() {
        console.log('🧹 Store модуль выгружен');
    }
}

