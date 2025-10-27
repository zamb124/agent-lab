/**
 * Billing Module - Billing management
 */

import { showNotification } from '/static/js/components/notification.js';
import { createPayment, getBillingStats } from '/static/js/api/payments.js';

export default class BillingModule {
    constructor(app) {
        this.app = app;
        this.name = 'billing';
        this.version = '1.0.0';
        this.statsRefreshInterval = null;
    }
    
    async init() {
        console.log('💰 ' + this.app.i18n.t('billing.init_message'));
        
        this.setupGlobalFunctions();
        this.setupEventListeners();
        this.startStatsRefresh();
        this.checkPaymentStatus();
        
        return this;
    }
    
    setupGlobalFunctions() {
        window.openPaymentModal = () => this.openPaymentModal();
        window.closePaymentModal = () => this.closePaymentModal();
        window.createPayment = () => this.handleCreatePayment();
        console.log('✅ ' + this.app.i18n.t('billing.functions_registered'));
    }
    
    setupEventListeners() {
        document.addEventListener('click', (e) => {
            const modal = document.getElementById('payment-modal');
            if (modal && e.target === modal) {
                this.closePaymentModal();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closePaymentModal();
            }
        });
    }
    
    openPaymentModal() {
        const modal = document.getElementById('payment-modal');
        if (modal) {
            modal.classList.add('active');
            document.getElementById('payment-amount').value = '1000';
        }
    }

    closePaymentModal() {
        const modal = document.getElementById('payment-modal');
        if (modal) {
            modal.classList.remove('active');
        }
    }

    async handleCreatePayment() {
        const amountInput = document.getElementById('payment-amount');
        const providerSelect = document.getElementById('payment-provider');
        const submitBtn = document.getElementById('payment-submit-btn');
        
        const amount = parseFloat(amountInput.value);
        
        if (!amount || amount < 100) {
            showNotification(this.app.i18n.t('billing.validation.min_amount', { amount: '100₽' }), 'error');
            return;
        }
        
        if (amount > 1000000) {
            showNotification(this.app.i18n.t('billing.validation.max_amount', { amount: '1,000,000₽' }), 'error');
            return;
        }
        
        const provider = providerSelect ? providerSelect.value : null;
        
        submitBtn.disabled = true;
        submitBtn.textContent = this.app.i18n.t('billing.creating_payment');
        
        try {
            const data = await createPayment(amount, provider);
            
            showNotification(this.app.i18n.t('billing.redirecting_to_payment'), 'info');
            
            setTimeout(() => {
                window.location.href = data.payment_url;
            }, 500);
            
        } catch (error) {
            console.error(this.app.i18n.t('billing.errors.payment_creation'), error);
            showNotification(`Ошибка: ${error.message}`, 'error');
            
            submitBtn.disabled = false;
            submitBtn.textContent = this.app.i18n.t('billing.modal.proceed_to_payment');
        }
    }

    startStatsRefresh() {
        this.statsRefreshInterval = setInterval(async () => {
            try {
                const data = await getBillingStats();
                this.updateStatsDisplay(data);
            } catch (error) {
                console.error(this.app.i18n.t('billing.errors.stats_update'), error);
            }
        }, 30000);
    }

    stopStatsRefresh() {
        if (this.statsRefreshInterval) {
            clearInterval(this.statsRefreshInterval);
            this.statsRefreshInterval = null;
        }
    }

    updateStatsDisplay(data) {
        const budgetSpent = document.querySelector('.budget-spent');
        if (budgetSpent && data.current_month_spent !== undefined) {
            budgetSpent.textContent = `${data.current_month_spent.toFixed(2)} ₽`;
        }

        if (data.monthly_budget > 0) {
            const progressFill = document.querySelector('.progress-fill');
            const progressLabel = document.querySelector('.progress-label');
            const percent = Math.min(100, (data.current_month_spent / data.monthly_budget) * 100);
            
            if (progressFill) {
                progressFill.style.width = `${percent}%`;
            }
            
            if (progressLabel) {
                progressLabel.textContent = `${percent.toFixed(1)}% использовано`;
            }
        }

        if (data.stats) {
            const totalCalls = document.querySelector('.stat-card:nth-child(1) .stat-value');
            const totalCost = document.querySelector('.stat-card:nth-child(2) .stat-value');
            
            if (totalCalls && data.stats.total_calls !== undefined) {
                totalCalls.textContent = data.stats.total_calls;
            }
            
            if (totalCost && data.stats.total_cost !== undefined) {
                totalCost.textContent = `${data.stats.total_cost.toFixed(2)} ₽`;
            }
        }
    }
    
    checkPaymentStatus() {
        const urlParams = new URLSearchParams(window.location.search);
        const paymentStatus = urlParams.get('payment');
        const transactionId = urlParams.get('transaction_id');
        
        if (paymentStatus === 'success' && transactionId) {
            showNotification(this.app.i18n.t('billing.payment_success_message'), 'success');
            
            setTimeout(async () => {
                try {
                    const data = await getBillingStats();
                    this.updateStatsDisplay(data);
                    
                    const balanceElement = document.querySelector('.balance-amount');
                    if (balanceElement && data.balance !== undefined) {
                        balanceElement.textContent = `${data.balance.toFixed(2)} ₽`;
                    }
                } catch (error) {
                    console.error(this.app.i18n.t('billing.errors.stats_refresh'), error);
                }
                
                window.history.replaceState({}, '', '/frontend/billing');
            }, 2000);
            
        } else if (paymentStatus === 'fail' && transactionId) {
            showNotification(this.app.i18n.t('billing.payment_error_message'), 'error');
            
            setTimeout(() => {
                window.history.replaceState({}, '', '/frontend/billing');
            }, 3000);
        }
    }
    
    destroy() {
        console.log('🧹 ' + this.app.i18n.t('billing.module_unloaded'));
        this.stopStatsRefresh();
    }
}

