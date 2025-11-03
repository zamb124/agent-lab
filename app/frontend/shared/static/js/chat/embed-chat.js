/**
 * Embed Chat Widget - простой способ встроить чат на любой сайт
 * 
 * Использование:
 * <script src="https://your-domain.com/static/js/chat/embed-chat.js"></script>
 * <script>
 *   EmbedChat.init({
 *     apiUrl: 'https://your-domain.com',
 *     token: 'your-token',
 *     flowId: 'app.flows.faq_flow.faq_flow_config',
 *     position: 'bottom-right', // или 'bottom-left'
 *     theme: 'light' // или 'dark'
 *   });
 * </script>
 */

(function(window, document) {
    'use strict';

    class EmbedChat {
        constructor() {
            this.config = null;
            this.iframe = null;
            this.button = null;
            this.isOpen = false;
            this.container = null;
        }

        init(config) {
            if (!config || !config.apiUrl || !config.token || !config.flowId) {
                console.error('❌ EmbedChat: Необходимы параметры apiUrl, token и flowId');
                return;
            }

            this.config = {
                apiUrl: config.apiUrl.replace(/\/$/, ''),
                token: config.token,
                flowId: config.flowId,
                position: config.position || 'bottom-right',
                theme: config.theme || 'light',
                sessionId: config.sessionId || null,
                userId: config.userId || null,
                buttonText: config.buttonText || '',
                buttonIcon: config.buttonIcon || '💬'
            };

            this.createButton();
            this.attachStyles();
        }

        createButton() {
            this.button = document.createElement('button');
            this.button.id = 'embed-chat-button';
            this.button.className = 'embed-chat-button';
            this.button.setAttribute('aria-label', 'Открыть чат');
            this.button.innerHTML = this.config.buttonIcon;
            
            if (this.config.buttonText) {
                const text = document.createElement('span');
                text.className = 'embed-chat-button-text';
                text.textContent = this.config.buttonText;
                this.button.appendChild(text);
            }

            this.button.addEventListener('click', () => this.toggleChat());
            document.body.appendChild(this.button);
        }

        toggleChat() {
            if (this.isOpen) {
                this.closeChat();
            } else {
                this.openChat();
            }
        }

        openChat() {
            if (this.isOpen) return;

            this.isOpen = true;
            this.button.classList.add('active');

            this.container = document.createElement('div');
            this.container.id = 'embed-chat-container';
            this.container.className = 'embed-chat-container';

            this.iframe = document.createElement('iframe');
            this.iframe.id = 'embed-chat-iframe';
            this.iframe.className = 'embed-chat-iframe';
            this.iframe.allow = 'microphone';
            this.iframe.frameBorder = '0';
            this.iframe.scrolling = 'no';

            const params = new URLSearchParams({
                token: this.config.token,
                flow_id: this.config.flowId,
                mode: 'expanded',
                theme: this.config.theme
            });

            if (this.config.sessionId) {
                params.append('session_id', this.config.sessionId);
            }

            if (this.config.userId) {
                params.append('user_id', this.config.userId);
            }

            this.iframe.src = `${this.config.apiUrl}/frontend/chat/embed?${params.toString()}`;

            this.container.appendChild(this.iframe);

            const closeButton = document.createElement('button');
            closeButton.className = 'embed-chat-close';
            closeButton.innerHTML = '×';
            closeButton.setAttribute('aria-label', 'Закрыть чат');
            closeButton.addEventListener('click', () => this.closeChat());
            this.container.appendChild(closeButton);

            document.body.appendChild(this.container);

            setTimeout(() => {
                this.container.classList.add('visible');
            }, 10);

            this.updateButtonText('Закрыть');
        }

        closeChat() {
            if (!this.isOpen) return;

            this.isOpen = false;
            this.button.classList.remove('active');

            if (this.container) {
                this.container.classList.remove('visible');
                setTimeout(() => {
                    if (this.container && this.container.parentNode) {
                        this.container.parentNode.removeChild(this.container);
                    }
                    this.container = null;
                    this.iframe = null;
                }, 300);
            }

            this.updateButtonText();
        }

        updateButtonText(text) {
            if (!this.config.buttonText) return;

            const textElement = this.button.querySelector('.embed-chat-button-text');
            if (textElement) {
                textElement.textContent = text || this.config.buttonText;
            }
        }

        attachStyles() {
            if (document.getElementById('embed-chat-styles')) return;

            const style = document.createElement('style');
            style.id = 'embed-chat-styles';
            style.textContent = `
                .embed-chat-button {
                    position: fixed;
                    ${this.config.position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
                    bottom: 20px;
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border: none;
                    color: white;
                    font-size: 24px;
                    cursor: pointer;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                    z-index: 999999;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: all 0.3s ease;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                }

                .embed-chat-button:hover {
                    transform: scale(1.1);
                    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
                }

                .embed-chat-button.active {
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                }

                .embed-chat-button-text {
                    margin-left: 8px;
                    font-size: 14px;
                    font-weight: 500;
                }

                .embed-chat-container {
                    position: fixed;
                    ${this.config.position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
                    bottom: 90px;
                    width: 380px;
                    height: 600px;
                    max-width: calc(100vw - 40px);
                    max-height: calc(100vh - 100px);
                    border-radius: 12px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
                    z-index: 999998;
                    opacity: 0;
                    transform: translateY(20px) scale(0.95);
                    transition: all 0.3s ease;
                    pointer-events: none;
                    background: white;
                }

                .embed-chat-container.visible {
                    opacity: 1;
                    transform: translateY(0) scale(1);
                    pointer-events: all;
                }

                .embed-chat-iframe {
                    width: 100%;
                    height: 100%;
                    border: none;
                    border-radius: 12px;
                }

                .embed-chat-close {
                    position: absolute;
                    top: -12px;
                    ${this.config.position === 'bottom-left' ? 'right: -12px;' : 'right: -12px;'}
                    width: 32px;
                    height: 32px;
                    border-radius: 50%;
                    background: #ff4757;
                    border: 2px solid white;
                    color: white;
                    font-size: 20px;
                    line-height: 1;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
                    transition: all 0.2s ease;
                    z-index: 999999;
                }

                .embed-chat-close:hover {
                    background: #ff3838;
                    transform: scale(1.1);
                }

                @media (max-width: 768px) {
                    .embed-chat-container {
                        width: calc(100vw - 20px);
                        height: calc(100vh - 100px);
                        ${this.config.position === 'bottom-left' ? 'left: 10px;' : 'right: 10px;'}
                        bottom: 80px;
                    }

                    .embed-chat-button {
                        ${this.config.position === 'bottom-left' ? 'left: 15px;' : 'right: 15px;'}
                        bottom: 15px;
                        width: 56px;
                        height: 56px;
                    }
                }
            `;
            document.head.appendChild(style);
        }

        destroy() {
            this.closeChat();
            if (this.button && this.button.parentNode) {
                this.button.parentNode.removeChild(this.button);
            }
            const styles = document.getElementById('embed-chat-styles');
            if (styles) {
                styles.parentNode.removeChild(styles);
            }
        }
    }

    window.EmbedChat = new EmbedChat();
})(window, document);






