import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();

const ENTRYPOINT_FILES = [
    'core/frontend/static/lib/platform-element/index.js',
    'core/frontend/static/lib/flows-chat/flows-chat-message.js',
    'core/frontend/static/lib/flows-chat/flows-chat-files-panel.js',
    'core/frontend/static/lib/flows-chat/blocks/flows-chat-ui-file-card.js',
    'apps/sync/ui/components/sync-message-bubble.js',
    'apps/crm/ui/components/entity-card.js',
    'apps/crm/ui/components/note-card-view.js',
    'apps/flows/ui/pages/operator-page.js',
    'apps/flows/ui/components/nodes/flows-base-node-editor.js',
    'core/frontend/static/lib/components/platform-calendar-modal.js',
];

function readRepoFile(relPath) {
    return readFileSync(path.join(ROOT, relPath), 'utf8');
}

describe('global file viewer entrypoints', () => {
    it('all known UI file surfaces route through PlatformElement.openFile', () => {
        for (const relPath of ENTRYPOINT_FILES) {
            const src = readRepoFile(relPath);
            expect(src, `${relPath} must use the shared global file viewer entrypoint`).toContain('openFile(');
        }
    });

    it('UI surfaces do not recreate documents from FileRecord before opening', () => {
        for (const relPath of ENTRYPOINT_FILES) {
            const src = readRepoFile(relPath);
            expect(src, `${relPath} must not call legacy documents/from-file flow`).not.toContain('/documents/from-file');
            expect(src, `${relPath} must not call legacy documents/from-file API`).not.toContain('documents/from-file');
        }
    });
});
