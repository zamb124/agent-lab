import UIKit
import Capacitor

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ application: UIApplication, willFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        HumanitecWebViewNewWindowFix.install()
        return true
    }

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        // Точка переопределения для кастомизации после запуска приложения.
        return true
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // Вызывается, когда приложение переходит из активного состояния в неактивное. Это может происходить при временных прерываниях (например, входящий звонок или SMS) или когда пользователь закрывает приложение и начинается переход в фоновое состояние.
        // Используйте этот метод, чтобы приостановить текущие задачи, отключить таймеры и сбросить callback-и рендеринга графики. В играх здесь ставят игру на паузу.
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        // Используйте этот метод, чтобы освободить общие ресурсы, сохранить данные пользователя, сбросить таймеры и сохранить достаточно состояния для восстановления приложения, если оно будет завершено позже.
        // Если приложение поддерживает выполнение в фоне, при выходе пользователя вызывается этот метод вместо applicationWillTerminate:.
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        // Вызывается при переходе из фонового состояния в активное; здесь можно откатить изменения, сделанные при уходе в фон.
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        // Перезапустите задачи, которые были приостановлены или ещё не начаты, пока приложение было неактивно. Если приложение было в фоне, при необходимости обновите интерфейс.
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // Вызывается перед завершением приложения. При необходимости сохраните данные. См. также applicationDidEnterBackground:.
    }

    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        // Вызывается, когда приложение запущено через URL. Дополнительную обработку можно добавить здесь,
        // но если App API должен отслеживать открытия URL, сохраните этот вызов
        return ApplicationDelegateProxy.shared.application(app, open: url, options: options)
    }

    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        // Вызывается, когда приложение запущено через activity, включая Universal Links.
        // Дополнительную обработку можно добавить здесь, но если App API должен поддерживать
        // отслеживание открытий URL приложения, сохраните этот вызов
        return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        NotificationCenter.default.post(name: .capacitorDidRegisterForRemoteNotifications, object: deviceToken)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        NotificationCenter.default.post(name: .capacitorDidFailToRegisterForRemoteNotifications, object: error)
    }

}
