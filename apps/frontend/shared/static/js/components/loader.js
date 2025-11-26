/**
 * Компоненты загрузки
 */

export function createLoader(text = 'Загрузка...') {
    const loader = document.createElement('div');
    loader.className = 'loading-indicator';
    loader.innerHTML = `
        <div class="spinner"></div>
        ${text ? `<span>${text}</span>` : ''}
    `;
    return loader;
}

export function createSpinner(size = 'medium') {
    const spinner = document.createElement('div');
    spinner.className = `spinner spinner-${size}`;
    return spinner;
}

export function showLoader(container, text = 'Загрузка...') {
    if (!container) return null;
    
    const loader = createLoader(text);
    container.innerHTML = '';
    container.appendChild(loader);
    return loader;
}

export function hideLoader(container) {
    if (!container) return;
    
    const loader = container.querySelector('.loading-indicator');
    if (loader) {
        loader.remove();
    }
}

export class LoadingOverlay {
    constructor() {
        this.overlay = null;
    }
    
    show(text = 'Загрузка...') {
        if (this.overlay) return;
        
        this.overlay = document.createElement('div');
        this.overlay.className = 'loading-overlay';
        this.overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 100000;
        `;
        
        this.overlay.innerHTML = `
            <div style="background: var(--bg-primary); padding: 30px; border-radius: 12px; text-align: center;">
                <div class="spinner" style="margin-bottom: 15px;"></div>
                <div style="color: var(--text-primary); font-size: 16px;">${text}</div>
            </div>
        `;
        
        document.body.appendChild(this.overlay);
        document.body.style.overflow = 'hidden';
    }
    
    hide() {
        if (!this.overlay) return;
        
        this.overlay.style.opacity = '0';
        setTimeout(() => {
            if (this.overlay) {
                this.overlay.remove();
                this.overlay = null;
                document.body.style.overflow = '';
            }
        }, 200);
    }
}

const loadingOverlay = new LoadingOverlay();

export function showLoadingOverlay(text) {
    loadingOverlay.show(text);
}

export function hideLoadingOverlay() {
    loadingOverlay.hide();
}

