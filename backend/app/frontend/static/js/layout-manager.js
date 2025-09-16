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
        if (collapseBtn) {
            collapseBtn.addEventListener('click', () => this.toggleSidebar());
        }
    }
    
    setupMobileMenu() {
        // Мобильное меню
        const toggleBtn = document.querySelector('.mobile-menu-toggle');
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        
        if (toggleBtn && sidebar) {
            toggleBtn.addEventListener('click', () => {
                sidebar.classList.toggle('open');
                overlay?.classList.toggle('active');
            });
        }
        
        if (overlay) {
            overlay.addEventListener('click', () => {
                sidebar?.classList.remove('open');
                overlay.classList.remove('active');
            });
        }
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
                this.closeMobileMenu();
                this.applySidebarState();
            }
            
            // Если перешли с десктопа на мобильный
            if (!wasMobile && this.isMobile) {
                this.expandSidebar();
            }
        });
    }
    
    toggleSidebar() {
        if (this.isMobile) {
            // На мобильных не сворачиваем, а открываем/закрываем
            return;
        }
        
        this.sidebarCollapsed = !this.sidebarCollapsed;
        this.applySidebarState();
        this.saveSidebarState();
    }
    
    applySidebarState() {
        const sidebar = document.querySelector('.sidebar');
        const mainContent = document.querySelector('.main-content');
        
        if (!sidebar || !mainContent) return;
        
        if (this.sidebarCollapsed && !this.isMobile) {
            sidebar.classList.add('collapsed');
            mainContent.classList.add('sidebar-collapsed');
        } else {
            sidebar.classList.remove('collapsed');
            mainContent.classList.remove('sidebar-collapsed');
        }
        
        // Обновляем иконку кнопки
        this.updateToggleIcon();
    }
    
    updateToggleIcon() {
        const toggleBtn = document.querySelector('[data-sidebar-toggle] i');
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
