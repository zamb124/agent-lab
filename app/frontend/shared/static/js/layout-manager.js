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
        const toggleBtn = document.querySelector('.mobile-menu-toggle');
        const sidebar = document.querySelector('.sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        
        console.log('🔍 Мобильное меню - кнопка:', toggleBtn, 'sidebar:', sidebar);
        
        if (toggleBtn && sidebar) {
            toggleBtn.addEventListener('click', () => {
                console.log('🔄 Клик по мобильному меню');
                this.toggleMobileMenu();
            });
        }
        
        if (overlay) {
            overlay.addEventListener('click', () => {
                console.log('🔄 Клик по overlay - закрываем меню');
                this.closeMobileMenu();
            });
        }
        
        const navLinks = document.querySelectorAll('.sidebar-nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', () => {
                if (this.isMobile) {
                    console.log('🔄 Клик по пункту меню на мобильном - закрываем sidebar');
                    setTimeout(() => this.closeMobileMenu(), 100);
                }
            });
        });
        
        document.addEventListener('click', (e) => {
            if (!this.isMobile) return;
            
            const sidebar = document.querySelector('.sidebar');
            if (!sidebar || !sidebar.classList.contains('open')) return;
            
            const clickedInsideSidebar = sidebar.contains(e.target);
            const clickedToggleBtn = e.target.closest('.mobile-menu-toggle');
            
            if (!clickedInsideSidebar && !clickedToggleBtn) {
                console.log('🔄 Клик вне sidebar на мобильном - закрываем');
                this.closeMobileMenu();
            }
        });
    }
    
    setupNavigation() {
        const sidebarLinks = document.querySelectorAll('.sidebar-nav-link');
        
        sidebarLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                sidebarLinks.forEach(l => l.classList.remove('active'));
                e.currentTarget.classList.add('active');
                
                if (this.isMobile) {
                    console.log('🔄 Клик по навигационной ссылке на мобильном - закрываем sidebar');
                    setTimeout(() => this.closeMobileMenu(), 100);
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
    
    toggleSidebar() {
        console.log('🔄 toggleSidebar вызван, isMobile:', this.isMobile);
        if (this.isMobile) {
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
            sidebar.classList.add('collapsed');
            document.body.classList.add('sidebar-collapsed');
        } else {
            sidebar.classList.remove('collapsed');
            document.body.classList.remove('sidebar-collapsed');
        }
        
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
        
        if (sidebar) {
            sidebar.classList.remove('open');
            sidebar.style.setProperty('transform', 'translateX(-100%)', 'important');
        }
        if (overlay) {
            overlay.classList.remove('active');
        }
        
        console.log('✅ Мобильное меню закрыто');
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
