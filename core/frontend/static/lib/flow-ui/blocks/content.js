/** Контент: heading, text, image, video, audio, code, badge, alert, metric, progress, status, empty_state, divider. */

import { unsafeHTML } from '../../../assets/js/lit/directives/unsafe-html.min.js';
import { html, nothing } from '../../lit-shim.js';
import { flowUIMediaSrc } from '../runtime/agent-identity-image.js';
import { blockText as text, blockUrl } from '../runtime/templating.js';
import { markdownToHtml } from '../../utils/markdown.js';


function mediaSrc(ctx, template) {
    const url = blockUrl(ctx, template);
    if (url === null || url === '') return null;
    return flowUIMediaSrc(ctx.platformUiOrigin, url);
}

export const CONTENT_BLOCKS = Object.freeze({
    heading(block, ctx) {
        const value = text(ctx, block.text);
        if (value === null) return nothing;
        if (block.level === 1) return html`<h1 class="fu-heading">${value}</h1>`;
        if (block.level === 3) return html`<h3 class="fu-heading">${value}</h3>`;
        return html`<h2 class="fu-heading">${value}</h2>`;
    },

    text(block, ctx) {
        const markdown = text(ctx, block.markdown);
        if (markdown === null) return nothing;
        return html`<div class="fu-markdown">${unsafeHTML(markdownToHtml(markdown))}</div>`;
    },

    image(block, ctx) {
        const src = mediaSrc(ctx, block.url);
        if (src === null) return nothing;
        return html`<img class="fu-media" src=${src} alt=${text(ctx, block.alt) ?? ''} loading="lazy">`;
    },

    video(block, ctx) {
        const src = mediaSrc(ctx, block.url);
        if (src === null) return nothing;
        return html`<video class="fu-media" src=${src} controls preload="metadata"></video>`;
    },

    audio(block, ctx) {
        const src = mediaSrc(ctx, block.url);
        if (src === null) return nothing;
        return html`<audio class="fu-media" src=${src} controls preload="metadata"></audio>`;
    },

    code(block, ctx) {
        const code = text(ctx, block.code);
        if (code === null) return nothing;
        return html`<pre class="fu-code" data-language=${block.language}><code>${code}</code></pre>`;
    },

    badge(block, ctx) {
        const label = text(ctx, block.label);
        if (label === null) return nothing;
        return html`<span class="fu-badge" data-tone=${block.tone}>${label}</span>`;
    },

    alert(block, ctx) {
        const title = text(ctx, block.title);
        const message = text(ctx, block.message);
        if (title === null || message === null) return nothing;
        return html`<div class="fu-alert" role="status" data-tone=${block.tone}>
            ${title !== '' ? html`<strong>${title}</strong>` : ''}
            ${message !== '' ? html`<p>${message}</p>` : ''}
        </div>`;
    },

    metric(block, ctx) {
        const label = text(ctx, block.label);
        const value = text(ctx, block.value);
        const hint = text(ctx, block.hint);
        if (label === null || value === null || hint === null) return nothing;
        return html`<div class="fu-metric">
            <span class="label">${label}</span>
            <span class="value">${value}</span>
            ${hint !== '' ? html`<span class="hint">${hint}</span>` : ''}
        </div>`;
    },

    progress(block, ctx) {
        const label = text(ctx, block.label);
        const raw = text(ctx, block.value);
        if (label === null || raw === null) return nothing;
        const value = Number(raw);
        if (!Number.isFinite(value)) {
            // На холсте неразрешённый шаблон ``{progress}`` — это ещё не данные, а не ошибка автора
            if (ctx.editing) return nothing;
            throw new Error(`flow-ui: progress value is not a number: ${JSON.stringify(raw)}`);
        }
        return html`<div class="fu-progress">
            <span>${label}</span>
            <progress max=${block.max} value=${Math.min(Math.max(value, 0), block.max)}></progress>
        </div>`;
    },

    status(block, ctx) {
        const label = text(ctx, block.label);
        if (label === null) return nothing;
        return html`<span class="fu-status" data-tone=${block.tone}>${label}</span>`;
    },

    empty_state(block, ctx) {
        const title = text(ctx, block.title);
        const message = text(ctx, block.message);
        if (title === null || message === null) return nothing;
        return html`<div class="fu-empty"><strong>${title}</strong>${message !== '' ? html`<span>${message}</span>` : ''}</div>`;
    },

    divider() {
        return html`<hr class="fu-divider">`;
    },
});
