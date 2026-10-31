package ru.humanitec.app;

import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Message;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebChromeClient;

import java.util.Locale;

/**
 * Перехватывает window.open / target=_blank в Android WebView.
 *
 * Дефолтный BridgeWebChromeClient в Capacitor не реализует onCreateWindow:
 * с setSupportMultipleWindows(true) такие переходы просто игнорируются.
 * Здесь URL извлекаем через временный WebView (стандартный приём Android),
 * затем для внутри-продуктовых хостов делаем loadUrl в основном WebView,
 * для внешних — Intent.ACTION_VIEW.
 *
 * Множество допустимых хостов: server URL, local URL и server.allowNavigation
 * из capacitor.config.json — тот же список, по которому работает
 * BridgeWebViewClient.shouldOverrideUrlLoading + Bridge.launchIntent.
 */
public class HumanitecBridgeWebChromeClient extends BridgeWebChromeClient {

    private final Bridge bridge;

    public HumanitecBridgeWebChromeClient(Bridge bridge) {
        super(bridge);
        this.bridge = bridge;
    }

    @Override
    public boolean onCreateWindow(WebView view, boolean isDialog, boolean isUserGesture, Message resultMsg) {
        Context context = view.getContext();
        WebView resolver = new WebView(context);
        resolver.setWebViewClient(new UrlResolverWebViewClient(view));
        WebView.WebViewTransport transport = (WebView.WebViewTransport) resultMsg.obj;
        transport.setWebView(resolver);
        resultMsg.sendToTarget();
        return true;
    }

    private boolean shouldKeepInWebView(String url) {
        Uri parsed = Uri.parse(url);
        String host = parsed.getHost();
        if (host == null || host.isEmpty()) {
            return false;
        }
        String scheme = parsed.getScheme();
        if (scheme == null) {
            return false;
        }
        if (!scheme.equalsIgnoreCase("http") && !scheme.equalsIgnoreCase("https")) {
            return false;
        }
        String hostLower = host.toLowerCase(Locale.ROOT);

        String serverUrl = bridge.getServerUrl();
        if (matchesUrlHost(hostLower, serverUrl)) {
            return true;
        }
        String localUrl = bridge.getLocalUrl();
        if (matchesUrlHost(hostLower, localUrl)) {
            return true;
        }

        String[] allowNav = bridge.getConfig().getAllowNavigation();
        if (allowNav != null) {
            for (String pattern : allowNav) {
                if (matchesPattern(hostLower, pattern)) {
                    return true;
                }
            }
        }
        return false;
    }

    private boolean matchesUrlHost(String host, String urlString) {
        if (urlString == null || urlString.isEmpty()) {
            return false;
        }
        Uri parsed = Uri.parse(urlString);
        String other = parsed.getHost();
        if (other == null) {
            return false;
        }
        return host.equals(other.toLowerCase(Locale.ROOT));
    }

    private boolean matchesPattern(String host, String pattern) {
        if (pattern == null || pattern.isEmpty()) {
            return false;
        }
        String p = pattern.toLowerCase(Locale.ROOT);
        if (p.startsWith("*.")) {
            String suffix = p.substring(1); // ".example.com"
            String apex = p.substring(2);   // "example.com"
            return host.equals(apex) || host.endsWith(suffix);
        }
        return host.equals(p);
    }

    private void handleNewWindowUrl(WebView mainWebView, String url) {
        if (url == null || url.isEmpty()) {
            return;
        }
        if (shouldKeepInWebView(url)) {
            mainWebView.loadUrl(url);
            return;
        }
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            mainWebView.getContext().startActivity(intent);
        } catch (ActivityNotFoundException ignored) {
        }
    }

    /**
     * Временный WebView нужен только для извлечения URL из onCreateWindow:
     * shouldOverrideUrlLoading даёт целевой URL, после чего экземпляр уничтожается.
     */
    private final class UrlResolverWebViewClient extends WebViewClient {

        private final WebView mainWebView;

        UrlResolverWebViewClient(WebView mainWebView) {
            this.mainWebView = mainWebView;
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            handleNewWindowUrl(mainWebView, request.getUrl().toString());
            view.destroy();
            return true;
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            handleNewWindowUrl(mainWebView, url);
            view.destroy();
            return true;
        }
    }
}
