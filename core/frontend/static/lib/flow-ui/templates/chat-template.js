/**
 * Canonical default chat Flow UI document (mirrors core.models.flow_interface.build_default_chat_document).
 */

import { flowUIComponent as component, stackLayout } from './component-factory.js';

export const LINNEX_DEFAULT_CHAT_TEMPLATE_ID = 'linnex.default-chat';
export const LINNEX_DEFAULT_CHAT_TEMPLATE_VERSION = '1.2.0';
export const PLATFORM_UI_SUBMIT_ACTION = 'platform.ui.submit';

/**
 * @param {{
 *   greetingMessage?: string,
 *   suggestedPrompts?: string[],
 * }} [options]
 */
export function buildDefaultChatDocument(options = {}) {
    const greetingMessage = typeof options.greetingMessage === 'string' ? options.greetingMessage : '';
    const suggestedPrompts = Array.isArray(options.suggestedPrompts)
        ? options.suggestedPrompts.map((item) => String(item))
        : [];

    const components = Object.freeze({
        root: component({
            component_id: 'root',
            type: 'PageShell',
            kind: 'container',
            children: ['header', 'conversation', 'greeting', 'suggestions', 'message-form'],
            container_layout: Object.freeze({
                mode: 'flex',
                flex: Object.freeze({ direction: 'column', gap_token: 'space.0' }),
            }),
            properties: { presentation: 'conversation' },
        }),
        header: component({
            component_id: 'header',
            type: 'Section',
            kind: 'container',
            children: ['agent-identity', 'task-controls'],
            container_layout: Object.freeze({
                mode: 'flex',
                flex: Object.freeze({ direction: 'row', justify_content: 'space-between' }),
            }),
            properties: { presentation: 'chat-header' },
        }),
        'agent-identity': component({
            component_id: 'agent-identity',
            type: 'AgentIdentity',
            bindings: { agent: '/system/agent' },
        }),
        'task-controls': component({
            component_id: 'task-controls',
            type: 'TaskControls',
            bindings: { task: '/system/activeTask' },
        }),
        conversation: component({
            component_id: 'conversation',
            type: 'ConversationFeed',
            kind: 'container',
            children: ['artifact-feed'],
            container_layout: stackLayout('space.3'),
        }),
        'artifact-feed': component({
            component_id: 'artifact-feed',
            type: 'ArtifactFeed',
            kind: 'container',
            children: [],
            container_layout: stackLayout('space.3'),
            bindings: { tasks: '/system/tasks' },
            properties: { presentation: 'conversation' },
        }),
        greeting: component({
            component_id: 'greeting',
            type: 'EmptyState',
            bindings: { message: '/content/greeting' },
        }),
        suggestions: component({
            component_id: 'suggestions',
            type: 'SuggestedPrompts',
            bindings: { items: '/content/suggestedPrompts', value: '/values/message' },
            actions: {
                select: Object.freeze({ kind: 'local', name: 'values.set' }),
            },
        }),
        'message-form': component({
            component_id: 'message-form',
            type: 'Form',
            kind: 'container',
            children: ['file-upload', 'message-input', 'voice-input', 'submit'],
            container_layout: stackLayout('space.3'),
            properties: { formId: 'message-form', presentation: 'composer' },
        }),
        'file-upload': component({
            component_id: 'file-upload',
            type: 'FileUpload',
            bindings: { value: '/values/files' },
            properties: { presentation: 'composer', multiple: true },
        }),
        'message-input': component({
            component_id: 'message-input',
            type: 'TextArea',
            bindings: { value: '/values/message' },
            properties: {
                presentation: 'composer',
                rows: 1,
                placeholder: 'Ask anything…',
            },
        }),
        'voice-input': component({
            component_id: 'voice-input',
            type: 'VoiceInput',
            bindings: { value: '/values/message' },
            properties: { presentation: 'composer', mode: 'session' },
        }),
        submit: component({
            component_id: 'submit',
            type: 'Button',
            properties: { label: 'Send', variant: 'primary', presentation: 'composer' },
            actions: {
                press: Object.freeze({
                    kind: 'event',
                    name: PLATFORM_UI_SUBMIT_ACTION,
                    context: Object.freeze({ formId: 'message-form' }),
                }),
            },
        }),
    });

    const surface = Object.freeze({
        surface_id: 'main',
        root_component_id: 'root',
        components,
        data_model: Object.freeze({
            content: Object.freeze({
                greeting: greetingMessage,
                suggestedPrompts: Object.freeze([...suggestedPrompts]),
            }),
            values: Object.freeze({ message: '', files: Object.freeze([]) }),
            system: Object.freeze({ tasks: Object.freeze([]), activeTask: null, agent: Object.freeze({}) }),
        }),
    });

    return Object.freeze({
        document_id: `template:${LINNEX_DEFAULT_CHAT_TEMPLATE_ID}:${LINNEX_DEFAULT_CHAT_TEMPLATE_VERSION}`,
        template_version: LINNEX_DEFAULT_CHAT_TEMPLATE_VERSION,
        active_page_id: 'main',
        pages: Object.freeze({
            main: Object.freeze({
                page_id: 'main',
                title: Object.freeze({ default: 'Conversation', translations: Object.freeze({}) }),
                route: '/',
                root_surface_id: 'main',
            }),
        }),
        surfaces: Object.freeze({ main: surface }),
        policy: Object.freeze({}),
    });
}

export function createDefaultChatTemplate(options = {}) {
    const document = buildDefaultChatDocument(options);
    return Object.freeze({
        template_id: LINNEX_DEFAULT_CHAT_TEMPLATE_ID,
        version: LINNEX_DEFAULT_CHAT_TEMPLATE_VERSION,
        document,
    });
}
