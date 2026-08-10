import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { FLOW_UI_CATALOG_MANIFEST } from '@platform/lib/flow-ui/catalog/manifest.js';
import { buildDefaultChatDocument } from '@platform/lib/flow-ui/templates/chat-template.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('Catalog VoiceInput', () => {
    it('is in platform palette and production maturity', () => {
        const entry = FLOW_UI_CATALOG_MANIFEST.components.VoiceInput;
        expect(entry).toBeTruthy();
        expect(entry.editor.group).toBe('input');
        expect(entry.editor.maturity).toBe('production');
        expect(entry.editor.palette).toBe(true);
    });

    it('default chat template includes voice-input child under message-form', () => {
        const document = buildDefaultChatDocument();
        const form = document.surfaces.main.components['message-form'];
        expect(form).toBeTruthy();
        expect(form.children).toContain('voice-input');
        const voice = document.surfaces.main.components['voice-input'];
        expect(voice.type).toBe('VoiceInput');
        expect(voice.properties?.mode).toBe('session');
    });

    it('composer Form discovers VoiceInput child and does not inject platform-voice-dictation', () => {
        const layout = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/catalog/platform/layout.js'),
            'utf8',
        );
        expect(layout).toContain("children.find((child) => child.type === 'VoiceInput')");
        expect(layout).toContain('renderVoiceInput');
        expect(layout.includes('<platform-voice-dictation')).toBe(false);
    });

    it('python catalog declares VoiceInput', () => {
        const catalog = readFileSync(join(root, 'core/a2ui/catalog.py'), 'utf8');
        expect(catalog).toContain('_component("VoiceInput"');
    });

    it('python default chat document includes voice-input', () => {
        const model = readFileSync(join(root, 'core/models/flow_interface.py'), 'utf8');
        expect(model).toContain('"voice-input');
        expect(model).toContain('type="VoiceInput"');
        expect(model).toContain('"mode": "session"');
    });
});
