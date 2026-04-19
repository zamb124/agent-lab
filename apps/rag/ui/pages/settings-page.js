/**
 * SettingsPage — настройки RAG-сервиса.
 *
 * Сейчас единственная управляемая настройка — выбор активного провайдера
 * (`<provider-selector>`). Бэкенд для usage/quotas пока не предоставлен,
 * поэтому страница содержит только секцию провайдеров и информационный блок.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '../components/provider-selector.js';

export class SettingsPage extends PlatformPage {
    static i18nNamespace = 'rag';

    static styles = [
        PlatformPage.styles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; }
            .breadcrumbs-wrap { flex-shrink: 0; margin-bottom: var(--space-3); }
            .settings-grid { display: grid; gap: var(--space-4); }
            .setting-card {
                padding: var(--space-5);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }
            .setting-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: var(--space-3); }
            .setting-title { font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--text-primary); margin-bottom: var(--space-1); }
            .setting-description { font-size: var(--text-sm); color: var(--text-tertiary); }
            .info-box {
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.6;
            }
        `,
    ];

    render() {
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                title=${this.t('settings_view.header_title')}
                subtitle=${this.t('settings_view.header_subtitle')}
            ></page-header>
            <div class="settings-grid">
                <div class="setting-card">
                    <div class="setting-header">
                        <div>
                            <div class="setting-title">${this.t('settings_view.providers_section')}</div>
                            <div class="setting-description">${this.t('settings_view.providers_section_desc')}</div>
                        </div>
                    </div>
                    <provider-selector></provider-selector>
                </div>

                <div class="info-box">
                    <strong>${this.t('settings_view.about_title')}</strong><br/>
                    ${this.t('settings_view.about_text')}
                </div>
            </div>
        `;
    }
}

customElements.define('rag-settings-page', SettingsPage);
