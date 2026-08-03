import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
    extractPlatformFileDownloadId,
    normalizeFlowChatBlockForPlatformUrls,
    resolvePlatformFileDownloadUrl,
    rewritePlatformFileUrlsInHtml,
} from '@platform/lib/chat/flows-url-rewrite.js';
import { installDomShim } from '../../helpers/dom-shim.js';

const historicalDownloadPath = (serviceSegment, fileId) =>
    `/${serviceSegment}/api/v1/files/download/${fileId}`;

let dom;

beforeEach(() => {
    dom = installDomShim();
    dom.window.location.pathname = '/flows/editor';
    Object.defineProperty(globalThis.location, 'pathname', {
        value: '/flows/editor',
        configurable: true,
    });
});

afterEach(() => {
    dom.uninstall();
});

describe('flows-url-rewrite', () => {
    it('extractPlatformFileDownloadId из пути любого сервиса', () => {
        expect(extractPlatformFileDownloadId('/frontend/api/v1/files/download/file_abc')).toBe('file_abc');
        expect(extractPlatformFileDownloadId(historicalDownloadPath('flows', 'file_old'))).toBe('file_old');
    });

    it('resolvePlatformFileDownloadUrl переписывает на segment текущего SPA', () => {
        expect(resolvePlatformFileDownloadUrl(historicalDownloadPath('sync', 'x y'))).toBe(
            '/flows/api/v1/files/download/x%20y',
        );
    });

    it('rewritePlatformFileUrlsInHtml переписывает href на текущий segment', () => {
        const legacyHref = historicalDownloadPath('crm', 'f1');
        const html = `<a href="${legacyHref}">x</a>`;
        expect(rewritePlatformFileUrlsInHtml(html)).toBe(
            '<a href="/flows/api/v1/files/download/f1">x</a>',
        );
    });

    it('normalizeFlowChatBlockForPlatformUrls для file_card', () => {
        const block = normalizeFlowChatBlockForPlatformUrls({
            type: 'file_card',
            url: historicalDownloadPath('rag', 'doc-1'),
            preview_url: historicalDownloadPath('worktracker', 'doc-1'),
        });
        expect(block.url).toBe('/flows/api/v1/files/download/doc-1');
        expect(block.preview_url).toBe('/flows/api/v1/files/download/doc-1');
    });
});
