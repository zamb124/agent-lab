/**
 * Settings View - настройки RAG Service
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { RagStore } from '../store/rag.store.js';
import '@platform/lib/components/layout/page-header.js';

export class SettingsView extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            
            .settings-grid {
                display: grid;
                gap: var(--space-4);
            }
            
            .setting-card {
                padding: var(--space-5);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            
            .setting-header {
                display: flex;
                justify-content: space-between;
                align-items: start;
                margin-bottom: var(--space-3);
            }
            
            .setting-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-1);
            }
            
            .setting-description {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .setting-value {
                font-size: var(--text-base);
                color: var(--text-secondary);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
                font-family: var(--font-mono);
            }
            
            .info-box {
                padding: var(--space-4);
                background: var(--info-bg);
                border: 1px solid var(--info-border);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.6;
            }
        `
    ];
    
    constructor() {
        super();
        this.state = this.use(s => ({
            currentProvider: s.providers.current,
            usage: s.usage,
        }));
    }
    
    render() {
        const { currentProvider, usage } = this.state.value;
        
        return html`
            <page-header 
                title=${this.i18n.t('settings_view.title')} 
                subtitle=${this.i18n.t('settings_view.subtitle')}
            ></page-header>
            
            <div class="settings-grid">
                <div class="setting-card">
                    <div class="setting-header">
                        <div>
                            <div class="setting-title">${this.i18n.t('settings_view.current_provider')}</div>
                            <div class="setting-description">${this.i18n.t('settings_view.current_provider_desc')}</div>
                        </div>
                    </div>
                    <div class="setting-value">${currentProvider}</div>
                </div>
                
                <div class="setting-card">
                    <div class="setting-header">
                        <div>
                            <div class="setting-title">${this.i18n.t('settings_view.usage')}</div>
                            <div class="setting-description">${this.i18n.t('settings_view.usage_desc')}</div>
                        </div>
                    </div>
                    <div style="display: flex; gap: var(--space-4); margin-top: var(--space-3);">
                        <div>
                            <div class="setting-description">${this.i18n.t('settings_view.pages')}</div>
                            <div class="setting-value">${usage.pages} / ${usage.maxPages}</div>
                        </div>
                        <div>
                            <div class="setting-description">${this.i18n.t('settings_view.queries')}</div>
                            <div class="setting-value">${usage.retrievals} / ${usage.maxRetrievals}</div>
                        </div>
                    </div>
                </div>
                
                <div class="info-box">
                    <strong>${this.i18n.t('settings_view.about_title')}</strong><br/>
                    ${this.i18n.t('settings_view.about_text')}
                </div>
            </div>
        `;
    }
}

customElements.define('settings-view', SettingsView);
