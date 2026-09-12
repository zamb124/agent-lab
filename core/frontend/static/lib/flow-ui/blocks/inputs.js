/**
 * Поля ввода. Значение поля — ``ctx.fieldValue(field)`` (локальная правка поверх проекции state),
 * изменение — ``ctx.onFieldChange(field, value)``; ``action`` поля отправляется по Enter/изменению.
 */

import { html, nothing } from '../../lit-shim.js';
import { blockText as text } from '../runtime/templating.js';
import { flowUIText } from '../utils/text.js';
import { formatFileSize } from '../../utils/format-file-size.js';
import { flowUIGlyph } from '../utils/glyph.js';


function fieldShell(block, ctx, control, { inline = false } = {}) {
    const label = text(ctx, block.label) ?? '';
    const error = ctx.fieldErrors.has(block.field) ? (text(ctx, block.error_message) ?? '') : '';
    const errorText = error !== '' ? error : (ctx.fieldErrors.has(block.field) ? flowUIText(ctx.locale, 'field_required') : '');
    return html`<div class="fu-field" data-field=${block.field} data-invalid=${errorText !== '' ? 'true' : nothing}>
        ${inline || label === '' ? '' : html`<label for=${`fu-${block.block_id}`}>${label}${block.required ? html`<span class="req">*</span>` : ''}</label>`}
        ${control}
        ${errorText !== '' ? html`<span class="error" role="alert">${errorText}</span>` : ''}
    </div>`;
}

function currentValue(block, ctx, fallback) {
    const value = ctx.fieldValue(block.field);
    return value === undefined || value === null ? fallback : value;
}

function commit(block, ctx, value) {
    ctx.onFieldChange(block.field, value);
    if (block.action) ctx.onAction(block, block.action);
}

function onEnter(block, ctx) {
    return (event) => {
        if (event.key !== 'Enter' || block.multiline || !block.action) return;
        event.preventDefault();
        ctx.onAction(block, block.action);
    };
}

export const INPUT_BLOCKS = Object.freeze({
    text_input(block, ctx) {
        const value = currentValue(block, ctx, text(ctx, block.default) ?? '');
        const placeholder = text(ctx, block.placeholder) ?? '';
        const control = block.multiline
            ? html`<textarea id=${`fu-${block.block_id}`} .value=${String(value)} placeholder=${placeholder}
                ?disabled=${ctx.readonly} ?required=${block.required}
                @input=${(event) => ctx.onFieldChange(block.field, event.target.value)}></textarea>`
            : html`<input id=${`fu-${block.block_id}`} type=${block.secret ? 'password' : 'text'} .value=${String(value)}
                placeholder=${placeholder} pattern=${block.pattern !== '' ? block.pattern : nothing}
                ?disabled=${ctx.readonly} ?required=${block.required}
                @input=${(event) => ctx.onFieldChange(block.field, event.target.value)}
                @keydown=${onEnter(block, ctx)}>`;
        return fieldShell(block, ctx, control);
    },

    number_input(block, ctx) {
        const value = currentValue(block, ctx, block.default);
        return fieldShell(block, ctx, html`<input id=${`fu-${block.block_id}`} type="number"
            .value=${value === null || value === undefined ? '' : String(value)}
            placeholder=${text(ctx, block.placeholder) ?? ''}
            min=${block.min ?? nothing} max=${block.max ?? nothing} step=${block.step}
            ?disabled=${ctx.readonly} ?required=${block.required}
            @input=${(event) => ctx.onFieldChange(block.field, event.target.value === '' ? null : Number(event.target.value))}
            @keydown=${onEnter(block, ctx)}>`);
    },

    select(block, ctx) {
        const value = currentValue(block, ctx, block.default ?? (block.multiple ? [] : ''));
        const selected = block.multiple ? new Set(Array.isArray(value) ? value : [value]) : new Set([String(value)]);
        const placeholder = text(ctx, block.placeholder) ?? '';
        return fieldShell(block, ctx, html`<select id=${`fu-${block.block_id}`} ?multiple=${block.multiple}
            ?disabled=${ctx.readonly} ?required=${block.required}
            @change=${(event) => {
                const picked = [...event.target.selectedOptions].map((option) => option.value);
                commit(block, ctx, block.multiple ? picked : (picked[0] ?? ''));
            }}>
            ${!block.multiple && placeholder !== '' ? html`<option value="" ?selected=${selected.has('')} disabled>${placeholder}</option>` : ''}
            ${block.options.map((option) => html`<option value=${option.value} ?selected=${selected.has(option.value)}>${text(ctx, option.label) ?? option.value}</option>`)}
        </select>`);
    },

    checkbox(block, ctx) {
        const checked = currentValue(block, ctx, block.default) === true;
        return fieldShell(block, ctx, html`<label class="fu-toggle">
            <input type="checkbox" .checked=${checked} ?disabled=${ctx.readonly}
                @change=${(event) => commit(block, ctx, event.target.checked)}>
            <span>${text(ctx, block.label) ?? ''}${block.required ? html`<span class="req">*</span>` : ''}</span>
        </label>`, { inline: true });
    },

    switch(block, ctx) {
        const checked = currentValue(block, ctx, block.default) === true;
        return fieldShell(block, ctx, html`<label class="fu-toggle">
            <input class="visually-hidden" type="checkbox" role="switch" .checked=${checked} ?disabled=${ctx.readonly}
                @change=${(event) => commit(block, ctx, event.target.checked)}>
            <span class="fu-switch-track"></span>
            <span>${text(ctx, block.label) ?? ''}</span>
        </label>`, { inline: true });
    },

    slider(block, ctx) {
        const value = currentValue(block, ctx, block.default ?? block.min);
        return fieldShell(block, ctx, html`<div class="fu-slider-row">
            <input id=${`fu-${block.block_id}`} type="range" min=${block.min} max=${block.max} step=${block.step}
                .value=${String(value)} ?disabled=${ctx.readonly}
                @input=${(event) => ctx.onFieldChange(block.field, Number(event.target.value))}
                @change=${(event) => commit(block, ctx, Number(event.target.value))}>
            <output>${String(value)}</output>
        </div>`);
    },

    date_input(block, ctx) {
        const value = currentValue(block, ctx, text(ctx, block.default) ?? '');
        return fieldShell(block, ctx, html`<input id=${`fu-${block.block_id}`} type="date" .value=${String(value)}
            ?disabled=${ctx.readonly} ?required=${block.required}
            @change=${(event) => commit(block, ctx, event.target.value)}>`);
    },

    datetime_input(block, ctx) {
        const value = currentValue(block, ctx, text(ctx, block.default) ?? '');
        return fieldShell(block, ctx, html`<input id=${`fu-${block.block_id}`} type="datetime-local" .value=${String(value)}
            ?disabled=${ctx.readonly} ?required=${block.required}
            @change=${(event) => commit(block, ctx, event.target.value)}>`);
    },

    file_upload(block, ctx) {
        const files = currentValue(block, ctx, []);
        const list = Array.isArray(files) ? files : [files];
        return fieldShell(block, ctx, html`<label class="fu-upload">
            <span>${flowUIText(ctx.locale, 'file_upload_hint')}</span>
            <input type="file" ?multiple=${block.multiple} accept=${block.accept !== '' ? block.accept : nothing}
                ?disabled=${ctx.readonly || ctx.uploading.has(block.field)} hidden
                @change=${(event) => {
                    const picked = [...event.target.files];
                    event.target.value = '';
                    if (picked.length > 0) ctx.onFilesSelected(block, picked);
                }}>
            ${ctx.uploading.has(block.field) ? html`<span>${flowUIText(ctx.locale, 'file_uploading')}</span>` : ''}
            ${list.length > 0 ? html`<ul>${list.map((file) => html`<li>${file.original_name} · ${formatFileSize(file.file_size ?? 0)}</li>`)}</ul>` : ''}
        </label>`);
    },

    voice_input(block, ctx) {
        const value = currentValue(block, ctx, '');
        const active = ctx.host.voiceSessionActive === true;
        return fieldShell(block, ctx, html`<div class="fu-control-row">
            <input id=${`fu-${block.block_id}`} type="text" .value=${String(value)} placeholder=${text(ctx, block.placeholder) ?? ''}
                ?disabled=${ctx.readonly} ?required=${block.required}
                @input=${(event) => ctx.onFieldChange(block.field, event.target.value)}
                @keydown=${onEnter(block, ctx)}>
            <button type="button" class="fu-button" data-variant=${active ? 'danger' : 'secondary'}
                aria-pressed=${active ? 'true' : 'false'}
                ?disabled=${ctx.readonly || !ctx.host.voiceSessionReady()}
                title=${flowUIText(ctx.locale, active ? 'voice_stop' : 'voice_start')}
                @click=${() => ctx.host.toggleVoiceSession()}>${flowUIGlyph(active ? 'mic-off' : 'mic', 18, ctx.platformUiOrigin)}</button>
        </div>`);
    },
});
