@echo off
setlocal

cd /d "%~dp0"

echo Starting ESM SCM FastAPI backend...
echo Project: %CD%
echo URL: http://127.0.0.1:8002/docs
echo.

rem 업무시간(KST 8-20시) 동안 CMS 데이터를 미리 받아 첫 분석 대기를 캐시 수준으로 줄인다.
rem 발주용 원천 + 분석 탭 기본 구간(최근 1년)을 25분 간격으로 갱신. 상세: OPERATIONS.md 3-2.
set SCM_PRE_ANALYSIS_ENABLED=true

rem PATH의 python은 다른 venv(numpy 없음)일 수 있어 절대 사용하지 않는다.
rem .venv가 있으면 그것을, 없으면 py -3.14를 사용한다.
rem OneDrive 동기화가 대량 파일 변경으로 감지되면 reload 루프가 생길 수 있으므로
rem 기본은 안정 모드로 실행한다. 개발 중 자동 reload가 필요하면
rem SCM_BACKEND_RELOAD=true 환경변수를 지정한다.
set UVICORN_RELOAD_ARGS=
if /I "%SCM_BACKEND_RELOAD%"=="true" set UVICORN_RELOAD_ARGS=--reload --reload-dir backend --reload-dir core

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -m uvicorn backend.main:app %UVICORN_RELOAD_ARGS% --host 0.0.0.0 --port 8002
) else (
    py -3.14 -m uvicorn backend.main:app %UVICORN_RELOAD_ARGS% --host 0.0.0.0 --port 8002
)

echo.
echo Backend server stopped.
pause
