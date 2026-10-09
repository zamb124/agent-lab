import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

const readSource = (rel) => {
    const jsPath = join(root, rel);
    const tsPath = jsPath.replace(/\.js$/, '.ts');
    return readFileSync(existsSync(jsPath) ? jsPath : tsPath, 'utf8');
};

describe('Landing public demo Flow UI host', () => {
    it('home demo agents mounts flow-ui-drawer with embed_public contract', () => {
        const source = readSource('apps/frontend/ui/components/landing/landing-home-demo-agents.js');
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
        const source = readSource('apps/frontend/ui/pages/landing-digital-workers-page.js');
        expect(source).toContain('<flow-ui-drawer');
        expect(source).toContain("profile: 'embed_public'");
        expect(source).toContain("companyId: 'system'");
        expect(source).toContain('voiceBaseUrl');
        expect(source).toContain('getRequestHeaders');
        expect(source).not.toContain('getAuthToken');
    });

    it('drawer forwards credentials, voice host props and isolated toggleEventName', () => {
        const source = readSource('core/frontend/static/lib/flow-ui/shell/drawer.js');
        expect(source).toContain('credentials=${this._credentials(c)}');
        expect(source).toContain('company-id=${companyId}');
        expect(source).toContain('voice-base-url=${voiceBaseUrl}');
        expect(source).toContain('toggleEventName');
        expect(source).toContain('flow-ui-drawer-open-changed');
    });
});
