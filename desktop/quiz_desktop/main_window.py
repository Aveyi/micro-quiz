"""Главное окно: экраны, меню, строка состояния."""

from PySide6.QtWidgets import QLabel, QMainWindow, QStackedWidget

from quiz_desktop.api import ApiClient
from quiz_desktop.live_client import live_http_base
from quiz_desktop.screens.base import Screen
from quiz_desktop.screens.editor import EditorScreen
from quiz_desktop.screens.history import HistoryScreen
from quiz_desktop.screens.host import HostScreen
from quiz_desktop.screens.login import LoginScreen
from quiz_desktop.screens.player import PlayerScreen
from quiz_desktop.screens.quizzes import QuizzesScreen
from quiz_desktop.screens.start import StartScreen
from quiz_desktop.settings import AppSettings
from quiz_desktop.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self.api = ApiClient(settings.server_url, self)
        self.api.unauthorized.connect(self._on_unauthorized)
        self.username: str | None = None  # вошедший ведущий
        self._live_api: ApiClient | None = None

        self.setWindowTitle("Онлайн-викторина")
        self.resize(960, 640)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)
        self._screens: dict[str, Screen] = {}

        self.add_screen("start", StartScreen(self))
        self.add_screen("login", LoginScreen(self))
        self.add_screen("quizzes", QuizzesScreen(self))
        self.add_screen("editor", EditorScreen(self))
        self.add_screen("history", HistoryScreen(self))
        # Экраны игры (участник 1). host_game открывается из «Моих викторин»
        # с quiz_id и сам создаёт комнату.
        self.add_screen("join", PlayerScreen(self))
        self.add_screen("host_game", HostScreen(self))

        self._build_menu()
        self._user_label = QLabel()
        self._server_label = QLabel()
        self.statusBar().addPermanentWidget(self._user_label)
        self.statusBar().addPermanentWidget(self._server_label)
        self._update_server_label()
        self._update_user()

        self.navigate("start")

    def live_api(self) -> ApiClient:
        """REST-клиент для /live/api/... Через nginx это общий self.api.

        Без nginx (переменная QUIZ_LIVE_URL, только для разработки) live живёт
        по другому адресу — тогда отдельный клиент с тем же токеном.
        """
        base = live_http_base(self.settings.server_url)
        if base == self.api.base_url:
            return self.api
        if self._live_api is None or self._live_api.base_url != base:
            self._live_api = ApiClient(base, self)
            # 401 от live — тоже «сессия истекла».
            self._live_api.unauthorized.connect(self.api.unauthorized)
        self._live_api.token = self.api.token
        return self._live_api

    def add_screen(self, name: str, screen: Screen) -> None:
        self._screens[name] = screen
        self._stack.addWidget(screen)

    def navigate(self, name: str, **params) -> None:
        screen = self._screens[name]
        self._stack.setCurrentWidget(screen)
        screen.entered(**params)

    def current_screen_name(self) -> str:
        current = self._stack.currentWidget()
        return next(name for name, screen in self._screens.items() if screen is current)

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&Приложение")
        menu.addAction("&Настройки сервера…", self.open_settings)
        self._logout_action = menu.addAction("Выйти из &аккаунта", self.logout)
        menu.addSeparator()
        menu.addAction("&Выход", self.close)

    def login(self, token: str, username: str) -> None:
        """Ведущий вошёл: запоминаем токен (только в памяти) и открываем его викторины."""
        self.api.token = token
        self.username = username
        self.settings.last_username = username
        self._update_user()
        self.navigate("quizzes")

    def logout(self) -> None:
        self.api.token = None
        self.username = None
        self._update_user()
        self.navigate("start")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings.server_url, self)
        if dialog.exec():
            self.settings.server_url = dialog.server_url
            self.api.base_url = self.settings.server_url
            # Токен выдан другим сервером, на новом он недействителен.
            self._update_server_label()
            self.logout()

    def _update_server_label(self) -> None:
        self._server_label.setText(f"Сервер: {self.settings.server_url}")

    def _update_user(self) -> None:
        self._user_label.setText(f"Ведущий: {self.username}" if self.username else "")
        self._logout_action.setEnabled(self.username is not None)

    def _on_unauthorized(self) -> None:
        # Токен живёт 12 часов (docs/quiz-design.md, раздел 6), потом сервер отвечает 401.
        self.logout()
        self.navigate("login")
        self.statusBar().showMessage("Сессия истекла, войдите снова", 10_000)
