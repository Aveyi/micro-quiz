# Сборка QuizDesktop.exe (только на Windows: PyInstaller не собирает под чужую ОС).
#   .venv/Scripts/python -m PyInstaller quiz_desktop.spec --noconfirm
# Результат — dist/QuizDesktop.exe, один файл без консольного окна.

a = Analysis(
    ["run_desktop.py"],
    # Модули, которые приложению не нужны, но которые PyInstaller иначе
    # подтянул бы по цепочке импортов: тесты, Tk, инструменты разработки.
    excludes=["tkinter", "unittest", "pytest", "pytestqt", "pydoc", "PyInstaller"],
)

# Переводы Qt PyInstaller кладёт на всех языках (больше сотни файлов),
# а приложение загружает только русские (quiz_desktop/__main__.py).
a.datas = [d for d in a.datas if "translations" not in d[0] or d[0].endswith("_ru.qm")]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    # binaries и datas внутри EXE — сборка в один файл (onefile): при запуске
    # он распаковывается во временную папку. Это пара секунд на старте,
    # зато сдавать и передавать удобно — один .exe.
    a.binaries,
    a.datas,
    name="QuizDesktop",
    # Без консоли: у приложения есть окно, чёрное окно терминала рядом не нужно.
    console=False,
    # UPX сжимает файлы, но антивирусы чаще ругаются на сжатые .exe.
    upx=False,
)
