/**
 * Canvas превью HTML-редактора: кадр ширины холста, тема light/dark, overlay empty/error.
 * Viewport / theme / Reload живут на тулбаре превью, не в шапке модалки.
 */

import { css, html, nothing, type TemplateResult } from 'lit';
import { HTML_EDITOR_SNIPPETS, HTML_EDITOR_VIEWPORTS } from './html-editor-api.js';
import type { HtmlEditorT } from './html-editor-inspector.js';

interface HtmlEditorStageToolbarArgs {
    viewport: string;
    theme: string;
    t: HtmlEditorT;
    onViewport: (viewport: unknown) => void;
    onTheme: (theme: unknown) => void;
    onReload: () => void;
    onCollapse: () => void;
    collapseDisabled?: boolean;
}

export interface HtmlEditorStageRenderArgs extends HtmlEditorStageToolbarArgs {
    empty: boolean;
    error: string;
    onSnippet: (id: string) => void;
    canvas: unknown;
}

// static i18nNamespace = 'flows'; host modal passes t()

export const htmlEditorStageStyles = css`
    .preview-pane {
        display: grid; grid-template-rows: auto minmax(220px, 1fr);
        min-height: 0; min-width: 0; height: 100%; overflow: hidden;
    }
    .stage-toolbar {
        display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
        min-width: 0; padding-bottom: 6px;
    }
    .stage-toolbar .collapse { margin-left: auto; }
    .stage {
        --flow-ui-html-min-height: 180px;
        display: grid; justify-items: center; align-content: start;
        grid-template-rows: minmax(0, 1fr);
        overflow: hidden; isolation: isolate; contain: paint;
        min-height: 220px; padding: var(--space-3); border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md); box-sizing: border-box;
        background: var(--flow-ui-page-background, var(--bg-primary));
        color: var(--flow-ui-text, var(--text-primary));
    }
    .stage[data-theme='dark'] {
        --flow-ui-text: rgba(255, 255, 255, 0.95); --flow-ui-heading: rgba(255, 255, 255, 0.95);
        --flow-ui-muted: rgba(255, 255, 255, 0.45); --flow-ui-border: rgba(255, 255, 255, 0.1);
        --flow-ui-panel: rgba(35, 35, 55, 0.85); --flow-ui-surface: rgba(35, 35, 55, 0.85);
        --flow-ui-input: rgba(0, 0, 0, 0.22); --flow-ui-accent: #99A6F9; --flow-ui-accent-hover: #8794F0;
        --flow-ui-on-accent: #0f0f1a; --flow-ui-accent-muted: rgba(153, 166, 249, 0.15);
        --flow-ui-radius: 24px; --flow-ui-radius-md: 12px; --flow-ui-page-background: #16213e;
        background: var(--flow-ui-page-background); color: var(--flow-ui-text);
    }
    .stage[data-theme='light'] {
        --flow-ui-text: #1c1f2e; --flow-ui-heading: #1c1f2e; --flow-ui-muted: rgba(28, 31, 46, 0.52);
        --flow-ui-border: rgba(28, 31, 46, 0.1); --flow-ui-panel: rgba(255, 255, 255, 0.98);
        --flow-ui-surface: rgba(28, 31, 46, 0.05); --flow-ui-input: rgba(255, 255, 255, 0.92);
        --flow-ui-accent: #6d62e8; --flow-ui-accent-hover: #5a50d4; --flow-ui-on-accent: #ffffff;
        --flow-ui-accent-muted: rgba(109, 98, 232, 0.2); --flow-ui-radius: 24px; --flow-ui-radius-md: 12px;
        --flow-ui-page-background: #f8fafc;
        background: var(--flow-ui-page-background); color: var(--flow-ui-text);
    }
    .stage .frame {
        width: min(100%, var(--preview-width, 1180px)); min-width: 0; min-height: 0;
        height: 100%; max-height: 100%; overflow: auto; overscroll-behavior: contain;
    }
    .stage .overlay {
        width: min(100%, var(--preview-width, 1180px)); display: grid; gap: 8px; padding: 12px 4px;
        min-height: 0; overflow: auto;
    }
    .stage .overlay p { margin: 0; font-size: 12px; color: var(--text-secondary); }
    .stage .overlay[data-kind='error'] p { color: var(--error); font-family: var(--font-mono); font-size: 11.5px; }
    .stage .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 6px; }
    .stage .cards button {
        margin: 0; padding: 10px 8px; border: 1px solid var(--border-subtle); border-radius: 10px;
        background: var(--glass-solid-subtle); color: var(--text-primary); font: inherit; font-size: 12px;
        text-align: left; cursor: pointer;
    }
    .stage .cards button:hover { background: var(--glass-solid-medium); }
`;

function renderStageToolbar({ viewport, theme, t, onViewport, onTheme, onReload, onCollapse, collapseDisabled }: HtmlEditorStageToolbarArgs) {
    const viewports = Object.keys(HTML_EDITOR_VIEWPORTS).map((value) => ({
        value,
        icon: value === 'desktop' ? 'monitor' : (value === 'tablet' ? 'tablet' : 'smartphone'),
        title: t(`interface_editor.viewport_${value}`),
    }));
    return html`<div class="stage-toolbar">
        <platform-segmented-control class="viewport-control" density="compact" icon-only .value=${viewport}
            .items=${viewports} aria-label=${t('interface_editor.viewport')}
            @change=${(event: CustomEvent<{ value: unknown }>) => onViewport(event.detail.value)}></platform-segmented-control>
        <platform-segmented-control class="theme-control" density="compact" .value=${theme}
            .items=${[{ value: 'dark', label: t('interface_editor.html_theme_dark') }, { value: 'light', label: t('interface_editor.html_theme_light') }]}
            @change=${(event: CustomEvent<{ value: unknown }>) => onTheme(event.detail.value)}></platform-segmented-control>
        <platform-button ghost density="compact" class="reload-preview" data-reload @click=${onReload}>
            <platform-icon name="refresh" size="13"></platform-icon>${t('interface_editor.html_reload')}
        </platform-button>
        <platform-button ghost density="compact" class="collapse" data-collapse="preview"
            ?disabled=${collapseDisabled === true}
            title=${t('interface_editor.html_panel_hide', { name: t('interface_editor.html_panel_preview') })}
            @click=${onCollapse}>
            <platform-icon name="minimize" size="13"></platform-icon>
        </platform-button>
    </div>`;
}

function previewWidth(viewport: string): number {
    switch (viewport) {
        case 'tablet':
            return HTML_EDITOR_VIEWPORTS.tablet;
        case 'mobile':
            return HTML_EDITOR_VIEWPORTS.mobile;
        default:
            return HTML_EDITOR_VIEWPORTS.desktop;
    }
}

export function renderHtmlEditorStage({
    viewport, theme, empty, error, t, onSnippet, canvas, onViewport, onTheme, onReload, onCollapse, collapseDisabled,
}: HtmlEditorStageRenderArgs) {
    const width = previewWidth(viewport);
    return html`<div class="preview-pane">
        ${renderStageToolbar({ viewport, theme, t, onViewport, onTheme, onReload, onCollapse, collapseDisabled })}
        <div class="stage" data-theme=${theme} style=${`--preview-width:${width}px`} aria-label=${t('interface_editor.html_preview')}>
            ${empty ? html`<div class="overlay" data-kind="empty">
                <p>${t('interface_editor.html_empty_preview')}</p>
                <div class="cards">
                    ${HTML_EDITOR_SNIPPETS.filter((item) => item.kitchen !== true).map((item) => html`<button type="button"
                        data-snippet=${item.id} @click=${() => onSnippet(item.id)}>${t(`interface_editor.html_snippet_${item.id}`)}</button>`)}
                </div>
            </div>` : html`<div class="frame">${canvas}</div>`}
            ${error !== '' ? html`<div class="overlay" data-kind="error"><p>${error}</p></div>` : nothing}
        </div>
    </div>`;
}
