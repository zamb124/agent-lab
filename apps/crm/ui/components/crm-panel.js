/**
 * CRM Panel - Расширение PlatformPanel с интеграцией CRMStore
 * Все панели CRM наследуют этот класс для получения функциональности сворачивания
 * с синхронизацией состояния через CRMStore
 */
import { css } from 'lit';
import { PlatformPanel } from '@platform/lib/components/layout/platform-panel.js';
import { CRMStore } from '../store/crm.store.js';

export class CRMPanel extends PlatformPanel {
    static properties = {
        ...PlatformPanel.properties,
        panelTitle: { type: String },
        panelIcon: { type: String },
    };

    /**
     * Алиас для обратной совместимости - наследники используют CRMPanel.panelStyles
     * Теперь просто возвращает стили родителя
     */
    static get panelStyles() {
        return PlatformPanel.styles;
    }

    constructor() {
        super();
        this.panelTitle = '';
        this.panelIcon = '';
        
        this._panelUnsubscribe = CRMStore.subscribe(state => {
            if (this.panelId) {
                const isCollapsed = state.ui.collapsedPanels[this.panelId] || false;
                if (this.collapsed !== isCollapsed) {
                    this.collapsed = isCollapsed;
                }
            }
        });
    }
    
    connectedCallback() {
        super.connectedCallback();
        if (this.panelId) {
            this.collapsed = CRMStore.isPanelCollapsed(this.panelId);
        }
    }
    
    disconnectedCallback() {
        super.disconnectedCallback();
        this._panelUnsubscribe?.();
    }
    
    updated(changedProps) {
        super.updated(changedProps);
        
        if (changedProps.has('panelTitle')) {
            this.title = this.panelTitle;
        }
        if (changedProps.has('panelIcon')) {
            this.icon = this.panelIcon;
        }
    }
    
    toggle() {
        if (this.panelId && this.collapsible) {
            CRMStore.togglePanel(this.panelId);
        }
    }
}

customElements.define('crm-panel', CRMPanel);
