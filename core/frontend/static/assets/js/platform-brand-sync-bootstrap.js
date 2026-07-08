(function () {
    try {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '/frontend/api/platform/brand', false);
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.send(null);
        if (xhr.status !== 200) {
            return;
        }
        var brand = JSON.parse(xhr.responseText);
        var hostname = window.location.hostname;
        var rawPort = window.location.port;
        var portSuffix = '';
        if (rawPort && rawPort !== '80' && rawPort !== '443') {
            portSuffix = ':' + rawPort;
        }
        var baseDomain = String(brand.base_domain || '');
        if (baseDomain === '') {
            if (hostname === 'localhost' || hostname.endsWith('.localhost')) {
                baseDomain = 'localhost';
            } else if (hostname === 'lvh.me' || hostname.endsWith('.lvh.me')) {
                baseDomain = 'lvh.me';
            } else if (/^(?:\d{1,3}\.){3}\d{1,3}$/.test(hostname)) {
                baseDomain = hostname;
            }
        }
        var protocol = window.location.protocol.replace(':', '');
        var isProduction = protocol === 'https' && portSuffix === '';
        window.__PLATFORM_BRAND__ = {
            platformName: String(brand.platform_name || 'Platform'),
            agentProductName: String(brand.agent_product_name || 'Platform Agent'),
            modelsProductName: String(brand.models_product_name || 'Platform Models'),
            voiceProductName: String(brand.voice_product_name || 'Platform Voice'),
            llmsDisplayLabel: String(brand.llms_display_label || 'Platform LLMs'),
            flowsProductLabel: String(brand.flows_product_label || 'Platform Flows'),
            supportEmail: String(brand.support_email || ''),
            logoPath: String(brand.logo_path || ''),
            apexOrigin: String(brand.apex_origin || ''),
            supportedDomains: Array.isArray(brand.supported_domains) ? brand.supported_domains : [],
            baseDomain: baseDomain,
            isProduction: isProduction,
            portSuffix: portSuffix,
            protocol: protocol,
        };
    } catch (_err) {
        /* brand bootstrap optional before module load */
    }
})();
