/**
 * Утилиты для работы с файлами
 */

export function getFileIcon(mimeType) {
    if (mimeType.startsWith('image/')) return 'ti-file-earmark-image';
    if (mimeType.startsWith('video/')) return 'ti-file-earmark-play';
    if (mimeType.startsWith('audio/')) return 'ti-file-earmark-music';
    if (mimeType.includes('pdf')) return 'ti-file-earmark-pdf';
    if (mimeType.includes('word') || mimeType.includes('document')) return 'ti-file-earmark-word';
    if (mimeType.includes('excel') || mimeType.includes('spreadsheet')) return 'ti-file-earmark-excel';
    if (mimeType.includes('powerpoint') || mimeType.includes('presentation')) return 'ti-file-earmark-ppt';
    if (mimeType.includes('zip') || mimeType.includes('archive')) return 'ti-file-earmark-zip';
    return 'ti-file-earmark';
}

export function getFileIconEmoji(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
        'pdf': '📄', 'doc': '📝', 'docx': '📝',
        'xls': '📊', 'xlsx': '📊', 'ppt': '📈', 'pptx': '📈',
        'txt': '📃', 'zip': '📦', 'rar': '📦'
    };
    return icons[ext] || '📎';
}

export function detectFileType(fileName) {
    if (fileName.startsWith('audio_')) {
        return 'audio';
    }
    
    if (!fileName.includes('.')) {
        return 'document';
    }
    
    const ext = fileName.split('.').pop().toLowerCase();
    
    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) {
        return 'image';
    }
    
    if (['mp4', 'webm', 'ogg', 'mov', 'avi'].includes(ext)) {
        return 'video';
    }
    
    if (['mp3', 'wav', 'ogg', 'flac', 'm4a'].includes(ext)) {
        return 'audio';
    }
    
    if (ext === 'pdf') {
        return 'pdf';
    }
    
    return 'document';
}

export function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = error => reject(error);
    });
}

export function validateFileType(file, allowedTypes) {
    if (!allowedTypes || allowedTypes.length === 0) return true;
    return allowedTypes.some(type => file.type.startsWith(type));
}

export function validateFileSize(file, maxSizeInBytes) {
    return file.size <= maxSizeInBytes;
}

