import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class CrawlReportEnrichmentTags extends PlatformElement {
    static i18nNamespace = 'frontend';

    static override properties: PropertyDeclarations = {
        enrichmentSnapshot: { type: Object },
        structuralSignals: { type: Object },
        compact: { type: Boolean },
    }
    declare enrichmentSnapshot: Record<string, unknown> | null;
    declare structuralSignals: Record<string, unknown> | null;
    declare compact: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                align-items: center;
            }
            .tag {
                display: inline-flex;
                align-items: center;
                padding: 2px 8px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--accent);
                border: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
            }
            .tag.muted {
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                border-color: var(--glass-border-subtle);
            }
            .tag.warn {
                background: color-mix(in srgb, var(--warning) 12%, transparent);
                color: var(--warning);
                border-color: color-mix(in srgb, var(--warning) 25%, transparent);
            }
            .title {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                margin-bottom: var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this.enrichmentSnapshot = null;
        this.structuralSignals = null;
        this.compact = false;
    }

    _contentTypeLabel(contentType: Record<string, any>) {
        const key = `crawl_report_page.content_type_${contentType}`;
        const translated = this.t(key);
        if (translated === key) return contentType;
        return translated;
    }

    _topicLabel(topic: string) {
        const key = `crawl_report_page.topic_${topic}`;
        const translated = this.t(key);
        if (translated === key) return topic;
        return translated;
    }

    _renderStructuralPreview() {
        const signals = this.structuralSignals;
        if (!signals) return nothing;
        const tags: any[] = [];
        if (signals.content_type_hint) {
            tags.push(html`<span class="tag muted">${this._contentTypeLabel(signals.content_type_hint)}</span>`);
        }
        if (signals.title && !this.compact) {
            tags.push(html`<span class="tag muted">${signals.title}</span>`);
        }
        if (tags.length === 0) return nothing;
        return html`<div class="row">${tags}</div>`;
    }

    override render(): TemplateResult | typeof nothing {
        const snapshot = this.enrichmentSnapshot;
        if (!snapshot || !snapshot.filter_metadata) {
            return this._renderStructuralPreview();
        }
        const meta = snapshot.filter_metadata;
        const topicTags = Array.isArray((meta as Record<string, any>).topic_tags) ? (meta as Record<string, any>).topic_tags : [];
        const categoryPath = Array.isArray((meta as Record<string, any>).category_path) ? (meta as Record<string, any>).category_path : [];
        return html`
            <div class="row">
                <span class="tag">${this._contentTypeLabel((meta as Record<string, any>).content_type)}</span>
                <span class="tag">${this._topicLabel((meta as Record<string, any>).primary_topic)}</span>
                ${categoryPath.length > 0
                    ? html`<span class="tag muted">${categoryPath.map((segment: string) => this._topicLabel(segment)).join(' / ')}</span>`
                    : nothing}
                ${!this.compact
                    ? topicTags.slice(0, 3).map((tag: string) => html`<span class="tag muted">${this._topicLabel(tag)}</span>`)
                    : nothing}
            </div>
            ${snapshot.page_title && !this.compact
                ? html`<div class="title">${snapshot.page_title}</div>`
                : nothing}
        `;
    }
}

customElements.define('crawl-report-enrichment-tags', CrawlReportEnrichmentTags);
