from __future__ import annotations

from pathlib import Path
import subprocess

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from station_config_web.config import WebConfig, load_web_config
from station_config_web.repository import StationDirectoryInput, StationDirectoryRepository
from zk_impedance_upload.exceptions import ConfigError
from zk_impedance_upload.log_store import LogStore
from zk_impedance_upload.share_auth import get_share_root


_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_BASE_DIR / "templates"))


def create_app(config_path: str | Path = "web_config.json") -> FastAPI:
    config = load_web_config(config_path)
    app = FastAPI(title="Station Directory Config")
    app.state.web_config = config
    app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse(url="/dashboard")

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        status, logs, log_error = _read_log_view(config, limit=20)
        return _TEMPLATES.TemplateResponse(
            request,
            "dashboard.html",
            {"config": config, "status": status, "logs": logs, "log_error": log_error},
        )

    @app.get("/logs", response_class=HTMLResponse)
    def logs_page(
        request: Request,
        type: str = Query("all"),
        status: str = Query("all"),
        keyword: str = Query(""),
    ) -> HTMLResponse:
        logs = []
        log_error = ""
        try:
            _ensure_web_log_share_access(config)
            logs = LogStore(config.log.dir).read_recent_logs(log_type=type, status=status, keyword=keyword, limit=200)
        except (ConfigError, OSError) as exc:
            log_error = str(exc)
        return _TEMPLATES.TemplateResponse(
            request,
            "logs.html",
            {"config": config, "logs": logs, "type": type, "status": status, "keyword": keyword, "log_error": log_error},
        )

    @app.get("/api/status")
    def api_status() -> dict[str, object]:
        status, _, log_error = _read_log_view(config, limit=0)
        if log_error:
            status["log_error"] = log_error
        return status

    @app.get("/api/logs")
    def api_logs(
        type: str = Query("all"),
        status: str = Query("all"),
        keyword: str = Query(""),
        limit: int = Query(200),
    ) -> dict[str, object]:
        bounded_limit = min(max(limit, 1), 1000)
        try:
            _ensure_web_log_share_access(config)
            logs = LogStore(config.log.dir).read_recent_logs(
                log_type=type,
                status=status,
                keyword=keyword,
                limit=bounded_limit,
            )
            return {"items": logs, "count": len(logs), "error": ""}
        except (ConfigError, OSError) as exc:
            return {"items": [], "count": 0, "error": str(exc)}

    @app.get("/api/logs/latest")
    def api_latest_logs() -> dict[str, object]:
        try:
            _ensure_web_log_share_access(config)
            logs = LogStore(config.log.dir).read_recent_logs(limit=50)
            return {"items": logs, "count": len(logs), "error": ""}
        except (ConfigError, OSError) as exc:
            return {"items": [], "count": 0, "error": str(exc)}

    @app.get("/station-config", response_class=HTMLResponse)
    def station_config_list(
        request: Request,
        status: str = Query("all"),
        keyword: str = Query(""),
        notice: str = Query(""),
    ) -> HTMLResponse:
        rows = []
        error = ""
        try:
            rows = StationDirectoryRepository(config).list_configs(status=status, keyword=keyword)
        except Exception as exc:  # pragma: no cover - display branch
            error = str(exc)
        return _TEMPLATES.TemplateResponse(
            request,
            "station_config_list.html",
            {
                "config": config,
                "rows": rows,
                "status": status,
                "keyword": keyword,
                "error": error,
                "notice": _notice_message(notice),
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
        flow: str = Form(""),
        station_name: str = Form(""),
        directory_path: str = Form(""),
        enabled: str = Form("0"),
        sort_order: str = Form("0"),
        remark: str = Form(""),
        confirm_missing_path: str = Form("0"),
    ) -> Response:
        form = _form_from_request(
            flow=flow,
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
        return RedirectResponse(url=f"/station-config?notice={_save_notice_key(form, 'created')}", status_code=303)

    @app.get("/station-config/{config_id}/edit", response_class=HTMLResponse)
    def station_config_edit(request: Request, config_id: int) -> HTMLResponse:
        try:
            row = StationDirectoryRepository(config).get_config(config_id)
            if row is None:
                raise ConfigError(f"配置不存在: {config_id}")
            form = {
                "id": row.id,
                "flow": row.flow,
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
        flow: str = Form(""),
        station_name: str = Form(""),
        directory_path: str = Form(""),
        enabled: str = Form("0"),
        sort_order: str = Form("0"),
        remark: str = Form(""),
        confirm_missing_path: str = Form("0"),
    ) -> Response:
        form = _form_from_request(
            flow=flow,
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
        return RedirectResponse(url=f"/station-config?notice={_save_notice_key(form, 'updated')}", status_code=303)

    @app.post("/station-config/{config_id}/enable")
    def station_config_enable(config_id: int) -> RedirectResponse:
        StationDirectoryRepository(config).set_enabled(config_id, True)
        return RedirectResponse(url="/station-config?notice=enabled", status_code=303)

    @app.post("/station-config/{config_id}/disable")
    def station_config_disable(config_id: int) -> RedirectResponse:
        StationDirectoryRepository(config).set_enabled(config_id, False)
        return RedirectResponse(url="/station-config?notice=disabled", status_code=303)

    @app.post("/station-config/check-path", response_class=HTMLResponse)
    def station_config_check_path(
        request: Request,
        directory_path: str = Form(""),
    ) -> HTMLResponse:
        rows = []
        error = ""
        notice = ""
        checked_directory_path = ""
        checked_path_exists = False
        checked_path_is_dir = False
        dialog_type = ""
        dialog_message = ""
        try:
            status_result = StationDirectoryRepository(config).check_and_record_directory(directory_path)
            checked_directory_path = status_result.directory_path
            checked_path_exists = status_result.exists
            checked_path_is_dir = status_result.is_dir
            if status_result.is_dir:
                notice = status_result.message
                dialog_type = "success"
                dialog_message = "目录检测成功：目录存在"
            elif status_result.exists:
                error = status_result.message
                dialog_type = "warn"
                dialog_message = "路径检测异常：该路径存在，但不是文件夹"
            else:
                error = status_result.message
                dialog_type = "error"
                dialog_message = "目录检测失败：目录不存在，请检查目录路径"
        except Exception as exc:
            error = str(exc)
            dialog_type = "error"
            dialog_message = "目录检测失败：无法完成检测，请查看页面错误信息"
        try:
            rows = StationDirectoryRepository(config).list_configs(status="all", keyword=directory_path)
        except Exception:
            rows = []
        return _TEMPLATES.TemplateResponse(
            request,
            "station_config_list.html",
            {
                "config": config,
                "rows": rows,
                "status": "all",
                "keyword": directory_path,
                "error": error,
                "notice": notice,
                "checked_directory_path": checked_directory_path,
                "checked_path_exists": checked_path_exists,
                "checked_path_is_dir": checked_path_is_dir,
                "dialog_type": dialog_type,
                "dialog_message": dialog_message,
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
        "flow": "",
        "station_name": "",
        "directory_path": "",
        "enabled": "1",
        "sort_order": "0",
        "remark": "",
    }


def _empty_status_snapshot() -> dict[str, object]:
    return {
        "latest_upload": None,
        "latest_watch": None,
        "latest_error": None,
        "today_success": 0,
        "today_failed": 0,
        "today_skipped": 0,
    }


def _read_log_view(config: WebConfig, limit: int) -> tuple[dict[str, object], list[dict[str, object]], str]:
    try:
        _ensure_web_log_share_access(config)
        store = LogStore(config.log.dir)
        recent_logs = store.read_recent_logs(limit=max(limit, 1000))
        status = store.build_status_snapshot(recent_logs)
        logs = recent_logs[:limit] if limit > 0 else []
        return status, logs, ""
    except (ConfigError, OSError) as exc:
        return _empty_status_snapshot(), [], str(exc)


def _ensure_web_log_share_access(config: WebConfig) -> None:
    log_share_root = get_share_root(config.log.dir)
    if log_share_root is None:
        return
    if _path_exists(log_share_root):
        return
    if not config.share.username or not config.share.password:
        raise ConfigError(f"日志共享目录不可访问，且 web_config.json 未配置 share.username/share.password: {log_share_root}")

    result = subprocess.run(
        ["net", "use", log_share_root, f"/user:{config.share.username}", config.share.password],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        output = " ".join(part.strip() for part in [result.stdout, result.stderr] if part and part.strip())
        suffix = f": {output}" if output else ""
        raise ConfigError(f"日志共享目录登录失败: {log_share_root}{suffix}")


def _path_exists(path: str) -> bool:
    try:
        return Path(path).exists()
    except OSError:
        return False


def _form_from_request(
    flow: str,
    station_name: str,
    directory_path: str,
    enabled: str,
    sort_order: str,
    remark: str,
    config_id: int | None = None,
) -> dict[str, object]:
    return {
        "id": config_id,
        "flow": flow,
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
    return StationDirectoryInput(
        flow=str(form["flow"]),
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
        request,
        "station_config_form.html",
        {
            "config": config,
            "mode": mode,
            "form": form,
            "error": error,
            "warning": warning,
            "allow_force_save": allow_force_save,
        },
        status_code=status_code,
    )


def _notice_message(notice: str) -> str:
    messages = {
        "created": "新增配置保存成功",
        "created_blank_flow": "新增配置保存成功；flow 待确认，上传时不会传工站代码",
        "created_disabled_blank_flow": "新增配置保存成功；flow 待确认，当前停用",
        "updated": "配置修改保存成功",
        "updated_blank_flow": "配置修改保存成功；flow 待确认，上传时不会传工站代码",
        "updated_disabled_blank_flow": "配置修改保存成功；flow 待确认，当前停用",
        "enabled": "配置启用成功",
        "disabled": "配置停用成功",
    }
    return messages.get(notice, "")


def _save_notice_key(form: dict[str, object], action: str) -> str:
    if str(form["flow"]).strip():
        return action
    if str(form["enabled"]) == "1":
        return f"{action}_blank_flow"
    return f"{action}_disabled_blank_flow"


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
