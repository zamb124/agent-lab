import { registerEmbedBlockType } from './block-registry.js';
import { EmbedUiCard } from './blocks/embed-ui-card.js';
import { EmbedUiTable } from './blocks/embed-ui-table.js';
import { EmbedUiActions } from './blocks/embed-ui-actions.js';
import { EmbedUiFileCard } from './blocks/embed-ui-file-card.js';
import { EmbedUiText } from './blocks/embed-ui-text.js';

let registered = false;

export function registerBuiltinEmbedBlocks() {
    if (registered) {
        return;
    }
    registered = true;
    registerEmbedBlockType('card', EmbedUiCard, null, 'embed-ui-card');
    registerEmbedBlockType('table', EmbedUiTable, null, 'embed-ui-table');
    registerEmbedBlockType('actions', EmbedUiActions, null, 'embed-ui-actions');
    registerEmbedBlockType('file_card', EmbedUiFileCard, null, 'embed-ui-file-card');
    registerEmbedBlockType('text', EmbedUiText, null, 'embed-ui-text');
}
