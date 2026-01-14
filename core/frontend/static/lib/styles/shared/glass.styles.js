/**
 * Glass Morphism - общие стили для glassmorphism эффектов
 * Используются во всех компонентах платформы
 */
import { css } from 'lit';

export const glassStyles = css`
    .glass-subtle {
        background: var(--glass-bg-subtle);
        backdrop-filter: blur(var(--glass-blur-subtle));
        -webkit-backdrop-filter: blur(var(--glass-blur-subtle));
        border: 1px solid var(--glass-border-subtle);
        box-shadow: var(--glass-shadow-subtle), var(--glass-inner-glow-subtle);
    }
    
    .glass-medium {
        background: var(--glass-bg-medium);
        backdrop-filter: blur(var(--glass-blur-medium));
        -webkit-backdrop-filter: blur(var(--glass-blur-medium));
        border: 1px solid var(--glass-border-medium);
        box-shadow: var(--glass-shadow-medium), var(--glass-inner-glow-medium);
    }
    
    .glass-strong {
        background: var(--glass-bg-strong);
        backdrop-filter: blur(var(--glass-blur-strong));
        -webkit-backdrop-filter: blur(var(--glass-blur-strong));
        border: 1px solid var(--glass-border-strong);
        box-shadow: var(--glass-shadow-strong), var(--glass-inner-glow-strong);
    }
    
    .glass-interactive {
        transition: all var(--duration-normal) var(--easing-default);
    }
    
    .glass-interactive:hover {
        border-color: var(--glass-border-glow);
        box-shadow: var(--glass-shadow-medium), var(--glass-inner-glow-medium), var(--hover-glow);
        transform: translateY(-1px);
    }
`;


