"""Выгрузить схему API в ``docs/openapi.json`` (контракт для команды фронтенда).

Запуск из корня репозитория::

    python scripts/export_openapi.py [путь]

Приложение собирается на временной пустой папке данных: схема от данных не
зависит, а рабочий ``data/`` не трогается.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.server import create_app  # noqa: E402
from network.jsonio import write_json  # noqa: E402


def export(target: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(data_dir=Path(tmp) / "data", web_dir=Path(tmp) / "no-web")
        schema = app.openapi()
    write_json(target, schema)
    return len(schema["paths"])


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0]) if args else ROOT / "docs" / "openapi.json"
    count = export(target)
    print(f"{target}: {count} путей")


if __name__ == "__main__":
    main()
