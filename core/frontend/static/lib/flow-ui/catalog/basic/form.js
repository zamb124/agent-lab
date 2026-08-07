import { html } from '../../../lit-shim.js';
import { FLOW_UI_ACTIONS } from '../../protocol/constants.js';
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

function isSubmitPressAction(component) {
    const press = component?.actions?.press;
    return press?.kind === 'event' && press?.name === FLOW_UI_ACTIONS.submit;
}

export function renderButton(host, component) {
    const label = labelOfComponent(host, component) || flowUIText(host.locale, 'submit_default');
    const variant = optionalComponentProperty(component, 'variant');
    const presentation = optionalComponentProperty(component, 'presentation');
    const disabled = optionalComponentProperty(component, 'disabled') === true || host.readonly;
    if (presentation === 'composer') {
        const composerState = optionalComponentProperty(component, 'composerState');
        if (composerState === 'stop') {
            return wrapFlowNode(
                host,
                component,
                html`<button
                        type="button"
                        class="circle-btn send composer-stop"
                        ?disabled=${host.readonly}
                        aria-label=${flowUIText(host.locale, 'composer_stop')}
                        title=${flowUIText(host.locale, 'composer_stop')}
                        @click=${() => host.controller?.cancelActiveTask()}
                    ><span class="composer-stop-square" aria-hidden="true"></span></button>`,
            );
        }
        if (composerState === 'busy') {
            return wrapFlowNode(
                host,
                component,
                html`<button
                        type="button"
                        class="circle-btn send"
                        disabled
                        aria-busy="true"
                        aria-label=${flowUIText(host.locale, 'composer_sending')}
                        title=${flowUIText(host.locale, 'composer_sending')}
                    ><span class="composer-spinner" aria-hidden="true"></span></button>`,
            );
        }
        return wrapFlowNode(
            host,
            component,
            html`<button
                    type="button"
                    class="circle-btn send"
                    ?disabled=${disabled}
                    aria-label=${flowUIText(host.locale, 'composer_send')}
                    title=${flowUIText(host.locale, 'composer_send')}
                    @click=${() => host._action(component, 'press')}
                >${flowUIGlyph('send', 18)}</button>`,
        );
    }
    const submitting = isSubmitPressAction(component)
        && host.controller?.activeContext?.submitting === true;
    return wrapFlowNode(
        host,
        component,
        html`<button
            class=${variant === 'secondary' ? 'secondary' : ''}
            ?disabled=${disabled || submitting}
            aria-busy=${submitting ? 'true' : 'false'}
            @click=${() => host._action(component, 'press')}
        >${submitting
            ? html`<span class="button-spinner" aria-hidden="true"></span><span>${label}</span>`
            : label}</button>`,
    );
}

export function renderTextField(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const placeholder = optionalComponentProperty(component, 'placeholder');
    const required = componentHasRequiredCheck(component);
    const invalid = componentFieldError(host, component) !== '';
    return wrapFlowNode(
        host,
        component,
        html`<label>${renderInputLabelText(host, component, label)}<input
            type="text"
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

export function renderCheckBox(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const required = componentHasRequiredCheck(component);
    const invalid = componentFieldError(host, component) !== '';
    return wrapFlowNode(
        host,
        component,
        html`<label><span><input
            type="checkbox"
            .checked=${value === true}
            ?disabled=${host.readonly}
            ?required=${required}
            aria-required=${required ? 'true' : 'false'}
            aria-invalid=${invalid ? 'true' : 'false'}
            @change=${(event) => host._change(component, 'value', event.target.checked)}
        > ${renderInputLabelText(host, component, label)}</span>${renderFieldError(host, component)}</label>`,
    );
}

export function renderChoicePicker(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const options = resolveBound(host.surface, component, 'options', host.tasks)
        ?? optionalComponentProperty(component, 'options');
    if (options != null && !Array.isArray(options)) {
        throw new Error(`flow-ui: ChoicePicker ${component.component_id} options must be an array`);
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

export function renderSlider(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const min = optionalComponentProperty(component, 'min');
    const max = optionalComponentProperty(component, 'max');
    return wrapFlowNode(
        host,
        component,
        html`<label>${label}<input
            class="progress"
            type="range"
            min=${min == null ? 0 : Number(min)}
            max=${max == null ? 100 : Number(max)}
            .value=${String(value ?? 0)}
            ?disabled=${host.readonly}
            @input=${(event) => host._change(component, 'value', Number(event.target.value))}
        ></label>`,
    );
}

export function renderDateTimeInput(host, component) {
    const label = labelOfComponent(host, component);
    const value = resolveBound(host.surface, component, 'value', host.tasks);
    const placeholder = optionalComponentProperty(component, 'placeholder');
    const required = componentHasRequiredCheck(component);
    const invalid = componentFieldError(host, component) !== '';
    return wrapFlowNode(
        host,
        component,
        html`<label>${renderInputLabelText(host, component, label)}<input
            type="datetime-local"
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

export function registerBasicForm(register) {
    register('Button', renderButton);
    register('TextField', renderTextField);
    register('CheckBox', renderCheckBox);
    register('ChoicePicker', renderChoicePicker);
    register('Slider', renderSlider);
    register('DateTimeInput', renderDateTimeInput);
}
