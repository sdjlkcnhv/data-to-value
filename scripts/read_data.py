#!/usr/bin/env python3
"""Read bounded previews without installing dependencies or modifying source files."""
import argparse
import csv
from datetime import date, datetime
from decimal import Decimal
import importlib
import itertools
import json
import math
from pathlib import Path
import sqlite3
from zipfile import ZipFile

from console_utils import configure_console


FORMATS = {
    **dict.fromkeys((".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".txt", ".md", ".log", ".sqlite", ".sqlite3", ".db", ".zip"), "core"),
    **dict.fromkeys((".xlsx", ".xlsm"), "tabular"),
    **dict.fromkeys((".xls", ".xlsb", ".ods", ".parquet", ".feather", ".pdf", ".docx", ".html", ".htm", ".xml"), "common"),
    **dict.fromkeys((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"), "ocr"),
}


class ReadIssue(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def need(module):
    try:
        return importlib.import_module(module)
    except ImportError as error:
        raise ReadIssue("missing_dependency", f"{module}: {error}; use an initialized runtime, not a per-upload install") from error


def safe_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"nonfinite": str(value)}
    if isinstance(value, (datetime, date)):
        return {"datetime": value.isoformat()}
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, dict):
        return {str(k): safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_value(v) for v in value]
    return str(value)


def records_unit(name, rows, limit, columns=None, total=None):
    sample = list(itertools.islice(iter(rows), limit + 1))
    truncated = len(sample) > limit or (total is not None and total > limit)
    result = {"name": str(name), "records": safe_value(sample[:limit]), "records_returned": min(len(sample), limit),
              "scope": "sample" if truncated else "all_records", "total_records": total if total is not None else (None if truncated else len(sample))}
    if columns is not None:
        result["columns"] = list(columns)
    return result


def text_unit(name, text, limit):
    return {"name": str(name), "text": text[:limit], "characters_returned": min(len(text), limit),
            "scope": "sample" if len(text) > limit else "all_extracted_text"}


def read_data(path, *, limit=100, max_units=10, max_chars=20000, max_bytes=64*1024*1024, encoding="utf-8-sig", delimiter=None, ocr=False, language="eng"):
    path = Path(path).resolve()
    extension = path.suffix.lower()
    result = {"schema_version": 1, "source": str(path), "format": extension.lstrip("."),
              "required_profile": FORMATS.get(extension), "status": "pending", "units": [], "warnings": [],
              "audit_complete": False, "limits": {"records_per_unit": limit, "units": max_units, "characters_per_unit": max_chars, "source_bytes": max_bytes}}
    try:
        if min(limit, max_units, max_chars, max_bytes) < 1:
            raise ReadIssue("invalid_options", "All limits must be positive")
        if extension not in FORMATS:
            raise ReadIssue("unsupported_format", "No reader registered for this format; no dependency installation attempted")
        result["size_bytes"] = path.stat().st_size
        if result["size_bytes"] > max_bytes:
            raise ReadIssue("size_limit", "Source exceeds the configured size limit; plan a bounded read explicitly")
        warnings = result["warnings"]
        units = result["units"]
        result["encoding"] = encoding if extension in {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".txt", ".md", ".log", ".html", ".htm"} else None
        if extension in {".csv", ".tsv"}:
            with path.open(encoding=encoding, newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter or ("\t" if extension == ".tsv" else ","), strict=True)
                columns = next(reader, [])
                unit = records_unit(path.name, reader, limit, columns=columns)
            units.append(unit)
            warnings.append("First record is treated as header; column names and values are not interpreted or coerced.")
            if len(set(columns)) != len(columns):
                warnings.append("Duplicate headers retained by physical position; do not merge them into dictionary keys.")
            if any(len(row) != len(columns) for row in unit["records"]):
                warnings.append("Sample includes rows with a different field count than the header.")
        elif extension in {".json", ".jsonl", ".ndjson"}:
            def object_pairs(pairs):
                obj = {}
                for key, value in pairs:
                    if key in obj:
                        raise ReadIssue("invalid_data", "Duplicate JSON key: " + key)
                    obj[key] = value
                return obj
            def decode(text):
                return json.loads(text, object_pairs_hook=object_pairs,
                                  parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonstandard JSON constant: " + x)))
            if extension == ".json":
                value = decode(path.read_text(encoding=encoding))
                rows = value if isinstance(value, list) else [value]
                units.append(records_unit(path.name, rows, limit, total=len(rows)))
                result["parsed_entire_source"] = True
            else:
                with path.open(encoding=encoding) as handle:
                    units.append(records_unit(path.name, (decode(line) for line in handle if line.strip()), limit))
        elif extension in {".txt", ".md", ".log"}:
            with path.open(encoding=encoding) as handle:
                units.append(text_unit(path.name, handle.read(max_chars + 1), max_chars))
        elif extension in {".xlsx", ".xlsm"}:
            engine = need("openpyxl")
            workbook = engine.load_workbook(path, read_only=True, data_only=False)
            try:
                result["unit_names"] = workbook.sheetnames
                for sheet in workbook.worksheets[:max_units]:
                    units.append(records_unit(sheet.title, sheet.iter_rows(values_only=True), limit))
            finally:
                workbook.close()
            warnings.append("Raw cell rows; first row is not assumed to be a header. Formula expressions retained, not evaluated; macros not executed.")
        elif extension in {".xls", ".xlsb", ".ods"}:
            engine = need("python_calamine")
            with engine.CalamineWorkbook.from_path(str(path)) as workbook:
                result["unit_names"] = workbook.sheet_names
                for name in workbook.sheet_names[:max_units]:
                    sheet = workbook.get_sheet_by_name(name)
                    units.append(records_unit(name, sheet.to_python(skip_empty_area=False), limit))
            warnings.append("Reader may materialize each selected sheet. Raw values only; formulas, formatting and merged-cell semantics are not preserved.")
        elif extension == ".parquet":
            engine = need("pyarrow.parquet")
            with engine.ParquetFile(path) as file:
                rows = (row for batch in file.iter_batches(batch_size=min(limit+1, 1024))
                        for row in zip(*(column.to_pylist() for column in batch.columns)))
                units.append(records_unit(path.name, rows, limit, columns=file.schema_arrow.names, total=file.metadata.num_rows))
        elif extension == ".feather":
            table = need("pyarrow.feather").read_table(path, memory_map=True)
            sample = table.slice(0, limit+1)
            rows = zip(*(column.to_pylist() for column in sample.columns))
            units.append(records_unit(path.name, rows, limit, columns=table.column_names, total=table.num_rows))
        elif extension in {".sqlite", ".sqlite3", ".db"}:
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            try:
                connection.execute("PRAGMA query_only=ON")
                names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                result["unit_names"] = names
                for name in names[:max_units]:
                    quoted = '"' + name.replace('"', '""') + '"'
                    cursor = connection.execute("SELECT * FROM " + quoted + " LIMIT ?", (limit+1,))
                    units.append(records_unit(name, cursor, limit, columns=[column[0] for column in cursor.description]))
            finally:
                connection.close()
            warnings.append("Read-only table preview; no stable row ordering implied. Views and external database connections are not queried.")
        elif extension == ".docx":
            document = need("docx").Document(path)
            blocks = document.iter_inner_content()
            for index, block in enumerate(itertools.islice(blocks, max_units+1)):
                if index == max_units:
                    result["more_units"] = True
                    break
                if hasattr(block, "rows"):
                    units.append(records_unit(f"table-block-{index+1}", ([cell.text for cell in row.cells] for row in block.rows), limit))
                else:
                    units.append(text_unit(f"paragraph-{index+1}", block.text, max_chars))
            warnings.append("Main body text/tables only; images, text boxes, headers, footnotes and layout are not audited.")
        elif extension in {".html", ".htm"}:
            soup = need("bs4").BeautifulSoup(path.read_text(encoding=encoding), "html.parser")
            for node in soup(["script", "style"]):
                node.decompose()
            units.append(text_unit(path.name, soup.get_text("\n", strip=True), max_chars))
            warnings.append("Visible text extraction only; no JavaScript execution, network fetch or table-structure inference.")
        elif extension == ".xml":
            tree = need("defusedxml.ElementTree").parse(path)
            units.append(text_unit(path.name, "\n".join(tree.getroot().itertext()), max_chars))
            warnings.append("Text extraction only; XML schema, attributes and relationships require a separate audit.")
        elif extension == ".zip":
            with ZipFile(path) as archive:
                entries = [{"path": item.filename, "size_bytes": item.file_size, "compressed_bytes": item.compress_size,
                            "encrypted": bool(item.flag_bits & 1)} for item in archive.infolist()]
                units.append(records_unit("archive_inventory", entries, limit, total=len(entries)))
            warnings.append("Inventory only; members are not extracted or read. Do not treat contained datasets as audited.")
        elif extension == ".pdf":
            reader = need("pypdf").PdfReader(path)
            if reader.is_encrypted:
                raise ReadIssue("encrypted", "Encrypted PDF; no decryption attempted")
            result["total_pages"] = len(reader.pages)
            for index, page in enumerate(reader.pages[:max_units]):
                text = page.extract_text() or ""
                if not text.strip() and ocr:
                    text = pdf_ocr(path, index, language)
                unit = text_unit(f"page-{index+1}", text, max_chars)
                unit["extraction"] = "ocr" if ocr and not (page.extract_text() or "").strip() else "text"
                units.append(unit)
                if not text.strip():
                    warnings.append(f"Page {index+1} has no extractable text; may need OCR or contain no text.")
            if any(not unit["text"].strip() for unit in units):
                result["status"] = "needs_ocr_or_review"
            result["more_units"] = len(reader.pages) > max_units
            warnings.append("Text extraction does not guarantee correct reading order, table structure or complete image coverage.")
        else:
            if not ocr:
                raise ReadIssue("needs_ocr", "Image input requires the optional OCR runtime and explicit --ocr")
            image = need("PIL.Image")
            with image.open(path) as img:
                if getattr(img, "n_frames", 1) > 1:
                    warnings.append("Only first image frame extracted.")
                    result["more_units"] = True
                units.append(text_unit(path.name, image_ocr(img, language), max_chars))
            if not units[0]["text"].strip():
                result["status"] = "needs_review"
            warnings.append("OCR is inferred text; compare with the image before treating it as measurement or truth.")
        if "unit_names" in result:
            result["more_units"] = len(result["unit_names"]) > max_units
        if result["status"] == "pending":
            result["status"] = "partial" if result.get("more_units") or any(unit["scope"] == "sample" for unit in units) else "read"
    except ReadIssue as error:
        result.update(status=error.status, error=str(error))
    except UnicodeError as error:
        result.update(status="encoding_error", error=str(error), hint="Specify the known source encoding using --encoding; no lossy guessing performed")
    except Exception as error:
        result.update(status="read_error", error=type(error).__name__ + ": " + str(error))
    return result


def image_ocr(image, language):
    engine = need("pytesseract")
    try:
        return engine.image_to_string(image, lang=language, timeout=60)
    except engine.TesseractNotFoundError as error:
        raise ReadIssue("missing_external_tool", "Tesseract executable not installed or not on PATH") from error


def pdf_ocr(path, index, language):
    engine = need("pypdfium2")
    with engine.PdfDocument(str(path)) as doc:
        page = doc[index]
        try:
            bitmap = page.render(scale=2)
            try:
                return image_ocr(bitmap.to_pil(), language)
            finally:
                bitmap.close()
        finally:
            page.close()


def main():
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-units", type=int, default=10)
    parser.add_argument("--max-chars", type=int, default=20000)
    parser.add_argument("--max-bytes", type=int, default=64*1024*1024)
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--delimiter")
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--language", default="eng")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must differ")
    result = read_data(args.input, limit=args.limit, max_units=args.max_units, max_chars=args.max_chars,
                       max_bytes=args.max_bytes, encoding=args.encoding, delimiter=args.delimiter, ocr=args.ocr, language=args.language)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    print(result["status"] + ": " + str(args.output.resolve()))
    return 0 if result["status"] in {"read", "partial"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
