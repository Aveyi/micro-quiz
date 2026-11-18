"""Базовый класс экрана и заглушка для экранов, которые ещё не сделаны."""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from quiz_desktop.theme import set_role, set_variant

if TYPE_CHECKING:
    from quiz_desktop.main_window import MainWindow


class Screen(QWidget):
    """Экран приложения. Все экраны живут в одном окне (QStackedWidget),
    одновременно виден один; переключает их MainWindow.navigate()."""

    # Содержимое не шире этого: на большом мониторе остаётся по центру,
    # а не растягивается на всё окно. Экран может переопределить.
    MAX_WIDTH = 1100

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window  # не self.window: так называется метод QWidget

        # Всё содержимое экрана кладём в self.page: подклассы строят свою вёрстку
        # на нём (QVBoxLayout(self.page)). Страница не шире MAX_WIDTH и стоит по центру,
        # а свободное место по бокам делят две растяжки. Боковые поля не используем:
        # они входили бы в минимальный размер экрана, и окно не могло бы сужаться.
        self.page = QWidget()
        self.page.setMaximumWidth(self.MAX_WIDTH)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)
        outer.addWidget(self.page, 1000)
        outer.addStretch(1)

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
        self.label = set_role(QLabel(), "h2")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        back = set_variant(QPushButton("← Назад"), "primary")
        back.clicked.connect(lambda: self.navigate(back_to))

        layout = QVBoxLayout(self.page)
        layout.addStretch()
        layout.addWidget(self.label)
        layout.addWidget(back, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def entered(self, **params) -> None:
        # Показываем параметры перехода: видно, что экран получил нужные данные.
        details = "\n".join(f"{k}: {v}" for k, v in params.items())
        self.label.setText(f"{self._title}\n\nЭкран в разработке\n\n{details}".rstrip())
