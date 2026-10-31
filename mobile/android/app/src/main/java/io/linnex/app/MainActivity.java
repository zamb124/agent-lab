package ru.humanitec.app;

import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;

/**
 * Точка входа Android-оболочки Humanitec.
 *
 * После super.onCreate бридж уже создал WebView с дефолтным BridgeWebChromeClient
 * (он не обрабатывает window.open / target=_blank, и Android по умолчанию глотает
 * такие запросы). Включаем поддержку нескольких окон и подменяем chrome-клиента
 * на HumanitecBridgeWebChromeClient — внутри-продуктовые URL грузятся в текущем
 * WebView, остальные открываются системным браузером. Симметрично iOS-swizzle
 * HumanitecWebViewNewWindowFix.swift.
 */
public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        WebView webView = bridge.getWebView();
        WebSettings settings = webView.getSettings();
        settings.setSupportMultipleWindows(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        webView.setWebChromeClient(new HumanitecBridgeWebChromeClient(bridge));
    }
}
