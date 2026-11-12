"""FastAPI-приложение трекера «Фотопринт».

Приложение собирается фабрикой ``create_app``: на импорте модуля ничего не
создаётся и диск не читается. Запуск::

    python run.py                # основной способ
    uvicorn api.server:create_app --factory   # корень данных — QNET_ROOT

Маршруты сгруппированы по режимам работы (раздел 8 промпта) в ``api/routers``.
Документация: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.workspace import PROJECT_ROOT, Workspace

from .deps import get_user
from .errors import ERROR_RESPONSES, install_error_handlers
from .routers import (
    analysis,
    audit,
    auth,
    builder,
    demo,
    deviations,
    flow,
    glossary,
    graph,
    kpi,
    nodes,
    overview,
    qc,
)

# Типы статики заданы явно: на Windows mimetypes берёт их из реестра, и ``.js``
# может прийти как ``text/plain`` — тогда браузер не запустит модуль фронтенда.
for _ext, _type in {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".json": "application/json",
}.items():
    mimetypes.add_type(_type, _ext)

# CORS: разрешаем localhost, ваш домен slovesny.ru и любые поддомены github.io (для GitHub Pages)
CORS_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://(www\.)?slovesny\.ru$|^https://[a-zA-Z0-9-]+\.github\.io$"

ROUTERS = (
    overview.router,
    graph.router,
    nodes.router,
    kpi.router,
    analysis.router,
    deviations.router,
    demo.router,
    glossary.router,
    builder.router,
    qc.router,
    audit.router,
    flow.router,
)


def create_app(
    config_dir: str | os.PathLike[str] | None = None,
    data_dir: str | os.PathLike[str] | None = None,
    web_dir: str | os.PathLike[str] | None = None,
) -> FastAPI:
    """Собрать приложение. Пути по умолчанию: ``config/``, ``data/`` (или QNET_ROOT), ``web/``."""
    ws = Workspace(config_dir, data_dir)
    app = FastAPI(
        title="Фотопринт — трекер KPI и решений",
        version="3.0",
        description=(
            "Единый слой событий и статусов: сигнал → контекст → причина → действие → "
            "повторная проверка. Пользователь задаётся заголовком `X-User`."
        ),
        responses=ERROR_RESPONSES,
        # root_path сюда НЕ добавляем (он теперь в run.py)
    )
    app.state.ws = ws
    
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=CORS_ORIGIN_RE,
        allow_credentials=True, # ДОБАВЛЕНО: разрешаем куки и заголовки авторизации
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

    @app.get("/health", tags=["Сервис"], summary="Проверка живости")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Р9: без X-User — 401 везде, кроме /health и /api/auth/users (роутер входа сам
    # требует пользователя на /api/me).
    app.include_router(auth.router)
    for router in ROUTERS:
        app.include_router(router, dependencies=[Depends(get_user)])

    # Статический фронтенд (если папка есть) монтируется последним: /api и /docs важнее.
    web = Path(web_dir) if web_dir is not None else PROJECT_ROOT / "web"
    if web.is_dir():
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app