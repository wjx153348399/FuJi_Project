from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from station_config_web.config import WebConfig, load_web_config
from station_config_web.repository import StationDirectoryInput, StationDirectoryRepository
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

    @app.get("/station-config/new", response_class=HTMLResponse)
    def station_config_new(request: Request) -> HTMLResponse:
        return _render_form(
            request=request,
            config=config,
            mode="new",
            form=_empty_form(),
        )

    @app.post("/station-config/new", response_class=HTMLResponse)
    def station_config_create(
        request: Request,
        station_code: str = Form(""),
        station_name: str = Form(""),
        directory_path: str = Form(""),
        enabled: str = Form("0"),
        sort_order: str = Form("0"),
        remark: str = Form(""),
        confirm_missing_path: str = Form("0"),
    ) -> Response:
        form = _form_from_request(
            station_code=station_code,
            station_name=station_name,
            directory_path=directory_path,
            enabled=enabled,
            sort_order=sort_order,
            remark=remark,
        )
        try:
            directory_warning = _directory_save_warning(config, form)
            if directory_warning and confirm_missing_path != "1":
                return _render_form(
                    request,
                    config,
                    "new",
                    form,
                    warning=directory_warning,
                    allow_force_save=True,
                    status_code=400,
                )
            StationDirectoryRepository(config).create_config(_input_from_form(form))
        except Exception as exc:
            return _render_form(request, config, "new", form, error=str(exc), status_code=400)
        return RedirectResponse(url="/station-config", status_code=303)

    @app.get("/station-config/{config_id}/edit", response_class=HTMLResponse)
    def station_config_edit(request: Request, config_id: int) -> HTMLResponse:
        try:
            row = StationDirectoryRepository(config).get_config(config_id)
            if row is None:
                raise ConfigError(f"配置不存在: {config_id}")
            form = {
                "id": row.id,
                "station_code": row.station_code,
                "station_name": row.station_name or "",
                "directory_path": row.directory_path,
                "enabled": "1" if row.enabled else "0",
                "sort_order": str(row.sort_order),
                "remark": row.remark or "",
            }
            return _render_form(request, config, "edit", form)
        except Exception as exc:
            return _render_form(request, config, "edit", _empty_form(config_id), error=str(exc), status_code=404)

    @app.post("/station-config/{config_id}/edit", response_class=HTMLResponse)
    def station_config_update(
        request: Request,
        config_id: int,
        station_code: str = Form(""),
        station_name: str = Form(""),
        directory_path: str = Form(""),
        enabled: str = Form("0"),
        sort_order: str = Form("0"),
        remark: str = Form(""),
        confirm_missing_path: str = Form("0"),
    ) -> Response:
        form = _form_from_request(
            station_code=station_code,
            station_name=station_name,
            directory_path=directory_path,
            enabled=enabled,
            sort_order=sort_order,
            remark=remark,
            config_id=config_id,
        )
        try:
            directory_warning = _directory_save_warning(config, form)
            if directory_warning and confirm_missing_path != "1":
                return _render_form(
                    request,
                    config,
                    "edit",
                    form,
                    warning=directory_warning,
                    allow_force_save=True,
                    status_code=400,
                )
            StationDirectoryRepository(config).update_config(config_id, _input_from_form(form))
        except Exception as exc:
            return _render_form(request, config, "edit", form, error=str(exc), status_code=400)
        return RedirectResponse(url="/station-config", status_code=303)

    @app.post("/station-config/{config_id}/enable")
    def station_config_enable(config_id: int) -> RedirectResponse:
        StationDirectoryRepository(config).set_enabled(config_id, True)
        return RedirectResponse(url="/station-config", status_code=303)

    @app.post("/station-config/{config_id}/disable")
    def station_config_disable(config_id: int) -> RedirectResponse:
        StationDirectoryRepository(config).set_enabled(config_id, False)
        return RedirectResponse(url="/station-config", status_code=303)

    @app.post("/station-config/check-path", response_class=HTMLResponse)
    def station_config_check_path(
        request: Request,
        directory_path: str = Form(""),
    ) -> HTMLResponse:
        rows = []
        error = ""
        notice = ""
        try:
            status_result = StationDirectoryRepository(config).check_directory(directory_path)
            if status_result.is_dir:
                notice = f"目录存在: {status_result.full_path}"
            elif status_result.exists:
                error = f"路径存在但不是目录: {status_result.full_path}"
            else:
                error = f"目录不存在: {status_result.full_path}"
        except Exception as exc:
            error = str(exc)
        try:
            rows = StationDirectoryRepository(config).list_configs(status="all", keyword=directory_path)
        except Exception:
            rows = []
        return _TEMPLATES.TemplateResponse(
            "station_config_list.html",
            {
                "request": request,
                "config": config,
                "rows": rows,
                "status": "all",
                "keyword": directory_path,
                "error": error,
                "notice": notice,
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


def _empty_form(config_id: int | None = None) -> dict[str, object]:
    return {
        "id": config_id,
        "station_code": "",
        "station_name": "",
        "directory_path": "",
        "enabled": "1",
        "sort_order": "0",
        "remark": "",
    }


def _form_from_request(
    station_code: str,
    station_name: str,
    directory_path: str,
    enabled: str,
    sort_order: str,
    remark: str,
    config_id: int | None = None,
) -> dict[str, object]:
    return {
        "id": config_id,
        "station_code": station_code,
        "station_name": station_name,
        "directory_path": directory_path,
        "enabled": "1" if enabled in {"1", "true", "on", "yes"} else "0",
        "sort_order": sort_order,
        "remark": remark,
    }


def _input_from_form(form: dict[str, object]) -> StationDirectoryInput:
    try:
        sort_order = int(str(form["sort_order"]).strip() or "0")
    except ValueError as exc:
        raise ConfigError("排序必须是整数") from exc
    if not str(form["station_code"]).strip():
        raise ConfigError("上传工站代码不能为空")
    return StationDirectoryInput(
        station_code=str(form["station_code"]),
        station_name=str(form["station_name"]),
        directory_path=str(form["directory_path"]),
        enabled=str(form["enabled"]) == "1",
        sort_order=sort_order,
        remark=str(form["remark"]),
    )


def _render_form(
    request: Request,
    config: WebConfig,
    mode: str,
    form: dict[str, object],
    error: str = "",
    warning: str = "",
    allow_force_save: bool = False,
    status_code: int = 200,
) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(
        "station_config_form.html",
        {
            "request": request,
            "config": config,
            "mode": mode,
            "form": form,
            "error": error,
            "warning": warning,
            "allow_force_save": allow_force_save,
        },
        status_code=status_code,
    )


def _directory_save_warning(config: WebConfig, form: dict[str, object]) -> str:
    status_result = StationDirectoryRepository(config).check_directory(str(form["directory_path"]))
    if status_result.is_dir:
        return ""
    if status_result.exists:
        return f"路径存在但不是目录，保存后自动上传无法扫描该配置: {status_result.full_path}"
    return f"目录不存在，保存后自动上传会跳过该配置: {status_result.full_path}"

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
