/**
 * LayoutManager - управление лейаутом и навигацией
 */
class LayoutManager {
    constructor() {
        this.sidebarCollapsed = false;
        this.isMobile = false;
        this.init();
    }
    
    init() {
        this.checkMobile();
        this.loadSidebarState();
        this.setupSidebar();
        this.setupMobileMenu();
        this.setupNavigation();
        this.setupResize();
    }
    
    checkMobile() {
        this.isMobile = window.innerWidth <= 768;
    }
    
    loadSidebarState() {
        // Загружаем состояние сайдбара из localStorage
        const savedState = localStorage.getItem('sidebar-collapsed');
        if (savedState === 'true' && !this.isMobile) {
            this.sidebarCollapsed = true;
            this.applySidebarState();
        }
    }
    
    setupSidebar() {
        // Кнопка сворачивания сайдбара
        const collapseBtn = document.querySelector('[data-sidebar-toggle]');
        console.log('🔍 Кнопка сайдбара найдена:', collapseBtn);
        if (collapseBtn) {
            collapseBtn.addEventListener('click', () => {
                console.log('🔄 Клик по кнопке сайдбара');
                this.toggleSidebar();
            });
        }
    }
    
    setupMobileMenu() {
        // Мобильное меню
        const toggleBtn = document.querySelector('.mobile-menu-toggle');
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        
        console.log('🔍 Мобильное меню - кнопка:', toggleBtn, 'sidebar:', sidebar);
        
        if (toggleBtn && sidebar) {
            toggleBtn.addEventListener('click', () => {
                console.log('🔄 Клик по мобильному меню');
                
                const isOpen = sidebar.classList.contains('open');
                
                if (isOpen) {
                    // Закрываем меню
                    sidebar.classList.remove('open');
                    sidebar.style.setProperty('transform', 'translateX(-100%)', 'important');
                    overlay?.classList.remove('active');
                } else {
                    // Открываем меню
                    sidebar.classList.add('open');
                    sidebar.style.setProperty('transform', 'translateX(0)', 'important');
                    overlay?.classList.add('active');
                }
                
                console.log('🔍 Меню', isOpen ? 'закрыто' : 'открыто');
            });
        }
        
        if (overlay) {
            overlay.addEventListener('click', () => {
                this.closeMobileMenu();
            });
        }
        
        // Закрываем меню при клике на навигационные ссылки
        const navLinks = document.querySelectorAll('.sidebar-nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', () => {
                if (this.isMobile) {
                    this.closeMobileMenu();
                }
            });
        });
    }
    
    setupNavigation() {
        // Активные ссылки в сайдбаре
        const sidebarLinks = document.querySelectorAll('.sidebar-nav-link');
        
        sidebarLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                // Убираем активный класс у всех ссылок
                sidebarLinks.forEach(l => l.classList.remove('active'));
                // Добавляем активный класс к текущей ссылке
                e.currentTarget.classList.add('active');
                
                // На мобильных закрываем меню после клика
                if (this.isMobile) {
                    this.closeMobileMenu();
                }
            });
        });
    }
    
    setupResize() {
        // Отслеживаем изменение размера экрана
        window.addEventListener('resize', () => {
            const wasMobile = this.isMobile;
            this.checkMobile();
            
            // Если перешли с мобильного на десктоп
            if (wasMobile && !this.isMobile) {
                this.resetToDesktop();
            }
            
            // Если перешли с десктопа на мобильный
            if (!wasMobile && this.isMobile) {
                this.expandSidebar();
            }
        });
    }
    
    resetToDesktop() {
        const sidebar = document.querySelector('.sidebar');
        const mainContent = document.querySelector('.main-content');
        const overlay = document.querySelector('.sidebar-overlay');
        
        if (sidebar) {
            // Убираем все мобильные стили и классы
            sidebar.style.removeProperty('transform');
            sidebar.classList.remove('open');
        }
        if (mainContent) {
            mainContent.style.removeProperty('margin-left');
        }
        if (overlay) {
            overlay.classList.remove('active');
        }
        
        // Применяем состояние десктопного сайдбара
        this.applySidebarState();
    }
    
    toggleMobileMenu() {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        
        if (!sidebar) return;
        
        const isOpen = sidebar.classList.contains('open');
        
        if (isOpen) {
            // Закрываем меню
            sidebar.classList.remove('open');
            sidebar.style.setProperty('transform', 'translateX(-100%)', 'important');
            overlay?.classList.remove('active');
        } else {
            // Открываем меню
            sidebar.classList.add('open');
            sidebar.style.setProperty('transform', 'translateX(0)', 'important');
            overlay?.classList.add('active');
        }
    }
    
    closeMobileMenu() {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        
        if (sidebar) {
            sidebar.classList.remove('open');
            sidebar.style.setProperty('transform', 'translateX(-100%)', 'important');
        }
        if (overlay) {
            overlay.classList.remove('active');
        }
    }
    
    toggleSidebar() {
        console.log('🔄 toggleSidebar вызван, isMobile:', this.isMobile);
        if (this.isMobile) {
            // На мобильных не сворачиваем, а открываем/закрываем
            console.log('📱 Мобильное устройство - пропускаем');
            return;
        }
        
        this.sidebarCollapsed = !this.sidebarCollapsed;
        console.log('🔄 Новое состояние сайдбара:', this.sidebarCollapsed);
        this.applySidebarState();
        this.saveSidebarState();
    }
    
    applySidebarState() {
        const sidebar = document.querySelector('.sidebar');
        const mainContent = document.querySelector('.main-content');
        
        if (!sidebar || !mainContent) return;
        
        if (this.sidebarCollapsed && !this.isMobile) {
            sidebar.style.setProperty('width', '60px', 'important');
            mainContent.style.setProperty('margin-left', '60px', 'important');
            sidebar.classList.add('collapsed');
            mainContent.classList.add('sidebar-collapsed');
        } else {
            // Убираем inline стили - возвращаем к CSS переменным
            sidebar.style.removeProperty('width');
            mainContent.style.removeProperty('margin-left');
            sidebar.classList.remove('collapsed');
            mainContent.classList.remove('sidebar-collapsed');
        }
        
        // Обновляем иконку кнопки
        this.updateToggleIcon();
    }
    
    updateToggleIcon() {
        const toggleBtn = document.querySelector('button[onclick*="toggleSidebar"] i');
        if (toggleBtn) {
            toggleBtn.className = this.sidebarCollapsed ? 'bi bi-chevron-right' : 'bi bi-chevron-left';
        }
    }
    
    expandSidebar() {
        this.sidebarCollapsed = false;
        this.applySidebarState();
        this.saveSidebarState();
    }
    
    collapseSidebar() {
        this.sidebarCollapsed = true;
        this.applySidebarState();
        this.saveSidebarState();
    }
    
    closeMobileMenu() {
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        
        sidebar?.classList.remove('open');
        overlay?.classList.remove('active');
    }
    
    saveSidebarState() {
        localStorage.setItem('sidebar-collapsed', this.sidebarCollapsed.toString());
    }
    
    // Публичные методы для внешнего использования
    getSidebarState() {
        return {
            collapsed: this.sidebarCollapsed,
            isMobile: this.isMobile
        };
    }
}

export default LayoutManager;
