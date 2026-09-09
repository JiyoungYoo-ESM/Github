"""PPTX → PDF 변환(soffice/PowerPoint).

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계). LibreOffice(soffice) 또는
PowerPoint COM으로 pptx를 pdf로 변환한다. 프로젝트 의존은 PDF 변환 직렬화 락뿐이다."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from fastapi import HTTPException

from backend.services.reports.models import PDF_CONVERSION_LOCK

def convert_pptx_to_pdf(pptx_path: Path, output_dir: Path) -> Path:
    # LibreOffice and PowerPoint COM are both fragile under parallel exports.
    # Serialize conversion so multiple users do not make the converter race itself.
    with PDF_CONVERSION_LOCK:
        return convert_pptx_to_pdf_unlocked(pptx_path, output_dir)

def convert_pptx_to_pdf_unlocked(pptx_path: Path, output_dir: Path) -> Path:
    soffice = find_soffice_executable()
    if not soffice:
        return convert_pptx_to_pdf_with_powerpoint(pptx_path, output_dir)

    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        profile_dir = temp_dir / "lo-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        command = [
            soffice,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--nolockcheck",
            "--norestore",
            f"-env:UserInstallation={profile_dir.as_uri()}",
            "--convert-to",
            "pdf:impress_pdf_Export",
            "--outdir",
            str(temp_dir),
            str(pptx_path),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
        if completed.returncode != 0:
            raise HTTPException(status_code=500, detail=f"PDF 변환에 실패했습니다: {completed.stderr.strip()}")

        converted = temp_dir / f"{pptx_path.stem}.pdf"
        if not converted.is_file():
            raise HTTPException(status_code=500, detail="PDF 변환 결과 파일을 찾을 수 없습니다.")

        pdf_path = output_dir / converted.name
        shutil.move(str(converted), pdf_path)
        return pdf_path


def find_soffice_executable() -> str | None:
    for env_name in ("SOFFICE_PATH", "LIBREOFFICE_PATH"):
        value = os.environ.get(env_name)
        if value and Path(value).is_file():
            return str(Path(value))

    discovered = shutil.which("soffice") or shutil.which("libreoffice")
    if discovered:
        return discovered

    candidate_paths = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "LibreOffice" / "program" / "soffice.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "LibreOffice" / "program" / "soffice.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "LibreOffice" / "program" / "soffice.exe",
        Path("/usr/bin/soffice"),
        Path("/usr/local/bin/soffice"),
        Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
    ]
    for candidate in candidate_paths:
        if candidate.is_file():
            return str(candidate)
    return None


def convert_pptx_to_pdf_with_powerpoint(pptx_path: Path, output_dir: Path) -> Path:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise_pdf_converter_error()

    pdf_path = output_dir / f"{pptx_path.stem}.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        temp_pptx_path = temp_dir / "source.pptx"
        temp_pdf_path = temp_dir / "source.pdf"
        shutil.copy2(pptx_path, temp_pptx_path)
        run_powerpoint_pdf_export(powershell, temp_pptx_path, temp_pdf_path)
        if not temp_pdf_path.is_file():
            raise_pdf_converter_error("PowerPoint PDF output file was not created.")
        shutil.move(str(temp_pdf_path), pdf_path)
    return pdf_path


def run_powerpoint_pdf_export(powershell: str, pptx_path: Path, pdf_path: Path) -> None:
    """PowerPoint COM으로 PDF를 저장한다.

    다른 프로세스가 PowerPoint를 사용 중일 때 발생할 수 있는 일시 오류는
    제한적으로 대기 후 재시도해 간헐적 실패를 줄인다.
    """
    script = f"""
$ErrorActionPreference = "Stop"
$pptxPath = {json.dumps(str(pptx_path))}
$pdfPath = {json.dumps(str(pdf_path))}
$powerPoint = $null
$presentation = $null
try {{
  $powerPoint = New-Object -ComObject PowerPoint.Application
  $presentation = $powerPoint.Presentations.Open($pptxPath, $true, $true, $false)
  $presentation.SaveAs($pdfPath, 32)
}} finally {{
  if ($presentation -ne $null) {{ $presentation.Close() | Out-Null }}
  if ($powerPoint -ne $null) {{ $powerPoint.Quit() | Out-Null }}
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}}
"""
    attempts = 3
    last_error = ""
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode == 0:
            return
        last_error = completed.stderr.strip()
        print(f"[perf][report_pdf] powerpoint_com_retry attempt={attempt}/{attempts} error={last_error[:160]}", flush=True)
        if attempt < attempts:
            time.sleep(2 * attempt)
    raise_pdf_converter_error(last_error)


def raise_pdf_converter_error(detail: str | None = None) -> None:
    message = "PDF 변환에 실패했습니다. PPT 디자인 기반 PDF 변환에는 LibreOffice(soffice, 권장) 또는 Microsoft PowerPoint가 필요합니다."
    if detail:
        message = f"{message} ({detail})"
    raise HTTPException(status_code=501, detail=message)




__all__ = [
    "convert_pptx_to_pdf",
    "convert_pptx_to_pdf_unlocked",
    "find_soffice_executable",
    "convert_pptx_to_pdf_with_powerpoint",
    "run_powerpoint_pdf_export",
    "raise_pdf_converter_error",
]
