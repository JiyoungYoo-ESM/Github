"""FastAPI OpenAPI 스키마를 JSON 파일로 내보낸다.

프론트엔드 TypeScript 타입 자동 생성(openapi-typescript, IMPROVEMENT_PLAN.md 6번)의
입력이 되는 파일이다. 서버를 띄우지 않고 앱을 import해서 스키마만 뽑으므로 CI에서도
가볍게 돌릴 수 있다.

실행(ESM_SCM8 루트에서):
    py -3.14 -m backend.scripts.export_openapi
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.main import app

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def main() -> None:
    schema = app.openapi()
    serialized = json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True)
    OUTPUT_PATH.write_text(serialized + "\n", encoding="utf-8")
    print(f"OpenAPI schema written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
