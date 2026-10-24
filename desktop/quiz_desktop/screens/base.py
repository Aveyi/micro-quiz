"""Базовый класс экрана и заглушка для экранов, которые ещё не сделаны."""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from quiz_desktop.main_window import MainWindow


class Screen(QWidget):
    """Экран приложения. Все экраны живут в одном окне (QStackedWidget),
    одновременно виден один; переключает их MainWindow.navigate()."""

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window  # не self.window: так называется метод QWidget

    @property
    def api(self):
        return self.window_.api

    def navigate(self, name: str, **params) -> None:
        self.window_.navigate(name, **params)

    def entered(self, **params) -> None:
        """Вызывается каждый раз, когда экран показывают. Здесь экран
        обновляет данные, например перезагружает список викторин.
        params — то, что передали в navigate(), например quiz_id для редактора."""


class PlaceholderScreen(Screen):
    """Заглушка, пока настоящий экран не готов: видно, что навигация работает."""

    def __init__(self, window: "MainWindow", title: str, back_to: str = "start"):
        super().__init__(window)
        self._title = title
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        back = QPushButton("← Назад")
        back.clicked.connect(lambda: self.navigate(back_to))

        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self.label)
        layout.addWidget(back, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def entered(self, **params) -> None:
        # Показываем параметры перехода: видно, что экран получил нужные данные.
        details = "\n".join(f"{k}: {v}" for k, v in params.items())
        self.label.setText(f"{self._title}\n\nЭкран в разработке\n\n{details}".rstrip())
