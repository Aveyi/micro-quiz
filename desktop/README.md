# desktop

Десктопное приложение викторины (Python, PySide6): интерфейс ведущего и игрока. Работает с сервером через nginx по одному адресу, по умолчанию `http://localhost:8000`. Контракты описаны в [`docs/quiz-design.md`](../docs/quiz-design.md).

## Структура

| Файл | Что внутри |
|---|---|
| `quiz_desktop/__main__.py` | точка входа `python -m quiz_desktop`, русские переводы Qt |
| `quiz_desktop/main_window.py` | главное окно: экраны, меню, строка состояния, возврат на старт при `401` |
| `quiz_desktop/screens/base.py` | базовый класс экрана `Screen` и заглушка `PlaceholderScreen` |
| `quiz_desktop/screens/start.py` | стартовый экран: «я ведущий» / «я игрок» |
| `quiz_desktop/settings.py` | адрес сервера, сохраняется между запусками (QSettings) |
| `quiz_desktop/settings_dialog.py` | диалог «Настройки сервера» с проверкой соединения |
| `quiz_desktop/api.py` | асинхронный REST-клиент `ApiClient` |

## Как добавить экран

1. Унаследовать класс от `Screen`. Внутри доступны `self.api` (REST-клиент) и `self.navigate("имя")`.
2. Если экран при каждом показе должен обновлять данные, переопределить `entered()`.
3. Зарегистрировать экран в `MainWindow.__init__`: `self.add_screen("имя", MyScreen(self))`. Сейчас там стоят заглушки `login` и `join`.

Запросы к серверу не блокируют интерфейс, ответ приходит сигналом:

```python
reply = self.api.get("/api/quizzes", auth=True)
reply.succeeded.connect(self.show_quizzes)  # разобранный JSON или None для 204
reply.failed.connect(self.show_error)       # ApiError: status (0 — нет связи) и message
```

С `auth=True` в запрос добавляется `Authorization: Bearer <api.token>`. Если сервер отвечает на такой запрос `401` (токен истёк), приложение само возвращается на стартовый экран.

## Запуск (Windows)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m quiz_desktop
```

Тесты (окна не показываются на экране, сервер не нужен):

```bash
.venv/Scripts/python -m pytest
```
