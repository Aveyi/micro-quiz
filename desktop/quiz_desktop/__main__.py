"""Точка входа: python -m quiz_desktop."""

import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from quiz_desktop.main_window import MainWindow
from quiz_desktop.settings import AppSettings


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Онлайн-викторина")

    # Русские переводы самого Qt: кнопки «Отмена» вместо «Cancel»,
    # сетевые ошибки вроде «Connection refused». Они идут вместе с PySide6.
    translator = QTranslator(app)
    if translator.load(QLocale("ru"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)

    window = MainWindow(AppSettings())
    window.show()
    # exec() крутит цикл событий Qt, пока не закроют последнее окно.
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
