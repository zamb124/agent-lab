import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { FLOW_UI_CATALOG_MANIFEST } from '../../../../core/frontend/static/lib/flow-ui/catalog/manifest.js';
import { flowUIText } from '../../../../core/frontend/static/lib/flow-ui/utils/text.js';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');

describe('flow-ui Image asset picker', () => {
    it('uses image schema kind and empty default src (no brand static path)', () => {
        const image = FLOW_UI_CATALOG_MANIFEST.components.Image;
        const srcField = image.editor.schema.find((field) => field.name === 'src');
        expect(srcField).toBeTruthy();
        expect(srcField.kind).toBe('image');
        expect(image.editor.defaults.properties.src).toBe('');
        expect(String(image.editor.defaults.properties.src)).not.toMatch(/service_logos|spinner/);
    });

    it('renders empty Image as placeholder, not throw', () => {
        const mediaSrc = readFileSync(
            path.join(REPO_ROOT, 'core/frontend/static/lib/flow-ui/catalog/basic/media.js'),
            'utf8',
        );
        expect(mediaSrc).toMatch(/image-empty/);
        expect(mediaSrc).toMatch(/imageSrc/);
        expect(mediaSrc).toMatch(/flowUIText\(host\.locale,\s*'image_empty'\)/);
        expect(flowUIText('ru', 'image_empty')).toBe('Изображение не выбрано');
        expect(flowUIText('en', 'image_empty')).toBe('No image selected');
    });

    it('wires inspector to platform.file_picker with flow asset upload + documents browse', () => {
        const inspectorSrc = readFileSync(
            path.join(
                REPO_ROOT,
                'apps/flows/ui/components/interface-editor/flows-interface-inspector.js',
            ),
            'utf8',
        );
        expect(inspectorSrc).toMatch(/kind === 'image'/);
        expect(inspectorSrc).toMatch(/platform\.file_picker/);
        expect(inspectorSrc).toMatch(/buildFlowAssetFileCreateSpecJson/);
        expect(inspectorSrc).toMatch(/buildPlatformFileDownloadUrl/);
        expect(inspectorSrc).toMatch(/flows\/catalogs/);
        expect(inspectorSrc).toMatch(/flows\/documents/);
        expect(inspectorSrc).toMatch(/flows\/documents_search/);
        expect(inspectorSrc).toMatch(/isPublic:\s*publicAsset/);
        expect(inspectorSrc).toMatch(/file\.is_public !== true/);

        const appSrc = readFileSync(
            path.join(REPO_ROOT, 'apps/flows/ui/app/flows-app.js'),
            'utf8',
        );
        expect(appSrc).toMatch(/flowsCatalogsOp/);
        expect(appSrc).toMatch(/flowsDocumentsOp/);
        expect(appSrc).toMatch(/flowsDocumentsSearchOp/);
        expect(appSrc).toMatch(/documents-browse\.resource\.js/);
    });
});
