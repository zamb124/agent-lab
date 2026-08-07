/**
 * Quick props for the per-component kebab menu.
 * Only boolean / enum fields from catalog editor.schema, plus synthetic
 * `__required` for input types that already support Validation in the inspector.
 * No invented fields.
 */
import { FLOW_UI_CATALOG_MANIFEST } from '../catalog/manifest.js';

/** Same set as flows-interface-inspector Validation section. */
export const FLOW_UI_VALIDATION_INPUT_TYPES = Object.freeze(new Set([
    'TextField',
    'TextArea',
    'NumberField',
    'Select',
    'CheckBox',
    'ChoicePicker',
    'DatePicker',
    'DateTimeInput',
    'FileUpload',
    'Switch',
]));

export const FLOW_UI_QUICK_REQUIRED_NAME = '__required';

/**
 * @param {unknown} options
 * @returns {readonly { value: string, label: { ru: string, en: string } }[]}
 */
function normalizeEnumOptions(options) {
    if (!Array.isArray(options)) return Object.freeze([]);
    return Object.freeze(options.map((option) => {
        if (option != null && typeof option === 'object' && !Array.isArray(option)) {
            const value = option.value;
            const label = option.label;
            if (value == null) {
                throw new Error('flow-ui quick-props: enum option.value required');
            }
            const valueText = String(value);
            if (label != null && typeof label === 'object' && !Array.isArray(label)) {
                return Object.freeze({
                    value: valueText,
                    label: Object.freeze({
                        ru: typeof label.ru === 'string' ? label.ru : valueText,
                        en: typeof label.en === 'string' ? label.en : valueText,
                    }),
                });
            }
            return Object.freeze({
                value: valueText,
                label: Object.freeze({ ru: valueText, en: valueText }),
            });
        }
        const valueText = String(option);
        return Object.freeze({
            value: valueText,
            label: Object.freeze({ ru: valueText, en: valueText }),
        });
    }));
}

/**
 * @param {string} type
 * @returns {readonly {
 *   name: string,
 *   kind: 'boolean' | 'enum',
 *   options?: readonly { value: string, label: { ru: string, en: string } }[],
 *   labelKey: string,
 *   schemaLabel: { ru: string, en: string } | null,
 * }[]}
 */
export function flowUIComponentQuickProps(type) {
    if (typeof type !== 'string' || type === '') {
        throw new Error('flow-ui quick-props: type required');
    }
    const entry = FLOW_UI_CATALOG_MANIFEST.components[type];
    const schema = Array.isArray(entry?.editor?.schema) ? entry.editor.schema : [];
    const props = [];
    for (const field of schema) {
        if (!field || typeof field !== 'object') continue;
        const name = field.name;
        const kind = field.kind;
        if (typeof name !== 'string' || name === '') continue;
        if (kind !== 'boolean' && kind !== 'enum') continue;
        const schemaLabel = field.label != null && typeof field.label === 'object'
            ? Object.freeze({
                ru: typeof field.label.ru === 'string' ? field.label.ru : name,
                en: typeof field.label.en === 'string' ? field.label.en : name,
            })
            : null;
        props.push(Object.freeze({
            name,
            kind,
            options: kind === 'enum' ? normalizeEnumOptions(field.options) : undefined,
            labelKey: `interface_editor.quick_${name}`,
            schemaLabel,
        }));
    }
    if (FLOW_UI_VALIDATION_INPUT_TYPES.has(type)) {
        props.push(Object.freeze({
            name: FLOW_UI_QUICK_REQUIRED_NAME,
            kind: 'boolean',
            labelKey: 'interface_editor.inspector_required',
            schemaLabel: null,
        }));
    }
    return Object.freeze(props);
}
