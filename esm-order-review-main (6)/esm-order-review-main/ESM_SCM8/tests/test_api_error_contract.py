from __future__ import annotations

import asyncio
import json

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import Request

from backend.main import custom_openapi
from backend.services.api_errors import (
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)


def make_request(request_id: str = "request-test-1") -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "headers": [],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1234),
            "scheme": "http",
        }
    )
    request.state.request_id = request_id
    return request


def response_body(response) -> dict[str, object]:
    return json.loads(response.body.decode("utf-8"))


def test_http_errors_use_stable_envelope_and_keep_legacy_detail():
    response = asyncio.run(http_exception_handler(make_request(), HTTPException(404, "분석 결과가 없습니다.")))
    body = response_body(response)

    assert response.status_code == 404
    assert response.headers["x-request-id"] == "request-test-1"
    assert body["detail"] == "분석 결과가 없습니다."
    assert body["error"] == {
        "code": "not_found",
        "message": "분석 결과가 없습니다.",
        "status": 404,
        "request_id": "request-test-1",
        "details": None,
    }


def test_string_error_codes_are_preserved_for_auth_compatibility():
    response = asyncio.run(http_exception_handler(make_request(), HTTPException(401, "invalid_credentials")))

    assert response_body(response)["error"]["code"] == "invalid_credentials"


def test_validation_errors_put_field_failures_in_details():
    error = RequestValidationError(
        [{"type": "missing", "loc": ("body", "name"), "msg": "Field required", "input": {}}]
    )
    response = asyncio.run(validation_exception_handler(make_request(), error))
    body = response_body(response)

    assert response.status_code == 422
    assert body["detail"] == "요청 값이 올바르지 않습니다."
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["loc"] == ["body", "name"]


def test_unexpected_errors_do_not_expose_internal_exception_text():
    response = asyncio.run(unexpected_exception_handler(make_request(), RuntimeError("database password leaked")))
    serialized = response.body.decode("utf-8")

    assert response.status_code == 500
    assert "database password leaked" not in serialized
    assert response_body(response)["error"]["code"] == "internal_server_error"


def test_openapi_documents_standard_error_response_for_every_operation():
    schema = custom_openapi()
    assert "ApiErrorResponse" in schema["components"]["schemas"]
    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            reference = operation["responses"]["default"]["content"]["application/json"]["schema"]
            assert reference == {"$ref": "#/components/schemas/ApiErrorResponse"}
