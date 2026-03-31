import Capacitor
import Foundation
import ObjectiveC
import WebKit

private typealias HumanitecCreateWebViewIMP = @convention(c) (
    AnyObject,
    Selector,
    WKWebView,
    WKWebViewConfiguration,
    WKNavigationAction,
    WKWindowFeatures
) -> WKWebView?

/**
 Capacitor по умолчанию в `WebViewDelegationHandler.webView(_:createWebViewWith:...)`
 вызывает `UIApplication.shared.open` и возвращает `nil`, поэтому сценарий «нового окна»
 уводит в Safari.

 `CAPBridgeViewController.loadView` помечен `final`, подменить `WebViewDelegationHandler`
 в подклассе VC нельзя. Перехват через swizzle; правила совпадают с `decidePolicyFor`
 (`shouldAllowNavigation` и префиксы server/local URL).
 */
enum HumanitecWebViewNewWindowFix {
    private static var didInstall = false
    private static let lock = NSLock()
    private static var originalCreateWebView: HumanitecCreateWebViewIMP?

    private static let createWebViewSelector = #selector(WKUIDelegate.webView(_:createWebViewWith:for:windowFeatures:))

    static func install() {
        lock.lock()
        defer { lock.unlock() }
        guard !didInstall else { return }
        didInstall = true

        let handlerClass = WebViewDelegationHandler.self
        let swizzledSelector = #selector(WebViewDelegationHandler.humanitec_cap_webView(_:createWebViewWith:for:windowFeatures:))

        guard let originalMethod = class_getInstanceMethod(handlerClass, createWebViewSelector) else {
            fatalError("HumanitecWebViewNewWindowFix: WebViewDelegationHandler не содержит createWebViewWith (смена версии Capacitor?).")
        }
        guard let swizzledMethod = class_getInstanceMethod(handlerClass, swizzledSelector) else {
            fatalError("HumanitecWebViewNewWindowFix: не найден humanitec_cap_webView — проверьте @objc-метод в расширении.")
        }

        let originalIMP = method_getImplementation(originalMethod)
        originalCreateWebView = unsafeBitCast(originalIMP, to: HumanitecCreateWebViewIMP.self)
        method_exchangeImplementations(originalMethod, swizzledMethod)
    }

    fileprivate static func callOriginalCapacitorCreateWebView(
        selfPtr: WebViewDelegationHandler,
        webView: WKWebView,
        configuration: WKWebViewConfiguration,
        navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        guard let imp = originalCreateWebView else {
            fatalError("HumanitecWebViewNewWindowFix: original IMP не сохранён")
        }
        return imp(selfPtr, createWebViewSelector, webView, configuration, navigationAction, windowFeatures)
    }
}

extension WebViewDelegationHandler {
    @objc dynamic func humanitec_cap_webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if let url = navigationAction.request.url {
            if let host = url.host, let bridge = bridge {
                if bridge.config.shouldAllowNavigation(to: host) {
                    webView.load(navigationAction.request)
                    return nil
                }
                let absolute = url.absoluteString
                let serverPrefix = bridge.config.serverURL.absoluteString
                let localPrefix = bridge.config.localURL.absoluteString
                if absolute.starts(with: serverPrefix) || absolute.starts(with: localPrefix) {
                    webView.load(navigationAction.request)
                    return nil
                }
            }
        }
        return HumanitecWebViewNewWindowFix.callOriginalCapacitorCreateWebView(
            selfPtr: self,
            webView: webView,
            configuration: configuration,
            navigationAction: navigationAction,
            windowFeatures: windowFeatures
        )
    }
}
