/**
 * Сжатие изображения для аватара канала (клиент): уменьшение длинной стороны и JPEG.
 */

/**
 * @param {number} naturalWidth
 * @param {number} naturalHeight
 * @param {number} maxEdge
 * @returns {{ width: number, height: number }}
 */
export function computeAvatarResizeDimensions(naturalWidth, naturalHeight, maxEdge) {
    if (typeof naturalWidth !== 'number' || typeof naturalHeight !== 'number') {
        throw new Error('computeAvatarResizeDimensions: width and height must be numbers');
    }
    if (naturalWidth <= 0 || naturalHeight <= 0) {
        throw new Error('computeAvatarResizeDimensions: dimensions must be positive');
    }
    if (typeof maxEdge !== 'number' || maxEdge <= 0) {
        throw new Error('computeAvatarResizeDimensions: maxEdge must be a positive number');
    }
    const long = Math.max(naturalWidth, naturalHeight);
    if (long <= maxEdge) {
        return { width: naturalWidth, height: naturalHeight };
    }
    const scale = maxEdge / long;
    return {
        width: Math.round(naturalWidth * scale),
        height: Math.round(naturalHeight * scale),
    };
}

/**
 * @param {File} file
 * @param {{ maxEdge?: number, quality?: number }} [options]
 * @returns {Promise<File>}
 */
export async function compressImageFileToJpeg(file, options = {}) {
    if (!(file instanceof File)) {
        throw new Error('compressImageFileToJpeg: File required');
    }
    const maxEdge = options.maxEdge === undefined ? 512 : options.maxEdge;
    const quality = options.quality === undefined ? 0.82 : options.quality;
    if (typeof createImageBitmap !== 'function') {
        throw new Error('compressImageFileToJpeg: createImageBitmap is not available');
    }
    const bitmap = await createImageBitmap(file);
    try {
        const { width, height } = computeAvatarResizeDimensions(bitmap.width, bitmap.height, maxEdge);
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
            throw new Error('compressImageFileToJpeg: 2d context unavailable');
        }
        ctx.drawImage(bitmap, 0, 0, width, height);
        const blob = await new Promise((resolve, reject) => {
            canvas.toBlob(
                (b) => {
                    if (b) resolve(b);
                    else reject(new Error('compressImageFileToJpeg: toBlob returned null'));
                },
                'image/jpeg',
                quality,
            );
        });
        return new File([blob], 'channel-avatar.jpg', { type: 'image/jpeg' });
    } finally {
        bitmap.close();
    }
}
