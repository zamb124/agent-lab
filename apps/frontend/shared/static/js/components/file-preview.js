/**
 * Компоненты для работы с файлами
 */

import { formatFileSize } from '/static/js/utils/formatting.js';
import { getFileIcon, getFileIconEmoji, detectFileType } from '/static/js/utils/files.js';

export class FilePreviewCard {
    constructor(file) {
        this.file = file;
    }
    
    render() {
        const fileCard = document.createElement('div');
        fileCard.className = 'chat-file-card';
        
        const icon = getFileIcon(this.file.type);
        
        fileCard.innerHTML = `
            <div class="file-card-icon">
                <i class="ti ti-${icon}"></i>
            </div>
            <div class="file-card-info">
                <div class="file-card-name">${this.file.name}</div>
                <div class="file-card-details">${formatFileSize(this.file.size)} • ${this.file.type}</div>
            </div>
            <div class="file-card-actions">
                <a href="${this.file.url}" target="_blank" class="file-download-btn" title="Скачать">
                    <i class="ti ti-download"></i>
                </a>
            </div>
        `;
        
        return fileCard;
    }
}

export class FilePreviewList {
    constructor(files, options = {}) {
        this.files = files;
        this.options = {
            showRemove: true,
            onRemove: null,
            ...options
        };
    }
    
    render() {
        const container = document.createElement('div');
        container.className = 'file-preview-list';
        
        const header = document.createElement('div');
        header.className = 'file-preview-header';
        header.innerHTML = `
            <span>📎 ${this.files.length} файл${this.files.length > 1 ? 'а' : ''}</span>
            ${this.options.showRemove ? `
                <button class="file-preview-cancel">
                    <i class="ti ti-x"></i>
                </button>
            ` : ''}
        `;
        
        if (this.options.showRemove) {
            const cancelBtn = header.querySelector('.file-preview-cancel');
            cancelBtn.addEventListener('click', () => {
                if (this.options.onRemove) {
                    this.options.onRemove();
                }
            });
        }
        
        container.appendChild(header);
        
        const list = document.createElement('div');
        list.className = 'file-preview-items';
        
        this.files.forEach(file => {
            const item = document.createElement('div');
            item.className = 'file-preview-item';
            item.innerHTML = `
                <i class="ti ti-file-earmark"></i>
                <span class="file-name">${file.name}</span>
                <span class="file-size">${formatFileSize(file.size)}</span>
            `;
            list.appendChild(item);
        });
        
        container.appendChild(list);
        
        return container;
    }
}

export async function renderDownloadButton(link) {
    const container = document.createElement('div');
    container.className = 'download-link-container';
    
    container.innerHTML = `
        <div class="file-preview loading-preview">
            <div class="spinner-border spinner-border-sm" role="status"></div>
            <span class="ms-2">Загрузка превью...</span>
        </div>
    `;
    
    const fileType = detectFileType(link.fileName);
    
    if (fileType !== 'document') {
        renderFilePreview(container, link, null, fileType);
    } else {
        try {
            const mimeType = await fetchFileMimeType(link.url);
            renderFilePreview(container, link, mimeType);
        } catch (error) {
            console.error('Ошибка загрузки файла:', error);
            renderFilePreview(container, link, null);
        }
    }
    
    return container;
}

async function fetchFileMimeType(url) {
    const fileId = url.split('/').pop();
    const infoUrl = url.replace(`/download/${fileId}`, `/info/${fileId}`);
    const response = await fetch(infoUrl);
    
    if (!response.ok) {
        return null;
    }
    
    const fileInfo = await response.json();
    return fileInfo.content_type;
}

function renderFilePreview(container, link, mimeType = null, knownType = null) {
    let fileType = knownType;
    
    if (mimeType && !knownType) {
        if (mimeType.startsWith('image/')) fileType = 'image';
        else if (mimeType.startsWith('video/')) fileType = 'video';
        else if (mimeType.startsWith('audio/')) fileType = 'audio';
        else if (mimeType.includes('pdf')) fileType = 'pdf';
        else fileType = 'document';
    }
    
    if (fileType === 'image') {
        container.innerHTML = `
            <div class="file-preview image-preview">
                <img src="${link.url}" alt="${link.fileName}" 
                     style="max-width: 300px; max-height: 300px; border-radius: 8px; cursor: pointer; object-fit: contain;"
                     onclick="window.open('${link.url}', '_blank')"
                     onerror="this.parentElement.innerHTML='<div class=error-preview>❌ Не удалось загрузить изображение</div>'"
                >
                <div class="file-info" style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                    <span class="file-name" style="font-size: 14px; color: #666;">${link.fileName}</span>
                    <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                        <i class="ti ti-download"></i> Скачать
                    </a>
                </div>
            </div>
        `;
    } else if (fileType === 'video') {
        container.innerHTML = `
            <div class="file-preview video-preview">
                <video controls style="max-width: 400px; border-radius: 8px;">
                    <source src="${link.url}" type="${mimeType || 'video/mp4'}">
                    Ваш браузер не поддерживает видео.
                </video>
                <div class="file-info" style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                    <span class="file-name" style="font-size: 14px; color: #666;">${link.fileName}</span>
                    <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                        <i class="ti ti-download"></i> Скачать
                    </a>
                </div>
            </div>
        `;
    } else if (fileType === 'audio') {
        container.innerHTML = `
            <div class="file-preview audio-preview">
                <audio controls style="width: 300px;">
                    <source src="${link.url}" type="${mimeType || 'audio/mpeg'}">
                    Ваш браузер не поддерживает аудио.
                </audio>
                <div class="file-info" style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                    <span class="file-name" style="font-size: 14px; color: #666;">${link.fileName}</span>
                    <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                        <i class="ti ti-download"></i> Скачать
                    </a>
                </div>
            </div>
        `;
    } else {
        const icon = getFileIconEmoji(link.fileName);
        container.innerHTML = `
            <div class="file-preview document-preview" style="display: flex; align-items: center; padding: 12px; border: 1px solid #ddd; border-radius: 8px; background: #f8f9fa;">
                <div class="file-icon" style="font-size: 32px; margin-right: 12px;">${icon}</div>
                <div class="file-info" style="flex-grow: 1;">
                    <div class="file-name" style="font-size: 14px; font-weight: 500;">${link.fileName}</div>
                    ${mimeType ? `<div class="file-type" style="font-size: 12px; color: #666;">${mimeType}</div>` : ''}
                </div>
                <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                    <i class="ti ti-download"></i>
                </a>
            </div>
        `;
    }
}

export { renderDownloadButton, renderFilePreview };

