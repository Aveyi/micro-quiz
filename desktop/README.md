# desktop

Десктопное приложение викторины (Python, PySide6): интерфейс ведущего и игрока. Работает с сервером через nginx по одному адресу, по умолчанию `http://localhost:8000`. Контракты описаны в [`docs/quiz-design.md`](../docs/quiz-design.md).

## Структура

| Файл | Что внутри |
|---|---|
| `quiz_desktop/__main__.py` | точка входа `python -m quiz_desktop`, русские переводы Qt |
| `quiz_desktop/main_window.py` | главное окно: экраны, меню, строка состояния; `login()` / `logout()`, возврат на вход при `401` |
| `quiz_desktop/screens/base.py` | базовый класс экрана `Screen` и заглушка `PlaceholderScreen` |
| `quiz_desktop/screens/start.py` | стартовый экран: «я ведущий» / «я игрок» |
| `quiz_desktop/screens/login.py` | вход и регистрация ведущего; после регистрации вход выполняется сам |
| `quiz_desktop/screens/quizzes.py` | «Мои викторины»: список, создать, изменить, удалить, провести игру, история |
| `quiz_desktop/screens/editor.py` | редактор викторины: вопросы (добавить, удалить, переставить), 2–4 варианта с отметкой правильного, проверки как в `content`, вопрос о несохранённых изменениях |
| `quiz_desktop/screens/history.py` | история игр: список игр ведущего и результаты выбранной (места, очки, статистика по вопросам с текстами из `content`) |
| `quiz_desktop/settings.py` | адрес сервера и имя последнего ведущего, сохраняются между запусками (QSettings); пароль и токен не сохраняются |
| `quiz_desktop/settings_dialog.py` | диалог «Настройки сервера» с проверкой соединения |
| `quiz_desktop/api.py` | асинхронный REST-клиент `ApiClient` |
| `quiz_desktop/live_client.py` | WebSocket-клиент `LiveClient` к `live` для экранов игры: конверт `{"type", "data"}`, понятные тексты ошибок подключения и кодов закрытия |

## Как добавить экран

1. Унаследовать класс от `Screen`. Внутри доступны `self.api` (REST-клиент) и `self.navigate("имя", **параметры)`.
2. Переопределить `entered(self, **params)`: вызывается при каждом показе экрана, в `params` приходит то, что передали в `navigate()`.
3. Зарегистрировать экран в `MainWindow.__init__`: `self.add_screen("имя", MyScreen(self))`, заменив заглушку с тем же именем.

Экраны и что они получают при переходе:

| Имя | Экран | Параметры | Чей |
|---|---|---|---|
| `start` | выбор роли | — | готов |
| `login` | вход и регистрация ведущего | — | готов |
| `quizzes` | «Мои викторины» | — | готов |
| `editor` | редактор викторины | `quiz_id` — id или `None` для новой | готов |
| `history` | история игр | — | готов |
| `host_game` | игра ведущего: сам создаёт комнату, лобби, вопросы, итоги | `quiz_id` | участник 1 |
| `join` | игра игрока: вход по коду и нику, вопросы, итоги | — | участник 1 |

Запросы к серверу не блокируют интерфейс, ответ приходит сигналом:

```python
reply = self.api.get("/api/quizzes", auth=True)
reply.succeeded.connect(self.show_quizzes)  # разобранный JSON или None для 204
reply.failed.connect(self.show_error)       # ApiError: status (0 — нет связи) и message
```

Запросы к `/live/api/...` отправляются через `self.window_.live_api()`: через nginx это тот же клиент, а без nginx (`QUIZ_LIVE_URL`) — отдельный клиент к `live` с тем же токеном.

С `auth=True` в запрос добавляется `Authorization: Bearer <api.token>`. Токен появляется после входа и хранится только в памяти. Если сервер отвечает на такой запрос `401` (токен истёк), приложение само возвращается на экран входа.

## Запуск (Windows)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m quiz_desktop
```

Без nginx `live` работает на своём порту, а адрес сервера в настройках указывает на `content`. Тогда адрес `live` для экранов игры задаётся переменной окружения (только для разработки):

```bash
QUIZ_LIVE_URL=http://localhost:8080 .venv/Scripts/python -m quiz_desktop
```

Тесты (окна не показываются на экране, сервер не нужен):

```bash
.venv/Scripts/python -m pytest
```
