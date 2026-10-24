"""Стартовый экран: выбор роли — ведущий или игрок."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout

from quiz_desktop.screens.base import Screen


class StartScreen(Screen):
    def __init__(self, window):
        super().__init__(window)

        title = QLabel("Онлайн-викторина")
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Ведущему нужен аккаунт, игрок входит по коду комнаты и нику
        # (docs/quiz-design.md, раздел 2).
        self.host_button = QPushButton("Я ведущий — войти")
        self.player_button = QPushButton("Я игрок — ввести код комнаты")
        for button in (self.host_button, self.player_button):
            button.setMinimumSize(320, 48)
        self.host_button.clicked.connect(lambda: self.navigate("login"))
        self.player_button.clicked.connect(lambda: self.navigate("join"))

        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(title)
        layout.addSpacing(32)
        layout.addWidget(self.host_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.player_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
