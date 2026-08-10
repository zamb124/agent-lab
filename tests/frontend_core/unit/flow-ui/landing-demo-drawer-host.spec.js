import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('Landing public demo Flow UI host', () => {
    it('home demo agents mounts flow-ui-drawer with embed_public contract', () => {
        const source = readFileSync(
            join(root, 'apps/frontend/ui/components/landing/landing-home-demo-agents.js'),
            'utf8',
        );
        expect(source).toContain("import '@platform/lib/flow-ui/shell/drawer.js'");
        expect(source).toContain('<flow-ui-drawer');
        expect(source).toContain("profile: 'embed_public'");
        expect(source).toContain("credentials: 'omit'");
        expect(source).toContain("companyId: 'system'");
        expect(source).toContain('voiceBaseUrl');
        expect(source).toContain('resolveVoiceHttpOriginFromFlowsBaseUrl');
        expect(source).toContain('getRequestHeaders');
        expect(source).toContain('@flow-ui-drawer-open-changed');
        expect(source).not.toContain('getAuthToken');
        expect(source).not.toContain('humanitec-embed-drawer-open-changed');
        expect(source).not.toContain('flows-base-url');
    });

    it('digital workers page mounts the same drawer host', () => {
        const source = readFileSync(
            join(root, 'apps/frontend/ui/pages/landing-digital-workers-page.js'),
            'utf8',
        );
        expect(source).toContain('<flow-ui-drawer');
        expect(source).toContain("profile: 'embed_public'");
        expect(source).toContain("companyId: 'system'");
        expect(source).toContain('voiceBaseUrl');
        expect(source).toContain('getRequestHeaders');
        expect(source).not.toContain('getAuthToken');
    });

    it('drawer forwards credentials, voice host props and isolated toggleEventName', () => {
        const source = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/shell/drawer.js'),
            'utf8',
        );
        expect(source).toContain('credentials=${this._credentials(c)}');
        expect(source).toContain('company-id=${companyId}');
        expect(source).toContain('voice-base-url=${voiceBaseUrl}');
        expect(source).toContain('toggleEventName');
        expect(source).toContain('flow-ui-drawer-open-changed');
    });
});
