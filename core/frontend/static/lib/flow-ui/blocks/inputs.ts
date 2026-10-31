/**
 * Поля ввода. Значение поля — ``ctx.fieldValue(field)`` (локальная правка поверх проекции state),
 * изменение — ``ctx.onFieldChange(field, value)``; ``action`` поля отправляется по Enter/изменению.
 */

import { html, nothing } from 'lit';
import { blockText as text } from '../runtime/templating.js';
import { flowUIText } from '../utils/text.js';
import { formatFileSize } from '../../utils/format-file-size.js';
import { flowUIGlyph } from '../utils/glyph.js';
import type { FlowUiBlock, FlowUiBlockRenderer, FlowUiRenderContext } from '../runtime/flow-ui-store.js';
import { isPlainRecord } from '../../events/payload.js';

function controlValue(event: Event): string {
    const target = event.target;
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) {
        return target.value;
    }
    throw new Error('flow-ui input: control required');
}

function inputElement(event: Event): HTMLInputElement {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
        throw new Error('flow-ui input: control required');
    }
    return target;
}

function selectElement(event: Event): HTMLSelectElement {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        throw new Error('flow-ui input: select required');
    }
    return target;
}

function fileRecord(file: unknown): Record<string, unknown> {
    if (!isPlainRecord(file)) {
        throw new Error('flow-ui input: file must be an object');
    }
    return file;
}


function shown(value: string | null): string {
    return value === null ? '' : value;
}

function fieldShell(block: FlowUiBlock, ctx: FlowUiRenderContext, control: unknown, { inline = false }: { inline?: boolean } = {}) {
    const label = shown(text(ctx, block.label));
    const error = ctx.fieldErrors.has(String(block.field)) ? shown(text(ctx, block.error_message)) : '';
    const errorText = error !== '' ? error : (ctx.fieldErrors.has(String(block.field)) ? flowUIText(ctx.locale, 'field_required') : '');
    return html`<div class="fu-field" data-field=${block.field} data-invalid=${errorText !== '' ? 'true' : nothing}>
        ${inline || label === '' ? '' : html`<label for=${`fu-${block.block_id}`}>${label}${block.required ? html`<span class="req">*</span>` : ''}</label>`}
        ${control}
        ${errorText !== '' ? html`<span class="error" role="alert">${errorText}</span>` : ''}
    </div>`;
}

function currentValue(block: FlowUiBlock, ctx: FlowUiRenderContext, fallback: unknown) {
    const value = ctx.fieldValue(block.field);
    return value === undefined || value === null ? fallback : value;
}

function commit(block: FlowUiBlock, ctx: FlowUiRenderContext, value: unknown) {
    ctx.onFieldChange(block.field, value);
    if (block.action) ctx.onAction(block, block.action);
}

function onEnter(block: FlowUiBlock, ctx: FlowUiRenderContext) {
    return (event: KeyboardEvent) => {
        if (event.key !== 'Enter' || block.multiline || !block.action) return;
        event.preventDefault();
        ctx.onAction(block, block.action);
    };
}

export const INPUT_BLOCKS: Readonly<Record<string, FlowUiBlockRenderer>> = Object.freeze({
    text_input(block, ctx) {
        const value = currentValue(block, ctx, shown(text(ctx, block.default)));
        const placeholder = shown(text(ctx, block.placeholder));
        const control = block.multiline
            ? html`<textarea id=${`fu-${block.block_id}`} .value=${String(value)} placeholder=${placeholder}
                ?disabled=${ctx.readonly} ?required=${block.required}
                @input=${(event: Event) => ctx.onFieldChange(block.field, controlValue(event))}></textarea>`
            : html`<input id=${`fu-${block.block_id}`} type=${block.secret ? 'password' : 'text'} .value=${String(value)}
                placeholder=${placeholder} pattern=${block.pattern !== '' ? block.pattern : nothing}
                ?disabled=${ctx.readonly} ?required=${block.required}
                @input=${(event: Event) => ctx.onFieldChange(block.field, controlValue(event))}
                @keydown=${onEnter(block, ctx)}>`;
        return fieldShell(block, ctx, control);
    },

    number_input(block, ctx) {
        const value = currentValue(block, ctx, block.default);
        return fieldShell(block, ctx, html`<input id=${`fu-${block.block_id}`} type="number"
            .value=${value === null || value === undefined ? '' : String(value)}
            placeholder=${shown(text(ctx, block.placeholder))}
            min=${block.min ?? nothing} max=${block.max ?? nothing} step=${block.step}
            ?disabled=${ctx.readonly} ?required=${block.required}
            @input=${(event: Event) => ctx.onFieldChange(block.field, controlValue(event) === '' ? null : Number(controlValue(event)))}
            @keydown=${onEnter(block, ctx)}>`);
    },

    select(block, ctx) {
        const value = currentValue(block, ctx, block.default ?? (block.multiple ? [] : ''));
        const selected = block.multiple ? new Set(Array.isArray(value) ? value : [value]) : new Set([String(value)]);
        const placeholder = shown(text(ctx, block.placeholder));
        return fieldShell(block, ctx, html`<select id=${`fu-${block.block_id}`} ?multiple=${block.multiple}
            ?disabled=${ctx.readonly} ?required=${block.required}
            @change=${(event: Event) => {
                const picked = [...selectElement(event).selectedOptions].map((option) => option.value);
                const option = picked[0];
                commit(block, ctx, block.multiple ? picked : (option === undefined ? '' : option));
            }}>
            ${!block.multiple && placeholder !== '' ? html`<option value="" ?selected=${selected.has('')} disabled>${placeholder}</option>` : ''}
            ${(Array.isArray(block.options) ? block.options : []).map((option: { value?: unknown; label?: unknown }) => html`<option value=${String(option.value)} ?selected=${selected.has(String(option.value))}>${text(ctx, option.label) ?? option.value}</option>`)}
        </select>`);
    },

    checkbox(block, ctx) {
        const checked = currentValue(block, ctx, block.default) === true;
        return fieldShell(block, ctx, html`<label class="fu-toggle">
            <input type="checkbox" .checked=${checked} ?disabled=${ctx.readonly}
                @change=${(event: Event) => commit(block, ctx, inputElement(event).checked)}>
            <span>${shown(text(ctx, block.label))}${block.required ? html`<span class="req">*</span>` : ''}</span>
        </label>`, { inline: true });
    },

    switch(block, ctx) {
        const checked = currentValue(block, ctx, block.default) === true;
        return fieldShell(block, ctx, html`<label class="fu-toggle">
            <input class="visually-hidden" type="checkbox" role="switch" .checked=${checked} ?disabled=${ctx.readonly}
                @change=${(event: Event) => commit(block, ctx, inputElement(event).checked)}>
            <span class="fu-switch-track"></span>
            <span>${shown(text(ctx, block.label))}</span>
        </label>`, { inline: true });
    },

    slider(block, ctx) {
        const value = currentValue(block, ctx, block.default ?? block.min);
        return fieldShell(block, ctx, html`<div class="fu-slider-row">
            <input id=${`fu-${block.block_id}`} type="range" min=${block.min} max=${block.max} step=${block.step}
                .value=${String(value)} ?disabled=${ctx.readonly}
                @input=${(event: Event) => ctx.onFieldChange(block.field, Number(controlValue(event)))}
                @change=${(event: Event) => commit(block, ctx, Number(controlValue(event)))}>
            <output>${String(value)}</output>
        </div>`);
    },

    date_input(block, ctx) {
        const value = currentValue(block, ctx, shown(text(ctx, block.default)));
        return fieldShell(block, ctx, html`<input id=${`fu-${block.block_id}`} type="date" .value=${String(value)}
            ?disabled=${ctx.readonly} ?required=${block.required}
            @change=${(event: Event) => commit(block, ctx, controlValue(event))}>`);
    },

    datetime_input(block, ctx) {
        const value = currentValue(block, ctx, shown(text(ctx, block.default)));
        return fieldShell(block, ctx, html`<input id=${`fu-${block.block_id}`} type="datetime-local" .value=${String(value)}
            ?disabled=${ctx.readonly} ?required=${block.required}
            @change=${(event: Event) => commit(block, ctx, controlValue(event))}>`);
    },

    file_upload(block, ctx) {
        const files = currentValue(block, ctx, []);
        const list = Array.isArray(files) ? files : [files];
        return fieldShell(block, ctx, html`<label class="fu-upload">
            <span>${flowUIText(ctx.locale, 'file_upload_hint')}</span>
            <input type="file" ?multiple=${block.multiple} accept=${block.accept !== '' && block.accept !== undefined ? String(block.accept) : nothing}
                ?disabled=${ctx.readonly || ctx.uploading.has(String(block.field))} hidden
                @change=${(event: Event) => {
                    const input = inputElement(event);
                    const picked = input.files === null ? [] : [...input.files];
                    input.value = '';
                    if (picked.length > 0) ctx.onFilesSelected(block, picked);
                }}>
            ${ctx.uploading.has(String(block.field)) ? html`<span>${flowUIText(ctx.locale, 'file_uploading')}</span>` : ''}
            ${list.length > 0 ? html`<ul>${list.map((file) => {
                const record = fileRecord(file);
                const size = record.file_size;
                return html`<li>${record.original_name} · ${formatFileSize(typeof size === 'number' ? size : 0)}</li>`;
            })}</ul>` : ''}
        </label>`);
    },

    voice_input(block, ctx) {
        const value = currentValue(block, ctx, '');
        const active = ctx.host.voiceSessionActive === true;
        return fieldShell(block, ctx, html`<div class="fu-control-row">
            <input id=${`fu-${block.block_id}`} type="text" .value=${String(value)} placeholder=${shown(text(ctx, block.placeholder))}
                ?disabled=${ctx.readonly} ?required=${block.required}
                @input=${(event: Event) => ctx.onFieldChange(block.field, controlValue(event))}
                @keydown=${onEnter(block, ctx)}>
            <button type="button" class="fu-button" data-variant=${active ? 'danger' : 'secondary'}
                aria-pressed=${active ? 'true' : 'false'}
                ?disabled=${ctx.readonly || !ctx.host.voiceSessionReady()}
                title=${flowUIText(ctx.locale, active ? 'voice_stop' : 'voice_start')}
                @click=${() => ctx.host.toggleVoiceSession()}>${flowUIGlyph(active ? 'mic-off' : 'mic', 18, ctx.platformUiOrigin)}</button>
        </div>`);
    },
});
