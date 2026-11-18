"""Стартовый экран: выбор роли — ведущий или игрок."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from quiz_desktop.screens.base import Screen
from quiz_desktop.theme import set_role, set_variant
from quiz_desktop.ui import LogoMark, card


class StartScreen(Screen):
    # Содержимое по центру, не шире этого: на большом мониторе не растягивается.
    MAX_WIDTH = 940

    def __init__(self, window):
        super().__init__(window)

        # Ведущему нужен аккаунт, игрок входит по коду комнаты и нику
        # (docs/quiz-design.md, раздел 2).
        self.host_button = set_variant(QPushButton("Войти или зарегистрироваться"), "primary")
        self.player_button = set_variant(QPushButton("Ввести код комнаты"), "primary")
        for button in (self.host_button, self.player_button):
            button.setMinimumHeight(46)
        self.host_button.clicked.connect(lambda: self.navigate("login"))
        self.player_button.clicked.connect(lambda: self.navigate("join"))

        roles = QHBoxLayout()
        roles.setSpacing(20)
        roles.addWidget(
            self._role_card("🎤", "Я ведущий", "Создавайте викторины, запускайте игры и смотрите результаты.", self.host_button)
        )
        roles.addWidget(
            self._role_card("🎮", "Я игрок", "Введите код комнаты и ник — и отвечайте на вопросы быстрее всех.", self.player_button)
        )

        layout = QVBoxLayout(self.page)
        layout.setSpacing(24)
        layout.addStretch()
        layout.addWidget(self._hero())
        layout.addLayout(roles)
        layout.addStretch()

    def _hero(self) -> QFrame:
        """Цветная шапка с названием и тремя ключевыми возможностями."""
        hero = QFrame()
        hero.setObjectName("hero")

        title = set_role(QLabel("Онлайн-викторина"), "hero-title")
        text = set_role(QLabel("Игры в реальном времени: вопросы на время, очки за скорость и живая таблица лидеров."), "hero-text")
        text.setWordWrap(True)

        pills = QHBoxLayout()
        pills.setSpacing(10)
        for caption in ("⚡ В реальном времени", "🏆 Таблица лидеров", "🎯 Очки за скорость"):
            pills.addWidget(set_role(QLabel(caption), "pill"))
        pills.addStretch()

        texts = QVBoxLayout()
        texts.setSpacing(8)
        texts.addWidget(title)
        texts.addWidget(text)
        texts.addSpacing(6)
        texts.addLayout(pills)

        layout = QHBoxLayout(hero)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(24)
        layout.addWidget(LogoMark(84, inverted=True), alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(texts, stretch=1)
        return hero

    def _role_card(self, icon: str, title: str, text: str, button: QPushButton) -> QWidget:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(10)

        badge = set_role(QLabel(icon), "icon")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = set_role(QLabel(text), "muted")
        description.setWordWrap(True)

        layout.addWidget(badge)
        layout.addWidget(set_role(QLabel(title), "h1"))
        layout.addWidget(description)
        layout.addStretch()
        layout.addSpacing(8)
        layout.addWidget(button)
        return frame
