/**
 * Компонент загрузчика приложения
 * Универсальный загрузчик с AI-мозгом для полноэкранной и встроенной загрузки
 */
import '../utils/viewport-app-vh.js';
import '../utils/platform-deeplink-init.js';
import { html, css, svg } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

export class AppLoader extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 24px;
            }
            
            :host([fullscreen]) {
                position: fixed;
                inset: 0;
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 25%, #0f0f23 50%, #1a1a2e 75%, #16213e 100%);
                z-index: 9999;
                transition: opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            }
            
            :host([fullscreen])::before,
            :host([fullscreen])::after {
                content: '';
                position: fixed;
                border-radius: 50%;
                filter: blur(100px);
                opacity: 0.15;
                pointer-events: none;
            }
            
            :host([fullscreen])::before {
                width: 600px;
                height: 600px;
                background: #99A6F9;
                top: -200px;
                right: -200px;
            }
            
            :host([fullscreen])::after {
                width: 500px;
                height: 500px;
                background: #8b5cf6;
                bottom: -150px;
                left: -150px;
            }
            
            :host(.hidden) {
                opacity: 0;
                pointer-events: none;
            }
            
            .loader-logo {
                width: var(--logo-size, 120px);
                height: var(--logo-size, 120px);
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
            }
            
            :host([size="sm"]) .loader-logo {
                --logo-size: 60px;
            }
            
            :host([size="md"]) .loader-logo {
                --logo-size: 90px;
            }
            
            :host([size="lg"]) .loader-logo {
                --logo-size: 120px;
            }
            
            :host([size="xl"]) .loader-logo {
                --logo-size: 160px;
            }
            
            .loader-logo svg {
                width: 100%;
                height: 100%;
            }
            
            .ai-brain-core {
                fill: none;
                stroke: url(#brain-gradient);
                stroke-width: 2;
                stroke-linecap: round;
                stroke-linejoin: round;
                animation: rotate 8s linear infinite;
                transform-origin: center;
            }
            
            .ai-node {
                fill: #99A6F9;
                animation: pulse-node 2s ease-in-out infinite;
            }
            
            .ai-node:nth-child(2) { animation-delay: 0.2s; }
            .ai-node:nth-child(3) { animation-delay: 0.4s; }
            .ai-node:nth-child(4) { animation-delay: 0.6s; }
            .ai-node:nth-child(5) { animation-delay: 0.8s; }
            
            .ai-connection {
                stroke: #FF885C;
                stroke-width: 1.5;
                opacity: 0.4;
                animation: flow 2s ease-in-out infinite;
            }
            
            .ai-connection:nth-child(even) { animation-delay: 0.3s; }
            
            .ai-center-glow {
                fill: url(#glow-gradient);
                animation: glow 3s ease-in-out infinite;
            }
            
            .loader-text {
                font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 14px;
                font-weight: 500;
                color: rgba(255, 255, 255, 0.5);
                letter-spacing: 0.05em;
            }
            
            @keyframes rotate {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            @keyframes pulse-node {
                0%, 100% { 
                    transform: scale(1);
                    opacity: 1;
                }
                50% { 
                    transform: scale(1.3);
                    opacity: 0.8;
                }
            }
            
            @keyframes flow {
                0%, 100% { 
                    stroke-dashoffset: 0;
                    opacity: 0.3;
                }
                50% { 
                    stroke-dashoffset: 20;
                    opacity: 0.7;
                }
            }
            
            @keyframes glow {
                0%, 100% { 
                    opacity: 0.5;
                    transform: scale(1);
                }
                50% { 
                    opacity: 0.8;
                    transform: scale(1.1);
                }
            }
        `
    ];

    static properties = {
        size: { type: String },
        text: { type: String },
        fullscreen: { type: Boolean, reflect: true },
    };

    constructor() {
        super();
        this.size = 'lg';
        this.text = 'AI Studio';
        this.fullscreen = false;
    }

    render() {
        return html`
            <div class="loader-logo">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
                    <defs>
                        <linearGradient id="brain-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#99A6F9;stop-opacity:1" />
                            <stop offset="100%" style="stop-color:#FF885C;stop-opacity:1" />
                        </linearGradient>
                        <radialGradient id="glow-gradient" cx="50%" cy="50%" r="50%">
                            <stop offset="0%" style="stop-color:#99A6F9;stop-opacity:0.6" />
                            <stop offset="100%" style="stop-color:#FF885C;stop-opacity:0" />
                        </radialGradient>
                    </defs>
                    
                    <!-- Центральное свечение -->
                    <circle class="ai-center-glow" cx="60" cy="60" r="30"/>
                    
                    <!-- Внешние узлы -->
                    <circle class="ai-node" cx="60" cy="20" r="6"/>
                    <circle class="ai-node" cx="95" cy="45" r="6"/>
                    <circle class="ai-node" cx="95" cy="75" r="6"/>
                    <circle class="ai-node" cx="60" cy="100" r="6"/>
                    <circle class="ai-node" cx="25" cy="75" r="6"/>
                    <circle class="ai-node" cx="25" cy="45" r="6"/>
                    
                    <!-- Соединения между узлами -->
                    <g class="ai-brain-core">
                        <path class="ai-connection" d="M60,20 L60,40" stroke-dasharray="4 2"/>
                        <path class="ai-connection" d="M95,45 L75,50" stroke-dasharray="4 2"/>
                        <path class="ai-connection" d="M95,75 L75,70" stroke-dasharray="4 2"/>
                        <path class="ai-connection" d="M60,100 L60,80" stroke-dasharray="4 2"/>
                        <path class="ai-connection" d="M25,75 L45,70" stroke-dasharray="4 2"/>
                        <path class="ai-connection" d="M25,45 L45,50" stroke-dasharray="4 2"/>
                        
                        <!-- Внутренние связи -->
                        <path class="ai-connection" d="M50,45 L70,45" stroke-dasharray="3 2"/>
                        <path class="ai-connection" d="M50,60 L70,60" stroke-dasharray="3 2"/>
                        <path class="ai-connection" d="M50,75 L70,75" stroke-dasharray="3 2"/>
                        <path class="ai-connection" d="M50,50 L70,70" stroke-dasharray="3 2"/>
                        <path class="ai-connection" d="M50,70 L70,50" stroke-dasharray="3 2"/>
                    </g>
                    
                    <!-- Центральный узел -->
                    <circle cx="60" cy="60" r="12" fill="#99A6F9" opacity="0.9">
                        <animate attributeName="r" values="12;14;12" dur="2s" repeatCount="indefinite"/>
                        <animate attributeName="opacity" values="0.9;1;0.9" dur="2s" repeatCount="indefinite"/>
                    </circle>
                    
                    <!-- Искры AI -->
                    <circle cx="60" cy="60" r="8" fill="none" stroke="#FF885C" stroke-width="1.5" opacity="0.6">
                        <animate attributeName="r" values="8;20;8" dur="3s" repeatCount="indefinite"/>
                        <animate attributeName="opacity" values="0.6;0;0.6" dur="3s" repeatCount="indefinite"/>
                    </circle>
                </svg>
            </div>
            ${this.text ? html`<div class="loader-text">${this.text}</div>` : ''}
        `;
    }
}

customElements.define('app-loader', AppLoader);

