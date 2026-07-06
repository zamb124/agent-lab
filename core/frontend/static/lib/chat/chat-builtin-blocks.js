import { registerFlowChatBlockType } from './block-registry.js';
import { FlowsChatUiCard } from './blocks/flows-chat-ui-card.js';
import { FlowsChatUiTable } from './blocks/flows-chat-ui-table.js';
import { FlowsChatUiActions } from './blocks/flows-chat-ui-actions.js';
import { FlowsChatUiFileCard } from './blocks/flows-chat-ui-file-card.js';
import { FlowsChatUiText } from './blocks/flows-chat-ui-text.js';

let registered = false;

export function registerBuiltinFlowChatBlocks() {
    if (registered) {
        return;
    }
    registered = true;
    registerFlowChatBlockType('card', FlowsChatUiCard, null, 'flows-chat-ui-card');
    registerFlowChatBlockType('table', FlowsChatUiTable, null, 'flows-chat-ui-table');
    registerFlowChatBlockType('actions', FlowsChatUiActions, null, 'flows-chat-ui-actions');
    registerFlowChatBlockType('file_card', FlowsChatUiFileCard, null, 'flows-chat-ui-file-card');
    registerFlowChatBlockType('text', FlowsChatUiText, null, 'flows-chat-ui-text');
}
