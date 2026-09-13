/**
 * Canvas превью HTML-редактора: кадр ширины холста, тема light/dark, overlay empty/error.
 */

import { css, html, nothing } from '../../lit-shim.js';
import { HTML_EDITOR_SNIPPETS, HTML_EDITOR_VIEWPORTS } from './html-editor-api.js';

// static i18nNamespace = 'flows'; host modal passes t()

export const htmlEditorStageStyles = css`
    .stage {
        --flow-ui-html-min-height: 180px;
        display: grid; justify-items: center; align-content: start; overflow: auto;
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
    .stage .frame { width: min(100%, var(--preview-width, 1180px)); min-width: 0; }
    .stage .overlay {
        width: min(100%, var(--preview-width, 1180px)); display: grid; gap: 8px; padding: 12px 4px;
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

export function renderHtmlEditorStage({ viewport, theme, empty, error, t, onSnippet, canvas }) {
    const width = HTML_EDITOR_VIEWPORTS[viewport] ?? HTML_EDITOR_VIEWPORTS.desktop;
    return html`<div class="stage" data-theme=${theme} style=${`--preview-width:${width}px`} aria-label=${t('interface_editor.html_preview')}>
        ${empty ? html`<div class="overlay" data-kind="empty">
            <p>${t('interface_editor.html_empty_preview')}</p>
            <div class="cards">
                ${HTML_EDITOR_SNIPPETS.filter((item) => item.kitchen !== true).map((item) => html`<button type="button"
                    data-snippet=${item.id} @click=${() => onSnippet(item.id)}>${t(`interface_editor.html_snippet_${item.id}`)}</button>`)}
            </div>
        </div>` : html`<div class="frame">${canvas}</div>`}
        ${error !== '' ? html`<div class="overlay" data-kind="error"><p>${error}</p></div>` : nothing}
    </div>`;
}
