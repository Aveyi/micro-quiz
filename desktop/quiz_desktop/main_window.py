"""Главное окно: экраны, меню, строка состояния."""

from PySide6.QtWidgets import QLabel, QMainWindow, QStackedWidget

from quiz_desktop.api import ApiClient
from quiz_desktop.screens.base import PlaceholderScreen, Screen
from quiz_desktop.screens.start import StartScreen
from quiz_desktop.settings import AppSettings
from quiz_desktop.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self.api = ApiClient(settings.server_url, self)
        self.api.unauthorized.connect(self._on_unauthorized)

        self.setWindowTitle("Онлайн-викторина")
        self.resize(960, 640)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)
        self._screens: dict[str, Screen] = {}

        self.add_screen("start", StartScreen(self))
        # Заглушки, пока экраны не готовы. Разделение — docs/quiz-design.md, раздел 10:
        # вход, викторины, редактор, история — участник 2; экраны игры — участник 1.
        self.add_screen("login", PlaceholderScreen(self, "Вход ведущего"))
        self.add_screen("join", PlaceholderScreen(self, "Вход игрока в комнату"))

        self._build_menu()
        self._server_label = QLabel()
        self.statusBar().addPermanentWidget(self._server_label)
        self._update_server_label()

        self.navigate("start")

    def add_screen(self, name: str, screen: Screen) -> None:
        self._screens[name] = screen
        self._stack.addWidget(screen)

    def navigate(self, name: str) -> None:
        screen = self._screens[name]
        self._stack.setCurrentWidget(screen)
        screen.entered()

    def current_screen_name(self) -> str:
        current = self._stack.currentWidget()
        return next(name for name, screen in self._screens.items() if screen is current)

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&Приложение")
        menu.addAction("&Настройки сервера…", self.open_settings)
        menu.addSeparator()
        menu.addAction("&Выход", self.close)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings.server_url, self)
        if dialog.exec():
            self.settings.server_url = dialog.server_url
            self.api.base_url = self.settings.server_url
            # Токен выдан другим сервером, на новом он недействителен.
            self.api.token = None
            self._update_server_label()
            self.navigate("start")

    def _update_server_label(self) -> None:
        self._server_label.setText(f"Сервер: {self.settings.server_url}")

    def _on_unauthorized(self) -> None:
        self.api.token = None
        self.navigate("start")
        self.statusBar().showMessage("Сессия истекла, войдите снова", 10_000)
