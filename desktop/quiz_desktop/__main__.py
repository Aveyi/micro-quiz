"""Точка входа: python -m quiz_desktop."""

import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from quiz_desktop.main_window import MainWindow
from quiz_desktop.settings import AppSettings
from quiz_desktop.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Онлайн-викторина")

    # Русские переводы самого Qt: кнопки «Отмена» вместо «Cancel»,
    # сетевые ошибки вроде «Connection refused». Они идут вместе с PySide6.
    translator = QTranslator(app)
    if translator.load(QLocale("ru"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)

    settings = AppSettings()
    # Тему применяем до создания окна: размеры виджетов считаются уже со стилями
    # (отступы полей, высота кнопок), иначе строки форм получаются сплюснутыми.
    apply_theme(app, settings.theme)
    window = MainWindow(settings)
    # «Как в системе»: при смене темы в Windows или macOS приложение подстраивается само.
    app.styleHints().colorSchemeChanged.connect(lambda _: settings.theme == "auto" and window.apply_theme())
    window.show()
    # exec() крутит цикл событий Qt, пока не закроют последнее окно.
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
