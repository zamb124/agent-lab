/**
 * Рендерер сообщений чата
 */

import { formatFileSize } from '/static/js/utils/formatting.js';
import { renderMarkdown, sanitizeHTML } from '/static/js/utils/markdown.js';
import { getFileIcon, getFileIconEmoji, detectFileType } from '/static/js/utils/files.js';

const MESSAGE_TYPES = {
    TEXT: 'text',
    HTML: 'html',
    MARKDOWN: 'markdown',
    FORM: 'form',
    BUTTONS: 'buttons',
    COMMAND: 'command',
    REACTION: 'reaction',
    POLL: 'poll',
    CARD: 'card',
    CAROUSEL: 'carousel',
    LOCATION: 'location',
    CONTACT: 'contact',
    REASONING: 'reasoning'
};

class ChatMessageRenderer {
    renderMessage(message) {
        const container = document.createElement('div');
        container.className = `chat-message ${message.sender}`;
        
        if (message.isReasoning) {
            container.classList.add('reasoning');
            const reasoningDiv = this.renderReasoning(message);
            container.appendChild(reasoningDiv);
            return container;
        }
        
        const contentDiv = this.renderContent(message);
        container.appendChild(contentDiv);
        
        if (message.attachments && message.attachments.length > 0) {
            const attachmentsDiv = this.renderAttachments(message.attachments);
            container.appendChild(attachmentsDiv);
        }
        
        if (message.buttons && message.buttons.length > 0) {
            const buttonsDiv = this.renderButtons(message.buttons);
            container.appendChild(buttonsDiv);
        }
        
        if (message.form) {
            const formDiv = this.renderForm(message.form);
            container.appendChild(formDiv);
        }
        
        return container;
    }

    renderReasoning(message) {
        const details = document.createElement('details');
        details.className = 'reasoning-details';
        
        const summary = document.createElement('summary');
        summary.className = 'reasoning-summary';
        summary.innerHTML = '💭 <span class="reasoning-label">Размышление</span>';
        
        const content = document.createElement('div');
        content.className = 'reasoning-content';
        content.innerHTML = renderMarkdown(message.content);
        
        details.appendChild(summary);
        details.appendChild(content);
        
        return details;
    }

    renderContent(message) {
        const div = document.createElement('div');
        div.className = 'message-content';
        
        let content = message.content;
        
        const { cleanContent, files } = this.parseFilesFromContent(content);
        const { cleanContentWithoutLinks, downloadLinks } = this.parseDownloadLinksFromContent(cleanContent);
        
        let finalContent = cleanContentWithoutLinks.replace(/\[СКАЧАТЬ:\s*[^\]]+\]/g, '').trim();
        
        switch (message.type) {
            case MESSAGE_TYPES.HTML:
                div.innerHTML = sanitizeHTML(finalContent);
                break;
            default:
                div.innerHTML = renderMarkdown(finalContent);
                break;
        }
        
        if (files.length > 0) {
            const filesContainer = document.createElement('div');
            filesContainer.className = 'message-files';
            
            files.forEach(file => {
                const fileCard = this.renderFileCard(file);
                filesContainer.appendChild(fileCard);
            });
            
            div.appendChild(filesContainer);
        }
        
        if (downloadLinks.length > 0) {
            const linksContainer = document.createElement('div');
            linksContainer.className = 'message-download-links';
            
            downloadLinks.forEach(async (link) => {
                const linkButton = await this.renderDownloadButton(link);
                linksContainer.appendChild(linkButton);
            });
            
            div.appendChild(linksContainer);
        }
        
        return div;
    }

    parseFilesFromContent(content) {
        const fileRegex = /\[FILE\](.*?)\[\/FILE\]/gs;
        const files = [];
        let cleanContent = content;
        
        let match;
        while ((match = fileRegex.exec(content)) !== null) {
            const fileText = match[1];
            
            const nameMatch = fileText.match(/Файл:\s*([^(]+)/);
            const idMatch = fileText.match(/ID:\s*([^,]+)/);
            const urlMatch = fileText.match(/URL:\s*([^,]+)/);
            const typeMatch = fileText.match(/тип:\s*([^,]+)/);
            const sizeMatch = fileText.match(/размер:\s*([^)]+)/);
            
            if (nameMatch) {
                files.push({
                    name: nameMatch[1].trim(),
                    id: idMatch ? idMatch[1].trim() : '',
                    url: urlMatch ? urlMatch[1].trim() : '',
                    type: typeMatch ? typeMatch[1].trim() : '',
                    size: sizeMatch ? sizeMatch[1].trim() : ''
                });
            }
            
            cleanContent = cleanContent.replace(match[0], '');
        }
        
        return { cleanContent: cleanContent.trim(), files };
    }

    renderFileCard(file) {
        const wrapper = document.createElement('div');
        wrapper.className = 'file-inline';
        
        const name = document.createElement('span');
        name.className = 'file-inline-name';
        name.textContent = file.name;
        
        const download = document.createElement('a');
        download.href = file.url;
        download.target = '_blank';
        download.className = 'file-inline-download';
        download.title = 'Скачать';
        download.setAttribute('aria-label', `Скачать ${file.name}`);
        download.innerHTML = '<i class="ti ti-download"></i>';
        
        wrapper.appendChild(name);
        wrapper.appendChild(download);
        
        return wrapper;
    }

    parseDownloadLinksFromContent(content) {
        const linkRegex = /(https?:\/\/[^\s]+\/api\/v1\/files\/download\/(file_|audio_)[a-z0-9]+)/gi;
        const downloadLinks = [];
        let cleanContent = content;
        
        let match;
        while ((match = linkRegex.exec(content)) !== null) {
            const url = match[1];
            const fileId = url.split('/').pop();
            
            const contextMatch = content.match(new RegExp(`файла?\\s+"([^"]+)"[^]*?${url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`));
            const fileName = contextMatch ? contextMatch[1] : fileId;
            
            downloadLinks.push({
                url: url,
                fileName: fileName,
                fileId: fileId
            });
            
            cleanContent = cleanContent.replace(url, `[СКАЧАТЬ: ${fileName}]`);
        }
        
        return {
            cleanContentWithoutLinks: cleanContent,
            downloadLinks: downloadLinks
        };
    }

    async renderDownloadButton(link) {
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
            this.renderFilePreview(container, link, null, fileType);
        } else {
            try {
                const mimeType = await this.fetchFileMimeType(link.url);
                this.renderFilePreview(container, link, mimeType);
            } catch (error) {
                console.error('Ошибка загрузки файла:', error);
                this.renderFilePreview(container, link, null);
            }
        }
        
        return container;
    }
    
    async fetchFileMimeType(url) {
        const fileId = url.split('/').pop();
        const infoUrl = url.replace(`/download/${fileId}`, `/info/${fileId}`);
        const response = await fetch(infoUrl);
        
        if (!response.ok) {
            return null;
        }
        
        const fileInfo = await response.json();
        return fileInfo.content_type;
    }
    
    renderFilePreview(container, link, mimeType = null, knownType = null) {
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
                <div class="file-preview image-preview" style="display:flex; flex-direction:column; align-items:flex-start; gap:6px;">
                    <img src="${link.url}" alt="${link.fileName}" 
                         style="max-width: 300px; max-height: 300px; border-radius: 8px; cursor: pointer; object-fit: contain; display:block;"
                         onclick="window.open('${link.url}', '_blank')"
                         onerror="this.parentElement.innerHTML='<div class=error-preview>❌ Не удалось загрузить изображение</div>'"
                    >
                    <div class="file-info" style="display:flex; justify-content: space-between; align-items: center; width:100%;">
                        <span class="file-name" style="font-size: 14px; color: #666;">${link.fileName}</span>
                        <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                            <i class="ti ti-download"></i> Скачать
                        </a>
                    </div>
                </div>
            `;
        } else if (fileType === 'video') {
            container.innerHTML = `
                <div class="file-preview video-preview" style="display:flex; flex-direction:column; align-items:flex-start; gap:6px;">
                    <video controls style="max-width: 400px; border-radius: 8px; display:block;">
                        <source src="${link.url}" type="${mimeType || 'video/mp4'}">
                        Ваш браузер не поддерживает видео.
                    </video>
                    <div class="file-info" style="display: flex; justify-content: space-between; align-items: center; width:100%;">
                        <span class="file-name" style="font-size: 14px; color: #666;">${link.fileName}</span>
                        <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                            <i class="ti ti-download"></i> Скачать
                        </a>
                    </div>
                </div>
            `;
        } else if (fileType === 'audio') {
            container.innerHTML = `
                <div class="file-preview audio-preview" style="display:flex; flex-direction:column; align-items:flex-start; gap:6px;">
                    <audio controls style="width: 300px;">
                        <source src="${link.url}" type="${mimeType || 'audio/mpeg'}">
                        Ваш браузер не поддерживает аудио.
                    </audio>
                    <div class="file-info" style="display: flex; justify-content: space-between; align-items: center; width:100%;">
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
                <div class="file-preview document-preview" style="display: flex; align-items: center; padding: 8px 10px; border: 1px solid #ddd; border-radius: 8px; background: #f8f9fa;">
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

    renderAttachments(attachments) {
        const container = document.createElement('div');
        container.className = 'message-attachments';
        
        attachments.forEach(attachment => {
            const attachmentElement = this.renderAttachment(attachment);
            container.appendChild(attachmentElement);
        });
        
        return container;
    }

    renderAttachment(attachment) {
        const div = document.createElement('div');
        div.className = 'chat-file';
        
        const displayType = this.getFileDisplayType(attachment.mime_type);
        
        if (displayType === 'image') {
            div.innerHTML = `
                <img src="${attachment.url}" alt="${attachment.name}" 
                     style="max-width: 200px; max-height: 200px; cursor: pointer;"
                     onclick="window.open('${attachment.url}', '_blank')">
                <div class="file-info">
                    <span>${attachment.name}</span>
                    <span>${formatFileSize(attachment.size)}</span>
                </div>
            `;
        } else {
            const icon = getFileIconEmoji(attachment.name);
            div.innerHTML = `
                <div class="d-flex align-items-center">
                    <span class="me-2">${icon}</span>
                    <div class="flex-grow-1">
                        <div>${attachment.name}</div>
                        <small class="text-muted">${formatFileSize(attachment.size)}</small>
                    </div>
                    <a href="${attachment.url}" target="_blank" class="btn btn-sm btn-outline-primary">
                        <i class="ti ti-download"></i>
                    </a>
                </div>
            `;
        }
        
        return div;
    }

    renderButtons(buttons) {
        const container = document.createElement('div');
        container.className = 'message-buttons mt-2';
        
        buttons.forEach(button => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-sm btn-outline-primary me-1 mb-1';
            btn.textContent = button.text;
            btn.onclick = () => this.handleButtonClick(button);
            container.appendChild(btn);
        });
        
        return container;
    }

    renderForm(form) {
        const div = document.createElement('div');
        div.className = 'message-form';
        div.innerHTML = `<p><strong>Форма:</strong> ${form.title}</p>`;
        return div;
    }

    handleButtonClick(button) {
        console.log('🔘 Нажата кнопка:', button);
    }

    getFileDisplayType(mimeType) {
        if (mimeType.startsWith('image/')) return 'image';
        if (mimeType.startsWith('video/')) return 'video';
        if (mimeType.startsWith('audio/')) return 'audio';
        return 'document';
    }
}

export default ChatMessageRenderer;
export { MESSAGE_TYPES };

