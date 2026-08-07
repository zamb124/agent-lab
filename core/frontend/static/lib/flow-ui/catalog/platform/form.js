import { html, nothing } from '../../../lit-shim.js';
import { flowUIGlyph } from '../flow-ui-glyph.js';
import {
    componentFieldError,
    componentHasRequiredCheck,
    labelOfComponent,
    localizedText,
    optionalComponentProperty,
    renderFieldError,
    renderInputLabelText,
    resolveBound,
    wrapFlowNode,
} from '../render-helpers.js';
import { flowUIText } from '../../utils/text.js';

export function renderSelect(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const options = resolveBound(host.surface, component, 'options', host.tasks)
        ?? optionalComponentProperty(component, 'options');
    if (options != null && !Array.isArray(options)) {
        throw new Error(`flow-ui: Select ${component.component_id} options must be an array`);
    }
    const list = Array.isArray(options) ? options : [];
    const required = componentHasRequiredCheck(component);
    const invalid = componentFieldError(host, component) !== '';
    return wrapFlowNode(
        host,
        component,
        html`<label>${renderInputLabelText(host, component, label)}<select
            .value=${String(value ?? '')}
            ?disabled=${host.readonly}
            ?required=${required}
            aria-required=${required ? 'true' : 'false'}
            aria-invalid=${invalid ? 'true' : 'false'}
            @change=${(event) => host._change(component, 'value', event.target.value)}
        >${list.map((item) => {
            const optionValue = typeof item === 'object' ? item.value : item;
            const optionLabel = typeof item === 'object'
                ? localizedText(item.label ?? item.value)
                : String(item);
            return html`<option value=${String(optionValue)}>${optionLabel}</option>`;
        })}</select>${renderFieldError(host, component)}</label>`,
    );
}

export function renderTextArea(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const rows = optionalComponentProperty(component, 'rows');
    const placeholder = optionalComponentProperty(component, 'placeholder');
    const required = componentHasRequiredCheck(component);
    const invalid = componentFieldError(host, component) !== '';
    // Composer TextArea is owned by Form(presentation=composer) in layout.js.
    return wrapFlowNode(
        host,
        component,
        html`<label>${renderInputLabelText(host, component, label)}<textarea
            .value=${String(value ?? '')}
            rows=${rows == null ? 3 : Number(rows)}
            placeholder=${placeholder == null ? '' : String(placeholder)}
            ?readonly=${host.readonly}
            ?required=${required}
            aria-required=${required ? 'true' : 'false'}
            aria-invalid=${invalid ? 'true' : 'false'}
            @input=${(event) => host._change(component, 'value', event.target.value)}
        ></textarea>${renderFieldError(host, component)}</label>`,
    );
}

export function renderNumberField(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const placeholder = optionalComponentProperty(component, 'placeholder');
    const required = componentHasRequiredCheck(component);
    const invalid = componentFieldError(host, component) !== '';
    return wrapFlowNode(
        host,
        component,
        html`<label>${renderInputLabelText(host, component, label)}<input
            type="number"
            .value=${String(value ?? '')}
            placeholder=${placeholder == null ? '' : String(placeholder)}
            ?readonly=${host.readonly}
            ?required=${required}
            aria-required=${required ? 'true' : 'false'}
            aria-invalid=${invalid ? 'true' : 'false'}
            @input=${(event) => host._change(component, 'value', Number(event.target.value))}
        >${renderFieldError(host, component)}</label>`,
    );
}

export function renderDatePicker(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const placeholder = optionalComponentProperty(component, 'placeholder');
    const required = componentHasRequiredCheck(component);
    const invalid = componentFieldError(host, component) !== '';
    return wrapFlowNode(
        host,
        component,
        html`<label>${renderInputLabelText(host, component, label)}<input
            type="date"
            .value=${String(value ?? '')}
            placeholder=${placeholder == null ? '' : String(placeholder)}
            ?readonly=${host.readonly}
            ?required=${required}
            aria-required=${required ? 'true' : 'false'}
            aria-invalid=${invalid ? 'true' : 'false'}
            @input=${(event) => host._change(component, 'value', event.target.value)}
        >${renderFieldError(host, component)}</label>`,
    );
}

function fileRefDisplayName(ref) {
    if (!ref || typeof ref !== 'object') {
        throw new Error('flow-ui: FileUpload value item must be a FileRef object');
    }
    if (typeof ref.original_name === 'string' && ref.original_name.trim() !== '') {
        return ref.original_name;
    }
    if (typeof ref.filename === 'string' && ref.filename.trim() !== '') {
        return ref.filename;
    }
    if (typeof ref.file_id === 'string' && ref.file_id.trim() !== '') {
        return ref.file_id;
    }
    throw new Error('flow-ui: FileRef missing original_name/filename/file_id');
}

export function renderFileUpload(host, component) {
    // Composer FileUpload is owned by Form(presentation=composer) in layout.js.
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const upload = host.uploadState?.[component.component_id];
    const busy = upload?.busy === true;
    const uploadError = typeof upload?.error === 'string' ? upload.error : '';
    const refs = Array.isArray(value) ? value : [];
    const multiple = optionalComponentProperty(component, 'multiple') !== false;
    const disabled = host.readonly || busy;
    const inputId = `flow-ui-file-${component.component_id}`;
    const required = componentHasRequiredCheck(component);
    const fieldError = componentFieldError(host, component);
    const title = label == null || label === ''
        ? flowUIText(host.locale, 'attach_files')
        : label;
    const openPicker = () => {
        if (disabled) return;
        const input = host.renderRoot?.getElementById(inputId);
        if (!input) {
            throw new Error(`flow-ui: file input ${inputId} missing`);
        }
        input.click();
    };
    return wrapFlowNode(
        host,
        component,
        html`<div class="file-upload">
            <input
                id=${inputId}
                class="file-upload-input"
                type="file"
                ?multiple=${multiple}
                ?disabled=${disabled}
                ?required=${required}
                aria-required=${required ? 'true' : 'false'}
                aria-invalid=${fieldError !== '' ? 'true' : 'false'}
                @change=${(event) => host._upload(component, event)}
            >
            <button
                type="button"
                class="file-upload-dropzone"
                ?disabled=${disabled}
                aria-label=${required ? `${title} *` : title}
                @click=${openPicker}
                @dragenter=${(event) => {
                    event.preventDefault();
                    if (!disabled) event.currentTarget.dataset.drag = 'true';
                }}
                @dragover=${(event) => {
                    event.preventDefault();
                    if (!disabled) event.currentTarget.dataset.drag = 'true';
                }}
                @dragleave=${(event) => {
                    event.preventDefault();
                    event.currentTarget.dataset.drag = 'false';
                }}
                @drop=${(event) => {
                    event.preventDefault();
                    event.currentTarget.dataset.drag = 'false';
                    if (disabled) return;
                    const dropped = Array.from(event.dataTransfer?.files || []);
                    if (dropped.length === 0) return;
                    void host._upload(component, multiple ? dropped : dropped.slice(0, 1));
                }}
            >
                <span class="file-upload-icon" aria-hidden="true">${flowUIGlyph('paperclip', 22)}</span>
                <span class="file-upload-copy">
                    <strong class="file-upload-title">${renderInputLabelText(host, component, title)}</strong>
                    <span class="file-upload-hint">${flowUIText(
                        host.locale,
                        busy ? 'uploading' : 'file_upload_hint',
                    )}</span>
                </span>
                ${busy
                    ? html`<span class="file-upload-spinner" aria-hidden="true"></span>`
                    : html`<span class="file-upload-cta">${flowUIText(host.locale, 'file_upload_browse')}</span>`}
            </button>
            ${refs.length > 0 ? html`<div class="file-upload-list" role="list">
                ${refs.map((ref) => html`<span class="composer-file-chip" role="listitem">
                    ${flowUIGlyph('file', 14)}
                    <span class="composer-file-name">${fileRefDisplayName(ref)}</span>
                    ${host.readonly ? nothing : html`<button
                        type="button"
                        class="composer-file-remove"
                        aria-label=${flowUIText(host.locale, 'remove_file', { name: fileRefDisplayName(ref) })}
                        @click=${() => host._removeUploadedFile(component, ref.file_id)}
                    >${flowUIGlyph('x', 12)}</button>`}
                </span>`)}
            </div>` : nothing}
            ${uploadError !== '' ? html`<span class="upload-error">${uploadError}</span>` : nothing}
            ${renderFieldError(host, component)}
        </div>`,
    );
}

export function renderSwitch(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const required = componentHasRequiredCheck(component);
    const invalid = componentFieldError(host, component) !== '';
    return wrapFlowNode(
        host,
        component,
        html`<label><span><input
            type="checkbox"
            role="switch"
            .checked=${value === true}
            ?disabled=${host.readonly}
            ?required=${required}
            aria-required=${required ? 'true' : 'false'}
            aria-invalid=${invalid ? 'true' : 'false'}
            @change=${(event) => host._change(component, 'value', event.target.checked)}
        > ${renderInputLabelText(host, component, label)}</span>${renderFieldError(host, component)}</label>`,
    );
}

export function registerPlatformForm(register) {
    register('Select', renderSelect);
    register('TextArea', renderTextArea);
    register('NumberField', renderNumberField);
    register('DatePicker', renderDatePicker);
    register('FileUpload', renderFileUpload);
    register('Switch', renderSwitch);
}
