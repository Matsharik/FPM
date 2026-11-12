"""Запуск бэкенда одной командой: ``python run.py``.

Флаги: ``--host``, ``--port``, ``--data`` (папка данных, по умолчанию ``data/``),
``--reset`` (пересоздать демо-данные из ``config/``), ``--clock`` (время стенда
при сбросе, ISO 8601 с поясом). Если данных ещё нет, сид запускается сам.
Документация API после старта: http://127.0.0.1:8000/docs
"""

# Файл намеренно написан без современного синтаксиса: на старом Python он должен
# дойти до проверки версии и объяснить, что не так, а не упасть на разборе.

import argparse
import os
import sys

MIN_PYTHON = (3, 11)
MAX_PYTHON = (3, 13)  # новее не проверяли: под них может не быть готовых колёс зависимостей


def check_python():
    current = tuple(sys.version_info[:2])
    if current < MIN_PYTHON or current > MAX_PYTHON:
        sys.stderr.write(
            "Поддерживается Python %d.%d–%d.%d, а запущен %d.%d.\n"
            "На других версиях установка зависимостей (pip) может упасть при сборке пакетов.\n"
            "Установите Python 3.13 и создайте окружение заново:\n"
            "  py -3.13 -m venv .venv          (Windows)\n"
            "  python3.13 -m venv .venv        (Linux, macOS)\n"
            "Подробнее — README, раздел «Требования».\n"
            % (MIN_PYTHON + MAX_PYTHON + current)
        )
        raise SystemExit(1)


def setup_utf8():
    """UTF-8 для своего вывода и для дочерних процессов.

    Без этого на Windows при перенаправлении вывода в файл или pipe кириллица
    падает с UnicodeEncodeError (кодировка cp1252).
    """
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Бэкенд трекера «Фотопринт»")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3008) 
    parser.add_argument("--data", default=None, help="папка данных (по умолчанию data/ или QNET_ROOT)")
    parser.add_argument("--reset", action="store_true", help="пересоздать демо-данные из config/")
    parser.add_argument("--check", action="store_true", help="только проверить версию Python и выйти")
    parser.add_argument(
        "--clock", default=None, help="время стенда при сбросе, например 2026-11-23T09:00:00+03:00"
    )
    return parser.parse_args(argv)


def prepare_data(ws, reset=False, clock=None):
    """Собрать демо-данные, если их нет или если попросили сброс. Вернуть True, если собирали."""
    if not (reset or clock or not ws.has_data()):
        return False
    result = ws.demo.reset("system", clock)
    print(
        "Демо-данные собраны: узлов %d, связей %d, заказов %d, событий %d, карточки: %s"
        % (result["nodes"], result["links"], result["orders"], result["events"],
           ", ".join(result["deviations"]) or "нет"),
        flush=True,
    )
    return True


def print_logins(ws):
    """Демо-логины: их передают в заголовке X-User (паролей нет, в продакшне — SSO/AD)."""
    print("Демо-логины (заголовок X-User):", flush=True)
    for user in ws.access.users():
        print("  %-12s %-8s %s" % (user.login, user.role, user.name), flush=True)


def main(argv=None):
    check_python()
    setup_utf8()
    if "--check" in (sys.argv[1:] if argv is None else argv):
        # Проверка версии до установки зависимостей: python run.py --check
        print("Python %d.%d подходит. Дальше: python -m pip install -r requirements.txt" % tuple(sys.version_info[:2]))
        return
    args = parse_args(argv)

    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        import uvicorn

        from api.server import create_app
    except ImportError as exc:
        sys.stderr.write(
            "Не найдены зависимости (%s).\nУстановите их: python -m pip install -r requirements.txt\n"
            % exc
        )
        raise SystemExit(1)

    app = create_app(data_dir=args.data)
    prepare_data(app.state.ws, args.reset, args.clock)
    print_logins(app.state.ws)
    if os.path.isfile(os.path.join(root, "web", "index.html")):
        print("Интерфейс: http://%s:%d/" % (args.host, args.port), flush=True)
    print("API:    http://%s:%d/docs" % (args.host, args.port), flush=True)
    print("Время стенда: %s" % app.state.ws.clock.iso(), flush=True)
    print("Данные: %s" % app.state.ws.data_dir.resolve(), flush=True)
    # Р10: один процесс — кэш рядов и счётчики id живут в памяти.
    uvicorn.run(app, host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
