# Добавьте сюда проектные правила ProGuard.
# Набор применяемых конфигурационных файлов можно управлять через
# настройку proguardFiles в build.gradle.
#
# Подробнее см.
#   http://developer.android.com/guide/developing/tools/proguard.html

# Если проект использует WebView с JS, раскомментируйте следующий блок
# и укажите полное имя класса для JavaScript-интерфейса
# class:
#-keepclassmembers class fqcn.of.javascript.interface.for.webview {
#   public *;
#}

# Раскомментируйте, чтобы сохранить информацию о номерах строк для
# отладки stack trace.
#-keepattributes SourceFile,LineNumberTable

# Если сохраняете информацию о номерах строк, раскомментируйте это, чтобы
# скрыть исходное имя файла.
#-renamesourcefileattribute SourceFile
