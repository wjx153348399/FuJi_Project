from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from station_config_web.config import WebConfig, load_web_config
from station_config_web.repository import StationDirectoryRepository
from zk_impedance_upload.exceptions import ConfigError


_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


def create_app(config_path: str | Path = "web_config.json") -> FastAPI:
    config = load_web_config(config_path)
    app = FastAPI(title="Station Directory Config")
    app.state.web_config = config
    app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse(url="/station-config")

    @app.get("/station-config", response_class=HTMLResponse)
    def station_config_list(
        request: Request,
        status: str = Query("all"),
        keyword: str = Query(""),
    ) -> HTMLResponse:
        rows = []
        error = ""
        try:
            rows = StationDirectoryRepository(config).list_configs(status=status, keyword=keyword)
        except Exception as exc:  # pragma: no cover - display branch
            error = str(exc)
        return _TEMPLATES.TemplateResponse(
            "station_config_list.html",
            {
                "request": request,
                "config": config,
                "rows": rows,
                "status": status,
                "keyword": keyword,
                "error": error,
            },
        )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "database": config.db.database,
            "table": config.db.table,
        }

    return app

def create_missing_config_app(error: ConfigError) -> FastAPI:
    app = FastAPI(title="Station Directory Config")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return f"""
        <!doctype html>
        <html lang="zh-CN">
          <head>
            <meta charset="utf-8">
            <title>工站目录配置</title>
          </head>
          <body>
            <h1>工站目录配置工具</h1>
            <p>Web 配置未就绪：{error}</p>
            <p>请复制 web_config.example.json 为 web_config.json，并填写真实配置。</p>
          </body>
        </html>
        """

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "config_error", "message": str(error)}

    return app


try:
    app = create_app()
except ConfigError as exc:
    app = create_missing_config_app(exc)


if __name__ == "__main__":
    import uvicorn

    web_config = load_web_config()
    uvicorn.run(
        "station_config_web.app:app",
        host=web_config.server.host,
        port=web_config.server.port,
        reload=False,
    )
