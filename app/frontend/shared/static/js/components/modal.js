/**
 * Единая система модальных окон
 */

class ModalManager {
    constructor() {
        this.modals = new Map();
        this.currentModal = null;
        this.init();
    }
    
    init() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.currentModal) {
                this.hide(this.currentModal);
            }
        });
    }
    
    show(content, options = {}) {
        const {
            title = '',
            size = 'medium',
            closeButton = true,
            backdrop = true,
            keyboard = true,
            onClose = null
        } = options;
        
        const id = `modal_${Date.now()}`;
        
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.setAttribute('data-modal-id', id);
        modal.style.cssText = `
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            z-index: 99999 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            background: rgba(0,0,0,0.8) !important;
            opacity: 1 !important;
            visibility: visible !important;
        `;
        
        const dialog = document.createElement('div');
        dialog.className = `modal-dialog modal-${size}`;
        dialog.style.cssText = `
            background: var(--bg-primary);
            border-radius: 12px;
            max-width: ${this.getSizeValue(size)};
            width: 100%;
            max-height: 90vh;
            overflow: auto;
            margin: 20px;
        `;
        
        let html = '';
        
        if (title || closeButton) {
            html += `
                <div class="modal-header" style="padding: 20px; border-bottom: 1px solid var(--border-color);">
                    ${title ? `<h4 class="modal-title" style="margin: 0; color: var(--text-primary);">${title}</h4>` : ''}
                    ${closeButton ? `
                        <button class="modal-close-btn" style="background: none; border: none; font-size: 24px; cursor: pointer; color: var(--text-secondary);">
                            <i class="bi bi-x"></i>
                        </button>
                    ` : ''}
                </div>
            `;
        }
        
        html += `
            <div class="modal-body" style="padding: 20px;">
                ${content}
            </div>
        `;
        
        dialog.innerHTML = html;
        modal.appendChild(dialog);
        
        if (closeButton) {
            const closeBtn = dialog.querySelector('.modal-close-btn');
            closeBtn.addEventListener('click', () => this.hide(id));
        }
        
        if (backdrop) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hide(id);
                }
            });
        }
        
        document.body.appendChild(modal);
        document.body.style.overflow = 'hidden';
        
        this.modals.set(id, { element: modal, onClose });
        this.currentModal = id;
        
        return id;
    }
    
    hide(id) {
        const modal = this.modals.get(id);
        if (!modal) return;
        
        modal.element.style.opacity = '0';
        
        setTimeout(() => {
            modal.element.remove();
            this.modals.delete(id);
            
            if (this.currentModal === id) {
                this.currentModal = null;
            }
            
            if (this.modals.size === 0) {
                document.body.style.overflow = '';
            }
            
            if (modal.onClose) {
                modal.onClose();
            }
        }, 200);
    }
    
    hideAll() {
        this.modals.forEach((modal, id) => {
            this.hide(id);
        });
    }
    
    getSizeValue(size) {
        const sizes = {
            'small': '400px',
            'medium': '600px',
            'large': '800px',
            'xlarge': '1000px',
            'full': '95vw'
        };
        return sizes[size] || sizes['medium'];
    }
}

const modalManager = new ModalManager();

// Экспортируем в глобальную область
window.modalManager = modalManager;
window.showModal = (content, options = {}) => modalManager.show(content, options);
window.hideModal = (id) => modalManager.hide(id);
window.hideAllModals = () => modalManager.hideAll();

