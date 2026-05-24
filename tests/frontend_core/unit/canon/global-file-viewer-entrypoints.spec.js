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

const FILE_ICON_SURFACE_FILES = [
    'core/frontend/static/lib/flows-chat/flows-chat-message.js',
    'core/frontend/static/lib/flows-chat/flows-chat-files-panel.js',
    'core/frontend/static/lib/flows-chat/flows-chat-input.js',
    'core/frontend/static/lib/flows-chat/blocks/flows-chat-ui-file-card.js',
    'apps/sync/ui/components/sync-message-bubble.js',
    'apps/crm/ui/components/entity-card.js',
    'apps/crm/ui/components/note-card-view.js',
    'apps/flows/ui/pages/operator-page.js',
    'apps/flows/ui/components/nodes/flows-base-node-editor.js',
    'core/frontend/static/lib/components/platform-calendar-modal.js',
    'apps/crm/ui/modals/knowledge-import-modal.js',
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

    it('known file surfaces use typed file icons instead of a generic UI file icon', () => {
        for (const relPath of FILE_ICON_SURFACE_FILES) {
            const src = readRepoFile(relPath);
            expect(src, `${relPath} must resolve file icons by filename/MIME`).toContain('resolveFileIconKey');
            expect(src, `${relPath} must render file SVG icons through platform-icon[file-icon]`).toContain('file-icon');
            expect(src, `${relPath} must not render attachments with the generic UI file icon`).not.toMatch(/<platform-icon\s+name=["']file["']/);
        }
    });
});
