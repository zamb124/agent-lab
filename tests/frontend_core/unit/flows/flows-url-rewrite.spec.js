import { describe, it, expect } from 'vitest';
import {
    CANONICAL_FILES_DOWNLOAD_PREFIX,
    extractPlatformFileDownloadId,
    normalizeFlowChatBlockForPlatformUrls,
    resolvePlatformFileDownloadUrl,
    rewritePlatformFileUrlsInHtml,
} from '@platform/lib/flows-chat/flows-url-rewrite.js';

const historicalDownloadPath = (serviceSegment, fileId) =>
    `/${serviceSegment}/api/v1/files/download/${fileId}`;

describe('flows-url-rewrite', () => {
    it('extractPlatformFileDownloadId из канонического пути', () => {
        expect(extractPlatformFileDownloadId('/frontend/api/v1/files/download/file_abc')).toBe('file_abc');
    });

    it('extractPlatformFileDownloadId из исторического same-origin пути', () => {
        expect(extractPlatformFileDownloadId(historicalDownloadPath('flows', 'file_old'))).toBe('file_old');
    });

    it('resolvePlatformFileDownloadUrl нормализует в frontend prefix', () => {
        expect(resolvePlatformFileDownloadUrl(historicalDownloadPath('sync', 'x y'))).toBe(
            `${CANONICAL_FILES_DOWNLOAD_PREFIX}/x%20y`,
        );
    });

    it('rewritePlatformFileUrlsInHtml переписывает href', () => {
        const legacyHref = historicalDownloadPath('crm', 'f1');
        const html = `<a href="${legacyHref}">x</a>`;
        expect(rewritePlatformFileUrlsInHtml(html)).toBe(
            `<a href="${CANONICAL_FILES_DOWNLOAD_PREFIX}/f1">x</a>`,
        );
    });

    it('normalizeFlowChatBlockForPlatformUrls для file_card', () => {
        const block = normalizeFlowChatBlockForPlatformUrls({
            type: 'file_card',
            url: historicalDownloadPath('rag', 'doc-1'),
            preview_url: historicalDownloadPath('worktracker', 'doc-1'),
        });
        expect(block.url).toBe(`${CANONICAL_FILES_DOWNLOAD_PREFIX}/doc-1`);
        expect(block.preview_url).toBe(`${CANONICAL_FILES_DOWNLOAD_PREFIX}/doc-1`);
    });
});
