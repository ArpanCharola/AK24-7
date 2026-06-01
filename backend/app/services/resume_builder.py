"""In-process integration with skilluence/resume-formatter.

The resume-formatter repo lives outside this codebase. We import its
`structure_resume`, `format_compact` functions directly via sys.path
so the formatter remains its own standalone project (with its own UI)
while AI Apply consumes its core pipeline.

Pipeline:
    tailored_text → structure_resume (gpt-4o-mini → JSON)
                  → format_compact (JSON → DOCX)
                  → Word COM ExportAsFixedFormat (Windows) / soffice (POSIX) (DOCX → PDF)
                  → bytes

Returns None on any failure so callers can fall back to plaintext.
"""
import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _add_formatter_to_path() -> None:
    """Insert the resume-formatter backend dir into sys.path (idempotent)."""
    if not settings.RESUME_FORMATTER_PATH:
        raise RuntimeError("RESUME_FORMATTER_PATH is not set in .env")
    backend_dir = Path(settings.RESUME_FORMATTER_PATH).expanduser() / "backend"
    if not backend_dir.exists():
        raise FileNotFoundError(f"Resume formatter backend folder not found: {backend_dir}")
    p = str(backend_dir)
    if p not in sys.path:
        sys.path.insert(0, p)
    # The formatter's structurer uses os.getenv("OPENAI_API_KEY") directly.
    # Make sure the key is in the environment (pydantic-settings only writes to
    # the Settings object, not os.environ).
    if settings.OPENAI_API_KEY and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY


def _docx_to_pdf_sync(docx_path: str, pdf_path: str) -> bool:
    """Convert DOCX → PDF. Windows uses docx2pdf (MS Word COM);
    Linux/Mac uses LibreOffice."""
    if os.name == "nt":
        # Drive Word via COM with ExportAsFixedFormat. We deliberately avoid
        # docx2pdf here: it converts via Document.SaveAs(FileFormat=17), which
        # fails ("RPC call failed") on the Office build installed on this box,
        # whereas ExportAsFixedFormat renders the same DOCX reliably.
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore

        wd_export_format_pdf = 17  # wdExportFormatPDF
        pythoncom.CoInitialize()
        word = None
        doc = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(os.path.abspath(docx_path), ReadOnly=True)
            doc.ExportAsFixedFormat(os.path.abspath(pdf_path), wd_export_format_pdf)
        except Exception as exc:
            logger.warning("Word COM PDF export failed: %s", exc)
        finally:
            # Best-effort teardown — Word can drop the COM connection after a
            # conversion, so a failing Close/Quit must not mask a written PDF.
            if doc is not None:
                try:
                    doc.Close(False)
                except Exception:
                    pass
            if word is not None:
                try:
                    word.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()
        return os.path.exists(pdf_path)
    # POSIX: use LibreOffice with an isolated profile dir
    try:
        out_dir = os.path.dirname(pdf_path)
        with tempfile.TemporaryDirectory(prefix="lo-profile-") as profile:
            result = subprocess.run(
                [
                    "soffice",
                    f"-env:UserInstallation=file://{profile}",
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", out_dir,
                    docx_path,
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
        if result.returncode != 0:
            logger.warning("soffice exit=%s stderr=%s", result.returncode, result.stderr[:300])
            return False
        return os.path.exists(pdf_path)
    except FileNotFoundError:
        logger.warning("soffice not installed; cannot render PDF")
        return False
    except Exception as exc:
        logger.warning("soffice conversion failed: %s", exc)
        return False


def _render_sync(resume_text: str, persist_to: str | None) -> bytes | None:
    """Synchronous pipeline. Runs in an executor — do not call from the event loop."""
    try:
        _add_formatter_to_path()
        from ai.structurer import structure_resume  # type: ignore
        from formatters.compact_ats import format_compact  # type: ignore
    except Exception as exc:
        logger.warning("Resume formatter unavailable: %s", exc)
        return None

    try:
        structured = structure_resume(resume_text)
    except Exception as exc:
        logger.warning("structure_resume failed: %s", exc)
        return None

    tmp_dir = tempfile.mkdtemp(prefix="resume-")
    docx_path = os.path.join(tmp_dir, "resume.docx")
    pdf_path = os.path.join(tmp_dir, "resume.pdf")
    try:
        try:
            format_compact(structured, docx_path)
        except Exception as exc:
            logger.warning("format_compact failed: %s", exc)
            return None

        if not _docx_to_pdf_sync(docx_path, pdf_path):
            return None

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        if persist_to:
            try:
                os.makedirs(os.path.dirname(persist_to), exist_ok=True)
                with open(persist_to, "wb") as f:
                    f.write(pdf_bytes)
            except Exception as exc:
                logger.warning("Could not persist generated PDF to %s: %s", persist_to, exc)

        return pdf_bytes
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def render_pdf_resume(resume_text: str, persist_to: str | None = None) -> bytes | None:
    """Render `resume_text` as an ATS-formatted PDF via the resume-formatter pipeline.

    `persist_to` (optional): if provided, also write the PDF bytes to this absolute path
    (parent dirs are created). Used to keep an archival copy per application.

    Returns the PDF bytes, or None if any step in the pipeline failed. The caller
    should treat None as a soft failure and continue without a PDF (agents will
    fall back to plaintext resume upload).
    """
    if not resume_text or not resume_text.strip():
        return None
    if not settings.RESUME_FORMATTER_PATH:
        logger.info("RESUME_FORMATTER_PATH not set — skipping PDF render")
        return None
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _render_sync, resume_text, persist_to)


def resume_archive_path(application_id: int) -> str:
    """Where the generated PDF is archived on disk for a given application."""
    backend_root = Path(__file__).resolve().parents[2]  # backend/
    return str(backend_root / "uploads" / "resumes" / f"application_{application_id}.pdf")
