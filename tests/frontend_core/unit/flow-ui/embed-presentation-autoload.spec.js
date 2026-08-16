import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('Flow UI embed autoload presentation', () => {
    it('branches drawer vs page hosts', () => {
        const source = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/shell/embed-autoload.js'),
            'utf8',
        );
        expect(source).toContain("import './page-host.js'");
        expect(source).toContain('resolvePresentation');
        expect(source).toContain("createElement('flow-ui-page-host')");
        expect(source).toContain("createElement('flow-ui-drawer')");
        expect(source).toContain('launcherPosition');
        expect(source).toContain('bearerFor');
        expect(source).toContain('assignLinnexFlowUI');
        expect(source).toContain('linnex-flow-ui-mounted');
        expect(source).toContain('platformUiOrigin');
        expect(source).not.toContain('chatTokenUrl');
        expect(source).not.toContain('data-chat-token-url');
        expect(source).not.toContain('humanitecEmbed');
    });

    it('page host mounts display=page profile=embed_public', () => {
        const source = readFileSync(
            join(root, 'core/frontend/static/lib/flow-ui/shell/page-host.js'),
            'utf8',
        );
        expect(source).toContain('display="page"');
        expect(source).toContain("profile || 'embed_public'");
        expect(source).toContain('company-id=${companyId}');
        expect(source).toContain('platform-ui-origin=${platformUiOrigin}');
        expect(source).toContain('getExtraMetadataVariables');
        expect(source).toContain('assistant-title');
        expect(source).toContain('position: fixed');
        expect(source).toContain('inset: 0');
    });
});
