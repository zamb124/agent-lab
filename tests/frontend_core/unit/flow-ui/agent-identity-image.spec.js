import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { FLOW_UI_CATALOG_MANIFEST } from '../../../../core/frontend/static/lib/flow-ui/catalog/manifest.js';
import {
    agentIdentityImageUrlFromDocument,
    flowUIMediaSrc,
    resolveAgentIdentityImageSrc,
    resolveAgentIdentityRawImageUrl,
} from '../../../../core/frontend/static/lib/flow-ui/runtime/agent-identity-image.js';
import { BRAND_LOGO_PATH, brandLogoSrc } from '../../../../core/frontend/static/lib/flow-ui/shell/brand-logo.js';
import { buildFlowAssetFileCreateSpecJson } from '../../../../core/frontend/static/lib/utils/file-create-spec.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('AgentIdentity image_url', () => {
    it('declares image schema kind with publicAsset and empty default', () => {
        const identity = FLOW_UI_CATALOG_MANIFEST.components.AgentIdentity;
        const imageField = identity.editor.schema.find((field) => field.name === 'image_url');
        expect(imageField).toBeTruthy();
        expect(imageField.kind).toBe('image');
        expect(imageField.publicAsset).toBe(true);
        expect(identity.editor.defaults.properties.image_url).toBe('');
    });

    it('builds public flow_asset upload spec when isPublic is true', () => {
        const spec = JSON.parse(buildFlowAssetFileCreateSpecJson({
            flowId: 'flow-1',
            isPublic: true,
        }));
        expect(spec.source_kind).toBe('flow_asset');
        expect(spec.source_ref.flow_id).toBe('flow-1');
        expect(spec.post_create.is_public).toBe(true);
    });

    it('builds private flow_asset upload spec by default', () => {
        const spec = JSON.parse(buildFlowAssetFileCreateSpecJson({ flowId: 'flow-1' }));
        expect(spec.post_create.is_public).toBe(false);
    });

    it('prefixes relative download and static paths with platform origin', () => {
        expect(flowUIMediaSrc('https://cdn.example', '/flows/api/v1/files/download/abc'))
            .toBe('https://cdn.example/flows/api/v1/files/download/abc');
        expect(flowUIMediaSrc('https://cdn.example/', BRAND_LOGO_PATH))
            .toBe(`https://cdn.example${BRAND_LOGO_PATH}`);
        expect(flowUIMediaSrc('', '/flows/api/v1/files/download/abc'))
            .toBe('/flows/api/v1/files/download/abc');
    });

    it('keeps https URLs and rejects javascript', () => {
        expect(flowUIMediaSrc('https://cdn.example', 'https://files.example/img.png'))
            .toBe('https://files.example/img.png');
        expect(() => flowUIMediaSrc('', 'javascript:alert(1)')).toThrow(/blocked scheme/);
        expect(() => flowUIMediaSrc('', 'data:text/html,x')).toThrow(/blocked scheme/);
    });

    it('resolves property over profile over brand; empty string does not mask', () => {
        const download = '/flows/api/v1/files/download/agent-img';
        const profileUrl = '/flows/api/v1/files/download/from-profile';
        const component = {
            type: 'AgentIdentity',
            properties: { image_url: download },
        };
        expect(resolveAgentIdentityRawImageUrl({
            component,
            profile: { flow_identity: { image_url: profileUrl } },
        })).toBe(download);
        expect(resolveAgentIdentityRawImageUrl({
            component: { type: 'AgentIdentity', properties: { image_url: '' } },
            profile: { flow_identity: { image_url: profileUrl } },
        })).toBe(profileUrl);
        expect(resolveAgentIdentityRawImageUrl({
            component: { type: 'AgentIdentity', properties: { image_url: '   ' } },
            profile: { flow_identity: { image_url: null } },
        })).toBeNull();
        expect(resolveAgentIdentityImageSrc({
            platformUiOrigin: '',
        })).toBe(brandLogoSrc(''));
        expect(resolveAgentIdentityImageSrc({
            component,
            platformUiOrigin: 'https://ui.example',
        })).toBe(`https://ui.example${download}`);
    });

    it('reads AgentIdentity.image_url from the document and rejects conflicts', () => {
        const download = '/flows/api/v1/files/download/doc-img';
        const document = {
            surfaces: {
                main: {
                    components: {
                        header: { type: 'Section', properties: {} },
                        identity: { type: 'AgentIdentity', properties: { image_url: download } },
                    },
                },
            },
        };
        expect(agentIdentityImageUrlFromDocument(document)).toBe(download);
        expect(() => agentIdentityImageUrlFromDocument({
            surfaces: {
                main: {
                    components: {
                        a: { type: 'AgentIdentity', properties: { image_url: download } },
                        b: { type: 'AgentIdentity', properties: { image_url: '/flows/api/v1/files/download/other' } },
                    },
                },
            },
        })).toThrow(/conflict/);
    });

    it('inspector rejects a non-public pick for publicAsset fields', () => {
        const inspectorSrc = readFileSync(
            join(root, 'apps/flows/ui/components/interface-editor/flows-interface-inspector.js'),
            'utf8',
        );
        expect(inspectorSrc).toMatch(/publicAsset === true/);
        expect(inspectorSrc).toMatch(/isPublic:\s*publicAsset/);
        expect(inspectorSrc).toMatch(/file\.is_public !== true/);
        expect(inspectorSrc).toMatch(/public image requires is_public file/);
    });
});
