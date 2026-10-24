"""Точка входа для PyInstaller: ему нужен файл-скрипт, а не `python -m quiz_desktop`."""

import sys

from quiz_desktop.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
