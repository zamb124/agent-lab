/**
 * Animations - общие анимации и transitions
 */
import { css } from 'lit';

export const animationStyles = css`
    .transition-fast {
        transition: all var(--duration-fast) var(--easing-default);
    }
    
    .transition-normal {
        transition: all var(--duration-normal) var(--easing-default);
    }
    
    .transition-slow {
        transition: all var(--duration-slow) var(--easing-default);
    }
    
    .transition-spring {
        transition: all var(--duration-normal) var(--easing-spring);
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


