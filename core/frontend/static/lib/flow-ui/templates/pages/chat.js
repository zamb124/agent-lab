import { flexLayout, stackLayout } from '../component-factory.js';
import { buildDefaultChatDocument } from '../chat-template.js';
import { component, copy, surface } from './_shared.js';

export function chatSurface(surfaceId) {
    const document = buildDefaultChatDocument();
    const main = document.surfaces.main;
    return surface(surfaceId, main.components, main.data_model);
}

export function assistantWithSidebarSurface(surfaceId, locale) {
    const chat = chatSurface(surfaceId);
    const components = { ...chat.components };
    components.root = component({
        component_id: 'root',
        type: 'PageShell',
        kind: 'container',
        children: ['workspace'],
        container_layout: stackLayout('space.0'),
        properties: { presentation: 'conversation' },
    });
    components.workspace = component({
        component_id: 'workspace',
        type: 'Section',
        kind: 'container',
        children: ['side', 'conversation', 'greeting', 'suggestions', 'message-form'],
        container_layout: flexLayout({ direction: 'column', gap: 'space.0' }),
    });
    components.side = component({
        component_id: 'side',
        type: 'Section',
        kind: 'container',
        children: ['side-title', 'side-note'],
        container_layout: stackLayout('space.2'),
    });
    components['side-title'] = component({
        component_id: 'side-title',
        type: 'Heading',
        bindings: { text: '/content/sideTitle' },
        properties: { level: 3 },
    });
    components['side-note'] = component({
        component_id: 'side-note',
        type: 'Markdown',
        bindings: { content: '/content/sideNote' },
    });
    delete components.header;
    return surface(surfaceId, components, {
        content: {
            ...chat.data_model.content,
            sideTitle: copy(locale, 'Контекст', 'Context'),
            sideNote: copy(
                locale,
                'Опишите, что агент должен учитывать на этом экране.',
                'Describe what the agent should keep in mind for this screen.',
            ),
        },
        values: chat.data_model.values,
        system: chat.data_model.system,
    });
}
