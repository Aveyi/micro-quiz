"""Стартовый экран: выбор роли — ведущий или игрок."""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

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

        brand = QHBoxLayout()
        brand.setSpacing(12)
        brand.addWidget(LogoMark(34))
        brand.addWidget(set_role(QLabel("Онлайн-викторина"), "brand"))
        brand.addStretch()

        headline = set_role(QLabel("Викторины в реальном времени"), "display")
        headline.setWordWrap(True)
        lead = set_role(QLabel("Вопросы на время, очки за скорость и живая таблица лидеров."), "lead")
        lead.setWordWrap(True)

        roles = QHBoxLayout()
        roles.setSpacing(20)
        roles.addWidget(
            self._role_card("01", "Я ведущий", "Создавайте викторины, запускайте игры и смотрите результаты.", self.host_button)
        )
        roles.addWidget(
            self._role_card("02", "Я игрок", "Введите код комнаты и ник, а дальше всё решает скорость.", self.player_button)
        )

        layout = QVBoxLayout(self.page)
        layout.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(40)
        layout.addWidget(headline)
        layout.addSpacing(6)
        layout.addWidget(lead)
        layout.addSpacing(32)
        layout.addLayout(roles)
        layout.addStretch()

    def _role_card(self, index: str, title: str, text: str, button: QPushButton) -> QWidget:
        frame = card()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(8)

        description = set_role(QLabel(text), "muted")
        description.setWordWrap(True)

        layout.addWidget(set_role(QLabel(index), "index"))
        layout.addWidget(set_role(QLabel(title), "h1"))
        layout.addWidget(description)
        layout.addStretch()
        layout.addSpacing(14)
        layout.addWidget(button)
        return frame
