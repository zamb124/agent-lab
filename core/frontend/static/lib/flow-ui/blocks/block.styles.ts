/**
 * Библиотека стилей блоков Flow UI — один визуальный язык для страницы, ленты и холста редактора.
 * Только ``--flow-ui-*`` токены (``shell/tokens.css`` / литералы хоста); переходы — по конкретным свойствам.
 * ``.fu-prose`` — общая типографика Markdown: блок ``markdown`` и ответ агента в ленте.
 */

import { css } from '../../lit-shim.js';

export const blockStyles = css`
    .fu-block {
        min-width: 0;
        box-sizing: border-box;
        width: calc(var(--fu-span, 12) / 12 * 100%);
        justify-self: start;
        align-self: start;
    }
    /* Grid — justify-self; flex-колонка (страница с лентой, .fu-column) — align-self. */
    .fu-block[data-align='center'] { justify-self: center; align-self: center; }
    .fu-block[data-align='end'] { justify-self: end; align-self: end; }
    .fu-block[data-block-type='button'],
    .fu-block[data-block-type='link'],
    .fu-block[data-block-type='badge'],
    .fu-block[data-block-type='status'] {
        width: max(min-content, calc(var(--fu-span, 12) / 12 * 100%));
        min-width: min-content;
    }
    .fu-block[data-span='12'],
    .fu-block[data-block-type='conversation'] {
        width: 100%;
        justify-self: stretch;
    }
    .fu-block[data-block-type='conversation'] { align-self: stretch; }
    .fu-block[data-selected='true'] { outline: 2px solid var(--flow-ui-accent); outline-offset: 3px; border-radius: var(--flow-ui-radius-sm); }
    :host([editing]) .fu-block { cursor: pointer; }
    :host([editing]) .fu-button,
    :host([editing]) .fu-link,
    :host([editing]) .fu-prompts button { pointer-events: none; }
    /* iframe sandbox ест клики — без этого html-блок на холсте нельзя выделить. */
    :host([editing]) flow-ui-html-block { pointer-events: none; }
    img.fu-glyph { display: block; filter: var(--flow-ui-glyph-filter); }
    svg.fu-glyph { display: block; flex: none; fill: none; stroke: currentColor; }

    /* Раскладка */
    .fu-section { display: grid; gap: var(--flow-ui-space-3); }
    .fu-section > h3 { margin: 0 0 2px; font-size: var(--flow-ui-font-size-xs); font-weight: 650; letter-spacing: .06em; text-transform: uppercase; color: var(--flow-ui-muted); }
    .fu-columns { display: grid; gap: var(--flow-ui-space-4); grid-template-columns: var(--fu-columns, 1fr); }
    @media (max-width: 640px) { .fu-columns { grid-template-columns: 1fr; } }
    .fu-column {
        display: flex; flex-direction: column; gap: var(--flow-ui-space-3);
        min-width: 0; min-height: 100%; align-items: start;
    }
    .fu-column > .fu-block[data-align='center'] { align-self: center; }
    .fu-column > .fu-block[data-align='end'] { align-self: end; }
    .fu-column > .fu-block[data-span='12'] { align-self: stretch; }
    .fu-column > .fu-block[data-valign='center'] { margin-block: auto; }
    .fu-column > .fu-block[data-valign='end'] { margin-top: auto; }
    :host([editing]) .fu-columns {
        padding: 6px; border: 1px dashed color-mix(in srgb, var(--flow-ui-accent) 32%, var(--flow-ui-border));
        border-radius: var(--flow-ui-radius-lg); background: color-mix(in srgb, var(--flow-ui-surface) 45%, transparent);
    }
    :host([editing]) .fu-column {
        min-height: 88px; padding: 8px; border: 1px dashed var(--flow-ui-border);
        border-radius: var(--flow-ui-radius-md); background: var(--flow-ui-page-background, var(--flow-ui-card));
    }
    :host([editing]) .fu-section, :host([editing]) .fu-tab-panel {
        min-height: 72px; padding: 8px; border: 1px dashed var(--flow-ui-border);
        border-radius: var(--flow-ui-radius-md);
    }
    .fu-container-empty {
        display: grid; place-items: center; min-height: 64px; padding: 16px 10px;
        color: var(--flow-ui-muted); font-size: var(--flow-ui-font-size-xs); text-align: center; pointer-events: none;
    }
    .fu-tabs { display: grid; gap: var(--flow-ui-space-3); }
    .fu-tabs > nav { display: inline-flex; gap: 2px; padding: 3px; border-radius: var(--flow-ui-radius-full); background: var(--flow-ui-surface); justify-self: start; max-width: 100%; overflow: auto; scrollbar-width: none; }
    .fu-tabs > nav button { border: 0; border-radius: var(--flow-ui-radius-full); padding: 6px 14px; background: transparent; color: var(--flow-ui-muted); font: inherit; font-size: var(--flow-ui-font-size-sm); font-weight: 550; white-space: nowrap; cursor: pointer; transition: var(--flow-ui-transition); }
    .fu-tabs > nav button:hover { color: var(--flow-ui-text); }
    .fu-tabs > nav button[aria-selected='true'] { color: var(--flow-ui-text); background: var(--flow-ui-panel-strong); box-shadow: 0 1px 2px rgba(0, 0, 0, .12); }
    .fu-tabs > nav button:focus-visible { outline: none; box-shadow: var(--flow-ui-focus-ring); }
    .fu-tab-panel { display: grid; gap: var(--flow-ui-space-3); }

    /* Типографика */
    .fu-heading { margin: 0; color: var(--flow-ui-heading); line-height: var(--flow-ui-line-height-tight); letter-spacing: -.015em; overflow-wrap: anywhere; }
    h1.fu-heading { font-size: 28px; font-weight: 700; } h2.fu-heading { font-size: 22px; font-weight: 650; } h3.fu-heading { font-size: 17px; font-weight: 650; }
    .fu-markdown, .fu-prose { color: var(--flow-ui-text); font-size: var(--flow-ui-font-size-body); line-height: var(--flow-ui-line-height); overflow-wrap: anywhere; }
    .fu-prose > :first-child, .fu-markdown > :first-child { margin-top: 0; } .fu-prose > :last-child, .fu-markdown > :last-child { margin-bottom: 0; }
    .fu-prose p, .fu-markdown p { margin: 0 0 .85em; }
    .fu-prose h1, .fu-prose h2, .fu-prose h3, .fu-prose h4, .fu-markdown h1, .fu-markdown h2, .fu-markdown h3, .fu-markdown h4 { margin: 1.3em 0 .5em; color: var(--flow-ui-heading); line-height: var(--flow-ui-line-height-tight); letter-spacing: -.01em; font-weight: 650; }
    .fu-prose h1, .fu-markdown h1 { font-size: 1.5em; } .fu-prose h2, .fu-markdown h2 { font-size: 1.3em; } .fu-prose h3, .fu-markdown h3 { font-size: 1.12em; } .fu-prose h4, .fu-markdown h4 { font-size: 1em; }
    .fu-prose ul, .fu-prose ol, .fu-markdown ul, .fu-markdown ol { margin: .3em 0 .9em; padding-left: 1.45em; }
    .fu-prose li, .fu-markdown li { margin: .28em 0; } .fu-prose li > p, .fu-markdown li > p { margin: 0; }
    .fu-prose strong, .fu-markdown strong { font-weight: 650; }
    .fu-prose a, .fu-markdown a { color: var(--flow-ui-accent); text-decoration: underline; text-decoration-color: color-mix(in srgb, var(--flow-ui-accent) 40%, transparent); text-underline-offset: 3px; }
    .fu-prose a:hover, .fu-markdown a:hover { text-decoration-color: currentColor; }
    .fu-prose code, .fu-markdown code { font-family: var(--font-mono); font-size: .9em; padding: .12em .4em; border-radius: 6px; background: var(--flow-ui-code-bg); }
    .fu-prose pre, .fu-markdown pre { margin: .6em 0 1em; padding: 12px 14px; border-radius: var(--flow-ui-radius-md); background: var(--flow-ui-code-bg); overflow: auto; line-height: 1.55; }
    .fu-prose pre code, .fu-markdown pre code { padding: 0; border-radius: 0; background: transparent; font-size: var(--flow-ui-font-size-mono); }
    .fu-prose blockquote, .fu-markdown blockquote { margin: .6em 0 1em; padding: 2px 0 2px 14px; border-left: 3px solid color-mix(in srgb, var(--flow-ui-accent) 55%, transparent); color: var(--flow-ui-text-secondary); }
    .fu-prose hr, .fu-markdown hr { border: 0; border-top: 1px solid var(--flow-ui-border); margin: 1.2em 0; }
    .fu-prose img, .fu-markdown img { max-width: 100%; border-radius: var(--flow-ui-radius-md); }
    .fu-prose table, .fu-markdown table { width: 100%; margin: .6em 0 1em; border-collapse: collapse; font-size: .93em; display: block; overflow: auto; }
    .fu-prose th, .fu-prose td, .fu-markdown th, .fu-markdown td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--flow-ui-border); vertical-align: top; }
    .fu-prose th, .fu-markdown th { font-weight: 600; color: var(--flow-ui-text-secondary); }
    .fu-media { display: block; max-width: 100%; border-radius: var(--flow-ui-radius-lg); }
    video.fu-media, audio.fu-media { width: 100%; height: auto; }
    .fu-code { margin: 0; padding: 12px 14px; border-radius: var(--flow-ui-radius-md); background: var(--flow-ui-code-bg); color: var(--flow-ui-text); font: var(--flow-ui-font-size-mono)/1.55 var(--font-mono); overflow: auto; white-space: pre; }
    .fu-badge, .fu-status { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: var(--flow-ui-radius-full); font-size: var(--flow-ui-font-size-xs); font-weight: 600; line-height: 1.4; background: color-mix(in srgb, currentColor 12%, transparent); color: var(--flow-ui-text); }
    .fu-status::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex: none; }
    [data-tone='info'] { color: var(--flow-ui-info); } [data-tone='success'] { color: var(--flow-ui-success); }
    [data-tone='warning'] { color: var(--flow-ui-warning); } [data-tone='danger'] { color: var(--flow-ui-danger); }
    .fu-alert { display: grid; gap: 4px; padding: 12px 16px; border-radius: var(--flow-ui-radius-lg); border: 1px solid color-mix(in srgb, currentColor 28%, transparent); background: color-mix(in srgb, currentColor 8%, transparent); font-size: var(--flow-ui-font-size-sm); line-height: 1.5; }
    .fu-alert[data-tone='neutral'] { color: var(--flow-ui-text); border-color: var(--flow-ui-border); background: var(--flow-ui-card); }
    .fu-alert strong { font-weight: 650; } .fu-alert p { margin: 0; color: var(--flow-ui-text); }
    .fu-metric { display: grid; gap: 2px; padding: 14px 16px; border-radius: var(--flow-ui-radius-lg); background: var(--flow-ui-card); border: 1px solid var(--flow-ui-border); }
    .fu-metric .label, .fu-metric .hint { font-size: var(--flow-ui-font-size-xs); color: var(--flow-ui-muted); }
    .fu-metric .value { font-size: 26px; font-weight: 700; letter-spacing: -.02em; line-height: 1.2; color: var(--flow-ui-heading); font-variant-numeric: tabular-nums; }
    .fu-progress { display: grid; gap: 6px; font-size: var(--flow-ui-font-size-xs); color: var(--flow-ui-muted); }
    .fu-progress progress { width: 100%; height: 6px; accent-color: var(--flow-ui-accent); }
    .fu-empty { display: grid; gap: 4px; padding: 28px 16px; text-align: center; border: 1px dashed var(--flow-ui-border); border-radius: var(--flow-ui-radius-lg); color: var(--flow-ui-muted); font-size: var(--flow-ui-font-size-sm); }
    .fu-empty strong { color: var(--flow-ui-text); font-size: var(--flow-ui-font-size-body); }
    .fu-divider { border: 0; border-top: 1px solid var(--flow-ui-border); margin: 4px 0; }

    /* Поля ввода */
    .fu-field { display: grid; gap: 6px; }
    .fu-field > label, .fu-field > .label { font-size: var(--flow-ui-font-size-sm); font-weight: 550; color: var(--flow-ui-text-secondary); }
    .fu-field .req { color: var(--flow-ui-danger); margin-left: 2px; }
    .fu-field input:not([type='checkbox']):not([type='range']), .fu-field textarea, .fu-field select {
        width: 100%; min-height: 42px; box-sizing: border-box; padding: 10px 14px; border-radius: var(--flow-ui-radius-md); border: 1px solid var(--flow-ui-border);
        background: var(--flow-ui-input); color: var(--flow-ui-text); font: inherit; font-size: var(--flow-ui-font-size-body); line-height: 1.4; outline: none; transition: var(--flow-ui-transition);
    }
    .fu-field input::placeholder, .fu-field textarea::placeholder { color: var(--flow-ui-muted); }
    .fu-field input:hover, .fu-field textarea:hover, .fu-field select:hover { border-color: color-mix(in srgb, var(--flow-ui-text) 22%, var(--flow-ui-border)); }
    .fu-field input:focus-visible, .fu-field textarea:focus-visible, .fu-field select:focus-visible { border-color: var(--flow-ui-accent); box-shadow: var(--flow-ui-focus-ring); }
    .fu-field[data-invalid='true'] input, .fu-field[data-invalid='true'] textarea, .fu-field[data-invalid='true'] select { border-color: color-mix(in srgb, var(--flow-ui-danger) 65%, transparent); }
    .fu-field textarea { min-height: 96px; resize: vertical; }
    .fu-field output { min-width: 3ch; text-align: right; font-variant-numeric: tabular-nums; color: var(--flow-ui-text-secondary); font-size: var(--flow-ui-font-size-sm); }
    .fu-field .error { font-size: var(--flow-ui-font-size-xs); color: var(--flow-ui-danger); }
    .fu-toggle { display: flex; align-items: center; gap: 10px; cursor: pointer; color: var(--flow-ui-text); font-size: var(--flow-ui-font-size-body); }
    .fu-toggle input { accent-color: var(--flow-ui-accent); width: 18px; height: 18px; margin: 0; }
    .fu-switch-track { position: relative; width: 40px; height: 22px; border-radius: var(--flow-ui-radius-full); background: color-mix(in srgb, var(--flow-ui-text) 22%, transparent); transition: background-color 160ms cubic-bezier(0.4, 0, 0.2, 1); flex: none; }
    .fu-switch-track::after { content: ''; position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, .25); transition: transform 160ms cubic-bezier(0.4, 0, 0.2, 1); }
    .fu-toggle input:checked + .fu-switch-track { background: var(--flow-ui-accent); }
    .fu-toggle input:checked + .fu-switch-track::after { transform: translateX(18px); }
    .fu-toggle input:focus-visible + .fu-switch-track { box-shadow: var(--flow-ui-focus-ring); }
    .fu-toggle input.visually-hidden { position: absolute; opacity: 0; width: 0; height: 0; }
    .fu-slider-row, .fu-control-row { display: flex; gap: 10px; align-items: center; min-width: 0; }
    .fu-slider-row input[type='range'] { flex: 1 1 auto; min-width: 0; accent-color: var(--flow-ui-accent); }
    .fu-control-row > input { flex: 1 1 auto; min-width: 0; }
    .fu-upload { display: grid; gap: 8px; padding: 20px 16px; border: 1px dashed color-mix(in srgb, var(--flow-ui-text) 22%, transparent); border-radius: var(--flow-ui-radius-lg); background: var(--flow-ui-card); text-align: center; color: var(--flow-ui-muted); font-size: var(--flow-ui-font-size-sm); cursor: pointer; transition: var(--flow-ui-transition); }
    .fu-upload:hover { border-color: color-mix(in srgb, var(--flow-ui-accent) 60%, transparent); color: var(--flow-ui-text); }
    .fu-upload ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; text-align: left; font-size: var(--flow-ui-font-size-xs); color: var(--flow-ui-text); }

    /* Кнопки и ссылки */
    .fu-button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 40px; padding: 0 18px; border-radius: var(--flow-ui-radius-full); border: 1px solid transparent; font: inherit; font-size: 14px; font-weight: 600; line-height: 1; cursor: pointer; text-decoration: none; transition: var(--flow-ui-transition); }
    .fu-button:disabled { opacity: .5; cursor: default; }
    .fu-button:focus-visible { outline: none; box-shadow: var(--flow-ui-focus-ring); }
    .fu-button:not(:disabled):active { transform: translateY(1px); }
    .fu-button[data-variant='primary'] { background: var(--flow-ui-accent); color: var(--flow-ui-on-accent); }
    .fu-button[data-variant='primary']:not(:disabled):hover { background: var(--flow-ui-accent-hover); }
    .fu-button[data-variant='primary'] img.fu-glyph { filter: var(--flow-ui-glyph-on-accent-filter); }
    .fu-button[data-variant='secondary'] { background: var(--flow-ui-card); color: var(--flow-ui-text); border-color: var(--flow-ui-border); }
    .fu-button[data-variant='secondary']:not(:disabled):hover { background: var(--flow-ui-surface-hover); }
    .fu-button[data-variant='ghost'] { background: transparent; color: var(--flow-ui-text); }
    .fu-button[data-variant='ghost']:not(:disabled):hover { background: var(--flow-ui-surface-hover); }
    .fu-button[data-variant='danger'] { background: var(--flow-ui-danger); color: #fff; }
    .fu-button[data-variant='danger']:not(:disabled):hover { filter: brightness(1.08); }
    .fu-link { color: var(--flow-ui-accent); background: none; border: 0; padding: 0; font: inherit; cursor: pointer; text-decoration: underline; text-decoration-color: color-mix(in srgb, var(--flow-ui-accent) 40%, transparent); text-underline-offset: 3px; }
    .fu-link:hover { text-decoration-color: currentColor; }
    .fu-link:focus-visible { outline: none; box-shadow: var(--flow-ui-focus-ring); border-radius: 4px; }

    /* Данные */
    .fu-table-wrap { overflow: auto; border: 1px solid var(--flow-ui-border); border-radius: var(--flow-ui-radius-lg); background: var(--flow-ui-card); }
    .fu-table { width: 100%; border-collapse: collapse; font-size: var(--flow-ui-font-size-sm); }
    .fu-table th, .fu-table td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--flow-ui-border); white-space: nowrap; }
    .fu-table tbody tr:last-child td { border-bottom: 0; }
    .fu-table th { font-size: var(--flow-ui-font-size-xs); font-weight: 650; letter-spacing: .03em; text-transform: uppercase; color: var(--flow-ui-muted); background: var(--flow-ui-surface-subtle); position: sticky; top: 0; }
    .fu-table tbody tr[data-clickable] { cursor: pointer; transition: background-color 120ms cubic-bezier(0.4, 0, 0.2, 1); } .fu-table tbody tr[data-clickable]:hover { background: var(--flow-ui-surface-hover); }
    .fu-chart { display: grid; gap: 10px; padding: 14px 16px; border: 1px solid var(--flow-ui-border); border-radius: var(--flow-ui-radius-lg); background: var(--flow-ui-card); }
    .fu-chart .title { font-size: var(--flow-ui-font-size-sm); font-weight: 600; color: var(--flow-ui-text); }
    .fu-chart svg { width: 100%; height: auto; display: block; overflow: visible; }
    .fu-chart .legend { display: flex; flex-wrap: wrap; gap: 10px; font-size: var(--flow-ui-font-size-xs); color: var(--flow-ui-muted); }
    .fu-chart .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }
    .fu-json { margin: 0; padding: 12px 14px; border-radius: var(--flow-ui-radius-md); background: var(--flow-ui-code-bg); color: var(--flow-ui-text); font: var(--flow-ui-font-size-xs)/1.55 var(--font-mono); overflow: auto; max-height: 360px; }
    .fu-card { display: grid; gap: 6px; padding: 14px 16px; border-radius: var(--flow-ui-radius-lg); border: 1px solid var(--flow-ui-border); background: var(--flow-ui-card); }
    .fu-card .head { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-weight: 600; color: var(--flow-ui-text); }
    .fu-card .head > span:first-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
    .fu-card .sub, .fu-card p { margin: 0; font-size: var(--flow-ui-font-size-sm); line-height: 1.5; color: var(--flow-ui-text-secondary); overflow-wrap: anywhere; }
    .fu-card dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 4px 0 0; font-size: var(--flow-ui-font-size-xs); }
    .fu-card dt { color: var(--flow-ui-muted); } .fu-card dd { margin: 0; color: var(--flow-ui-text); overflow-wrap: anywhere; }
    .fu-file { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border: 1px solid var(--flow-ui-border); border-radius: var(--flow-ui-radius-md); background: var(--flow-ui-card); color: var(--flow-ui-text); text-decoration: none; transition: var(--flow-ui-transition); }
    .fu-file:hover { background: var(--flow-ui-surface-hover); }
    .fu-file .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--flow-ui-font-size-sm); font-weight: 550; }
    .fu-file .meta { font-size: var(--flow-ui-font-size-xs); color: var(--flow-ui-muted); font-variant-numeric: tabular-nums; }
    .fu-file-list { display: grid; gap: 6px; }

    /* Платформенные */
    .fu-identity { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .fu-identity img {
        width: 40px; height: 40px; border-radius: 50%; object-fit: contain; flex: none;
        padding: 7px; box-sizing: border-box;
        background: var(--flow-ui-logo-disc-bg); border: 1px solid var(--flow-ui-logo-disc-border); box-shadow: var(--flow-ui-logo-disc-shadow);
    }
    .fu-avatar img { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; flex: none; background: var(--flow-ui-logo-disc-bg); }
    .fu-identity .title { font-weight: 650; font-size: var(--flow-ui-font-size-body); letter-spacing: -.01em; color: var(--flow-ui-heading); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .fu-avatar { display: inline-flex; align-items: center; gap: 10px; color: var(--flow-ui-text); }
    .fu-avatar .initials { width: 40px; height: 40px; border-radius: 50%; display: inline-grid; place-items: center; background: var(--flow-ui-accent-muted); color: var(--flow-ui-accent); font-weight: 700; font-size: var(--flow-ui-font-size-sm); }
    .fu-slot { display: grid; gap: var(--flow-ui-space-3); }
    .fu-slot > .title { font-size: var(--flow-ui-font-size-xs); font-weight: 650; color: var(--flow-ui-muted); text-transform: uppercase; letter-spacing: .06em; }
    .fu-slot-empty { padding: 18px; border: 1px dashed var(--flow-ui-border); border-radius: var(--flow-ui-radius-lg); color: var(--flow-ui-muted); font-size: var(--flow-ui-font-size-sm); text-align: center; }
    .fu-chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .fu-chip { display: inline-flex; align-items: center; gap: 7px; padding: 5px 11px; border-radius: var(--flow-ui-radius-full); background: var(--flow-ui-card); border: 1px solid var(--flow-ui-border); color: var(--flow-ui-text-secondary); font-size: var(--flow-ui-font-size-xs); font-family: inherit; line-height: 1.4; }
    .fu-chip[data-status='running'] { color: var(--flow-ui-text); border-color: color-mix(in srgb, var(--flow-ui-accent) 40%, var(--flow-ui-border)); }
    .fu-chip[data-status='running']::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--flow-ui-accent); animation: fu-pulse 1.1s ease-in-out infinite; }
    .fu-chip[data-status='error'] { background: color-mix(in srgb, var(--flow-ui-danger) 10%, transparent); border-color: color-mix(in srgb, var(--flow-ui-danger) 35%, transparent); color: var(--flow-ui-danger); }
    .fu-chip[data-status='done']::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--flow-ui-success); }
    .fu-chip .detail { color: var(--flow-ui-muted); max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    @keyframes fu-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
    .fu-prompts { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
    .fu-prompts button { padding: 9px 16px; border-radius: var(--flow-ui-radius-full); border: 1px solid var(--flow-ui-border); background: var(--flow-ui-card); color: var(--flow-ui-text); font: inherit; font-size: var(--flow-ui-font-size-sm); line-height: 1.4; text-align: left; cursor: pointer; transition: var(--flow-ui-transition); }
    .fu-prompts button:hover:not(:disabled) { background: var(--flow-ui-surface-hover); border-color: color-mix(in srgb, var(--flow-ui-text) 20%, var(--flow-ui-border)); }
    .fu-prompts button:focus-visible { outline: none; box-shadow: var(--flow-ui-focus-ring); }
    .fu-prompts button:disabled { opacity: .55; cursor: default; }
    .fu-preview img { width: 100%; border-radius: var(--flow-ui-radius-md); border: 1px solid var(--flow-ui-border); }
    .fu-reflection { padding: 10px 14px; border-left: 3px solid var(--flow-ui-accent); background: var(--flow-ui-accent-muted); border-radius: 0 var(--flow-ui-radius-md) var(--flow-ui-radius-md) 0; color: var(--flow-ui-text); font-size: var(--flow-ui-font-size-sm); line-height: 1.5; }
    .fu-html { display: block; width: 100%; border: 0; border-radius: var(--flow-ui-radius-md); background: transparent; }
    .fu-html-error, .fu-block-error { margin-top: 6px; padding: 8px 12px; border-radius: var(--flow-ui-radius-sm); background: color-mix(in srgb, var(--flow-ui-danger) 12%, transparent); color: var(--flow-ui-danger); font-size: var(--flow-ui-font-size-xs); line-height: 1.5; white-space: pre-wrap; }
    .fu-block-error { margin-top: 0; font-family: var(--font-mono); }
    .fu-block-empty { padding: 12px 14px; border: 1px dashed var(--flow-ui-border); border-radius: var(--flow-ui-radius-md); color: var(--flow-ui-muted); font-size: var(--flow-ui-font-size-xs); text-align: center; }
    .fu-trace { display: grid; gap: 4px; font-size: var(--flow-ui-font-size-xs); }
    .fu-trace li { display: flex; gap: 8px; align-items: baseline; color: var(--flow-ui-text); }
    .fu-trace .kind { color: var(--flow-ui-muted); min-width: 92px; font-family: var(--font-mono); font-size: 11.5px; }
    .fu-trace ol { margin: 0; padding: 0; list-style: none; }
    @media (prefers-reduced-motion: reduce) {
        .fu-chip[data-status='running']::before { animation: none; }
        .fu-tabs > nav button, .fu-field input, .fu-field textarea, .fu-field select, .fu-switch-track, .fu-switch-track::after, .fu-upload, .fu-button, .fu-file, .fu-prompts button { transition: none; }
    }
`;
