from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from station_config_web.config import WebConfig, load_web_config
from zk_impedance_upload.exceptions import ConfigError


def create_app(config_path: str | Path = "web_config.json") -> FastAPI:
    config = load_web_config(config_path)
    app = FastAPI(title="Station Directory Config")
    app.state.web_config = config

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _render_index(config)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "database": config.db.database,
            "table": config.db.table,
        }

    return app


def _render_index(config: WebConfig) -> str:
    return f"""
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8">
        <title>工站目录配置</title>
      </head>
      <body>
        <h1>工站目录配置工具</h1>
        <p>数据库：{config.db.database}</p>
        <p>配置表：{config.db.table}</p>
        <p>共享盘根目录：{config.share.root}</p>
        <p>阶段 1：Web 工具骨架已启动。</p>
      </body>
    </html>
    """


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
