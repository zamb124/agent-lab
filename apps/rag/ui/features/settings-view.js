/**
 * Settings View - настройки RAG Service
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/layout/page-header.js';

export class SettingsView extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        buttonStyles,
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
        `,
    ];

    constructor() {
        super();
        this.state = this.use((s) => ({
            currentProvider: s.providers.current,
            usage: s.usage,
            loading: s.loading,
        }));
    }

    render() {
        const { currentProvider, usage, loading } = this.state.value;

        return html`
            <page-header
                title="Настройки"
                subtitle="Конфигурация RAG Service"
            ></page-header>

            <div class="settings-grid">
                <div class="setting-card">
                    <div class="setting-header">
                        <div>
                            <div class="setting-title">Текущий провайдер</div>
                            <div class="setting-description">Активный RAG провайдер для хранения документов</div>
                        </div>
                    </div>
                    <div class="setting-value">${currentProvider}</div>
                </div>

                <div class="setting-card">
                    <div class="setting-header">
                        <div>
                            <div class="setting-title">Использование</div>
                            <div class="setting-description">Текущее использование ресурсов</div>
                        </div>
                    </div>
                    <div style="display: flex; gap: var(--space-4); margin-top: var(--space-3);">
                        <div>
                            <div class="setting-description">Страницы</div>
                            <div class="setting-value">${usage.pages} / ${usage.maxPages}</div>
                        </div>
                        <div>
                            <div class="setting-description">Запросы</div>
                            <div class="setting-value">${usage.retrievals} / ${usage.maxRetrievals}</div>
                        </div>
                    </div>
                </div>

                <div class="setting-card">
                    <div class="setting-header">
                        <div>
                            <div class="setting-title">Индексация и поиск</div>
                            <div class="setting-description">
                                Парсинг, нарезка чанков и дефолты поиска задаются в merged конфиге сервиса:
                                ключ <code>rag.document_indexing</code> (схема как в
                                <code>core/rag_indexing_schema.py</code>).
                            </div>
                        </div>
                    </div>
                    ${loading
                        ? html`<div class="setting-description">Загрузка…</div>`
                        : html`<div class="setting-description">
                              Глобальный профиль — через деплой / conf.json. Параметры загрузки документа в namespace
                              (нарезка, парсинг) настраиваются на странице namespace и сохраняются в браузере.
                          </div>`}
                </div>

                <div class="info-box">
                    <strong>О RAG Service</strong><br />
                    Retrieval Augmented Generation (RAG) позволяет использовать ваши документы для улучшения
                    ответов AI. Документы разбиваются на части, векторизуются и сохраняются для быстрого
                    семантического поиска.
                </div>
            </div>
        `;
    }
}

customElements.define('settings-view', SettingsView);
