from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from requests import RequestException


@dataclass(frozen=True)
class UploadResult:
    success: bool
    status_code: int | None
    response: dict[str, Any]
    response_text: str
    error: str
    retry_count: int


def upload_file(
    file_path: str | Path,
    url: str,
    timeout_seconds: int,
    retry_count: int,
    station_code: str = "",
    session: Any | None = None,
) -> UploadResult:
    path = Path(file_path)
    http = session or requests.Session()

    attempts = retry_count + 1
    last_error = ""

    for attempt_index in range(attempts):
        try:
            with path.open("rb") as file:
                response = http.post(
                    url,
                    files={"file": (path.name, file)},
                    data={"station_code": station_code},
                    timeout=timeout_seconds,
                )
        except RequestException as exc:
            last_error = str(exc)
            if attempt_index < retry_count:
                continue
            return UploadResult(
                success=False,
                status_code=None,
                response={},
                response_text="",
                error=last_error,
                retry_count=attempt_index,
            )

        response_text = response.text
        parsed_response = _parse_response_json(response)
        if 200 <= response.status_code < 300:
            if parsed_response.get("success") is False:
                return UploadResult(
                    success=False,
                    status_code=response.status_code,
                    response=parsed_response,
                    response_text=response_text,
                    error=_business_error_message(parsed_response, response_text),
                    retry_count=attempt_index,
                )
            return UploadResult(
                success=True,
                status_code=response.status_code,
                response=parsed_response,
                response_text=response_text,
                error="",
                retry_count=attempt_index,
            )

        last_error = f"HTTP {response.status_code}"
        if attempt_index < retry_count:
            continue
        return UploadResult(
            success=False,
            status_code=response.status_code,
            response=parsed_response,
            response_text=response_text,
            error=last_error,
            retry_count=attempt_index,
        )

    return UploadResult(
        success=False,
        status_code=None,
        response={},
        response_text="",
        error=last_error or "upload failed",
        retry_count=retry_count,
    )


def _parse_response_json(response: Any) -> dict[str, Any]:
    try:
        parsed = response.json()
    except ValueError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {"data": parsed}


def _business_error_message(response: dict[str, Any], response_text: str) -> str:
    message = response.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return response_text or "upload business failure"
