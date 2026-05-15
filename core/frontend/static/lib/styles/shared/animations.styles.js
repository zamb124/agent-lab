/**
 * Animations - общие анимации и transitions
 */
import { css } from 'lit';

export const animationStyles = css`
    .transition-fast {
        transition: var(--motion-transition-interactive);
    }
    
    .transition-normal {
        transition: var(--motion-transition-interactive);
    }
    
    .transition-slow {
        transition:
            background-color var(--duration-slow) var(--easing-default),
            border-color var(--duration-slow) var(--easing-default),
            color var(--duration-slow) var(--easing-default),
            box-shadow var(--duration-slow) var(--easing-default),
            opacity var(--duration-slow) var(--easing-default),
            transform var(--duration-slow) var(--easing-default);
    }
    
    .transition-spring {
        transition:
            background-color var(--duration-normal) var(--easing-spring),
            border-color var(--duration-normal) var(--easing-spring),
            color var(--duration-normal) var(--easing-spring),
            box-shadow var(--duration-normal) var(--easing-spring),
            opacity var(--duration-normal) var(--easing-spring),
            transform var(--duration-normal) var(--easing-spring);
    }
    
    @keyframes fadeIn {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }
    
    @keyframes fadeOut {
        from {
            opacity: 1;
        }
        to {
            opacity: 0;
        }
    }
    
    @keyframes slideInUp {
        from {
            transform: translateY(20px);
            opacity: 0;
        }
        to {
            transform: translateY(0);
            opacity: 1;
        }
    }
    
    @keyframes slideInDown {
        from {
            transform: translateY(-20px);
            opacity: 0;
        }
        to {
            transform: translateY(0);
            opacity: 1;
        }
    }
    
    .animate-fade-in {
        animation: fadeIn var(--duration-normal) var(--easing-default);
    }
    
    .animate-slide-in-up {
        animation: slideInUp var(--duration-normal) var(--easing-spring);
    }
    
    .animate-slide-in-down {
        animation: slideInDown var(--duration-normal) var(--easing-spring);
    }
`;

