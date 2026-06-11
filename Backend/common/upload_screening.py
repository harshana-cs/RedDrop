from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable

import requests
from PIL import ExifTags, Image, ImageChops, ImageEnhance, ImageStat

from django.conf import settings


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
DOCUMENT_EXTENSIONS = {".pdf"}


def _get_extension(uploaded_file) -> str:
    name = getattr(uploaded_file, "name", "") or ""
    _, ext = os.path.splitext(name.lower())
    return ext


def _get_content_type(uploaded_file) -> str:
    return (getattr(uploaded_file, "content_type", "") or "").lower()


def _read_upload_bytes(uploaded_file) -> bytes:
    if not uploaded_file or not hasattr(uploaded_file, "read"):
        return b""

    try:
        data = uploaded_file.read()
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

    if isinstance(data, str):
        return data.encode("utf-8", errors="ignore")
    return data or b""


def _looks_like_image(uploaded_file) -> bool:
    ext = _get_extension(uploaded_file)
    content_type = _get_content_type(uploaded_file)
    return ext in IMAGE_EXTENSIONS or content_type.startswith("image/")


def _looks_like_pdf(uploaded_file, data: bytes) -> bool:
    ext = _get_extension(uploaded_file)
    content_type = _get_content_type(uploaded_file)
    return ext in DOCUMENT_EXTENSIONS or content_type == "application/pdf" or data.startswith(b"%PDF")


def _risk_verdict(score: int) -> str:
    if score >= 70:
        return "BLOCK"
    if score >= 40:
        return "REVIEW"
    return "PASS"


def check_exif_metadata(uploaded_file) -> dict[str, Any]:
    data = _read_upload_bytes(uploaded_file)
    if not data:
        return {
            "applied": False,
            "exif_present": False,
            "suspicious": False,
            "flags": [],
        }

    if not _looks_like_image(uploaded_file):
        return {
            "applied": False,
            "exif_present": False,
            "suspicious": False,
            "flags": [],
        }

    flags: list[str] = []
    exif_present = False

    try:
        image = Image.open(io.BytesIO(data))
        exif_data = image.getexif()
        exif_present = bool(exif_data)

        if not exif_data:
            flags.append("NO_EXIF: Image has no camera metadata")
        else:
            exif = {
                ExifTags.TAGS.get(key, key): value
                for key, value in exif_data.items()
            }

            expected_fields = ["Make", "Model", "DateTime", "ExposureTime", "ISOSpeedRatings"]
            missing = [field for field in expected_fields if field not in exif]
            if len(missing) >= 3:
                flags.append(f"MISSING_CAMERA_DATA: {', '.join(missing)}")
    except Exception as exc:
        flags.append(f"IMAGE_OPEN_FAILED: {exc}")

    return {
        "applied": True,
        "exif_present": exif_present,
        "suspicious": bool(flags),
        "flags": flags,
    }


def error_level_analysis(uploaded_file, quality: int = 90) -> dict[str, Any]:
    data = _read_upload_bytes(uploaded_file)
    if not data or not _looks_like_image(uploaded_file):
        return {
            "applied": False,
            "mean_ela": 0.0,
            "std_ela": 0.0,
            "suspicious": False,
            "flags": [],
        }

    flags: list[str] = []

    try:
        original = Image.open(io.BytesIO(data)).convert("RGB")
        compressed_buffer = io.BytesIO()
        original.save(compressed_buffer, "JPEG", quality=quality)
        compressed_buffer.seek(0)
        compressed = Image.open(compressed_buffer).convert("RGB")

        ela_image = ImageChops.difference(original, compressed)
        extrema = ela_image.getextrema()
        max_diff = max(channel_max for _, channel_max in extrema) if extrema else 0
        scale = 255.0 / max_diff if max_diff else 1.0
        ela_image = ImageEnhance.Brightness(ela_image).enhance(scale)

        stat = ImageStat.Stat(ela_image)
        mean_ela = round(sum(stat.mean) / len(stat.mean), 2) if stat.mean else 0.0
        std_ela = round(sum(stat.stddev) / len(stat.stddev), 2) if stat.stddev else 0.0

        suspicious = std_ela < 18 and mean_ela > 12
        if suspicious:
            flags.append("UNIFORM_ELA: Possible edited or AI-generated image")

        return {
            "applied": True,
            "mean_ela": mean_ela,
            "std_ela": std_ela,
            "suspicious": suspicious,
            "flags": flags,
        }
    except Exception as exc:
        flags.append(f"ELA_FAILED: {exc}")
        return {
            "applied": True,
            "mean_ela": 0.0,
            "std_ela": 0.0,
            "suspicious": True,
            "flags": flags,
        }


def check_pdf_metadata(uploaded_file) -> dict[str, Any]:
    data = _read_upload_bytes(uploaded_file)
    if not data or not _looks_like_pdf(uploaded_file, data):
        return {
            "applied": False,
            "suspicious": False,
            "flags": [],
        }

    flags: list[str] = []
    header = data[:65536].decode("latin1", errors="ignore")
    expected = ["/Creator", "/Producer", "/CreationDate", "/ModDate", "/Author", "/Title", "/Subject"]
    missing = [field for field in expected if field not in header]

    if len(missing) >= 4:
        flags.append(f"MISSING_PDF_METADATA: {', '.join(missing)}")

    # Generic metadata is a common signal for PDFs created by generators or AI-to-PDF tools.
    generic_markers = [
        r"\(anonymous\)",
        r"\(unspecified\)",
        r"ReportLab PDF Library",
        r"wkhtmltopdf",
        r"WeasyPrint",
        r"PDFKit",
        r"iText",
        r"LibreOffice",
    ]
    generic_hits = [marker for marker in generic_markers if re.search(marker, header, re.I)]
    if generic_hits:
        flags.append(f"GENERATOR_METADATA: {', '.join(generic_hits)}")

    # A document with anonymous title/author/subject and a generator marker is likely synthetic.
    generic_value_count = sum(
        1
        for pattern in [r"/Author\s*\(\(anonymous\)\)", r"/Title\s*\(\(anonymous\)\)", r"/Subject\s*\(\(unspecified\)\)", r"/Creator\s*\(\(unspecified\)\)"]
        if re.search(pattern, header, re.I)
    )
    if generic_value_count >= 3:
        flags.append("GENERIC_PDF_IDENTITY: Author/title/subject/creator are generic")

    if not re.search(r"/(Image|XObject)", header):
        flags.append("LOW_PDF_STRUCTURE: Missing common PDF document markers")

    if len(data) < 12_000 and generic_hits:
        flags.append("SMALL_GENERATED_PDF: Tiny file with generator metadata")

    return {
        "applied": True,
        "suspicious": bool(flags),
        "flags": flags,
    }


def check_with_hive(uploaded_file) -> dict[str, Any]:
    api_key = os.getenv("HIVE_API_KEY") or getattr(settings, "HIVE_API_KEY", "")
    if not api_key or not uploaded_file:
        return {
            "applied": False,
            "flagged": False,
            "ai_probability": None,
            "flags": [],
        }

    data = _read_upload_bytes(uploaded_file)
    if not data:
        return {
            "applied": False,
            "flagged": False,
            "ai_probability": None,
            "flags": [],
        }

    filename = getattr(uploaded_file, "name", "upload")
    try:
        response = requests.post(
            "https://api.thehive.ai/api/v2/task/sync",
            headers={"Authorization": f"Token {api_key}"},
            files={"image": (filename, io.BytesIO(data), "application/octet-stream")},
            data={"model": "ai_generated_image_detection"},
            timeout=20,
        )
        response.raise_for_status()
        result = response.json()

        classes = (
            result.get("status", [{}])[0]
            .get("response", {})
            .get("output", [{}])[0]
            .get("classes", [])
        )
        ai_score = 0.0
        for cls in classes:
            if cls.get("class") == "ai_generated":
                ai_score = float(cls.get("score") or 0)
                break

        flagged = ai_score > 0.75
        flags = []
        if flagged:
            flags.append(f"HIVE_AI_SCORE: {ai_score:.2f}")

        return {
            "applied": True,
            "flagged": flagged,
            "ai_probability": ai_score,
            "flags": flags,
            "raw": result,
        }
    except Exception as exc:
        return {
            "applied": True,
            "flagged": False,
            "ai_probability": None,
            "flags": [f"HIVE_FAILED: {exc}"],
        }


def screen_uploaded_file(uploaded_file, upload_label: str = "Uploaded file", upload_type: str = "document") -> dict[str, Any]:
    data = _read_upload_bytes(uploaded_file)
    if not uploaded_file:
        return {
            "label": upload_label,
            "upload_type": upload_type,
            "risk_score": 0,
            "verdict": "PASS",
            "flags": [],
            "details": {},
        }

    details: dict[str, Any] = {}
    flags: list[str] = []
    risk_score = 0

    is_image = _looks_like_image(uploaded_file)
    is_pdf = _looks_like_pdf(uploaded_file, data)

    if is_image:
        exif = check_exif_metadata(uploaded_file)
        details["metadata"] = exif
        if exif["suspicious"]:
            risk_score += 25
            flags.extend(exif["flags"])

        ela = error_level_analysis(uploaded_file)
        details["ela"] = ela
        if ela["suspicious"]:
            risk_score += 35
            flags.extend(ela["flags"])

        hive = check_with_hive(uploaded_file)
        details["hive"] = hive
        if hive.get("flagged"):
            risk_score += 60
            flags.extend(hive.get("flags", []))

    elif is_pdf:
        pdf_meta = check_pdf_metadata(uploaded_file)
        details["pdf_metadata"] = pdf_meta
        if pdf_meta["suspicious"]:
            risk_score += 35
            flags.extend(pdf_meta["flags"])

        if len(data) < 12_000:
            risk_score += 10
            flags.append("SMALL_PDF: Very small document file")

    else:
        risk_score += 20
        flags.append("UNSUPPORTED_FORMAT: Unable to verify this upload type")

    verdict = _risk_verdict(risk_score)

    return {
        "label": upload_label,
        "upload_type": upload_type,
        "risk_score": min(risk_score, 100),
        "verdict": verdict,
        "flags": flags,
        "details": details,
    }


def screen_uploaded_files(file_map: dict[str, Any], upload_type: str = "document") -> dict[str, Any]:
    file_results: dict[str, Any] = {}
    flagged_files: list[str] = []
    combined_flags: list[str] = []
    total_risk = 0

    for label, uploaded_file in file_map.items():
        result = screen_uploaded_file(uploaded_file, upload_label=label.replace("_", " ").title(), upload_type=upload_type)
        file_results[label] = result
        total_risk += int(result["risk_score"])
        if result["verdict"] != "PASS":
            flagged_files.append(label)
        combined_flags.extend([f"{label}: {flag}" for flag in result["flags"]])

    total_risk = min(total_risk, 100)
    verdict = _risk_verdict(total_risk)

    return {
        "risk_score": total_risk,
        "verdict": verdict,
        "file_results": file_results,
        "flagged_files": flagged_files,
        "flags": combined_flags,
    }


def notify_suspicious_upload(
    *,
    title: str,
    message: str,
    upload_result: dict[str, Any],
    hospital=None,
    blood_request=None,
    user=None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        from adminpanel.models import Notification, HospitalAuditLog

        Notification.objects.create(
            title=title,
            message=message,
            type="system_alert",
            hospital=hospital,
            blood_request=blood_request,
            user=user,
            is_read=False,
        )

        if hospital:
            HospitalAuditLog.objects.create(
                hospital=hospital,
                action="document_upload",
                description=message,
                metadata={
                    "risk_score": upload_result.get("risk_score"),
                    "verdict": upload_result.get("verdict"),
                    "flags": upload_result.get("flags", []),
                    **(metadata or {}),
                },
            )
    except Exception:
        pass
