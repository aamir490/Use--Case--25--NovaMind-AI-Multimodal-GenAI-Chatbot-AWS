"""Isolated document validator. Archives are never extracted to disk."""
import io
import json
import posixpath
import sys
import zipfile
from pathlib import PurePosixPath
from xml.parsers import expat

MAX_MEMBERS = 1000
MAX_PART_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_RATIO = 100
MAX_PAGES = 200
MAX_OBJECTS = 10000


def restrict_memory():
    """Fail closed if a 512 MiB worker memory ceiling cannot be installed."""
    limit = 512 * 1024 * 1024
    if sys.platform != "win32":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        return None
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64),
                    ("flags", w.DWORD), ("min_ws", c.c_size_t), ("max_ws", c.c_size_t),
                    ("active", w.DWORD), ("affinity", c.c_size_t),
                    ("priority", w.DWORD), ("scheduling", w.DWORD)]
    class Extended(c.Structure):
        _fields_ = [("basic", Basic), ("io", c.c_uint64 * 6),
                    ("process_memory", c.c_size_t), ("job_memory", c.c_size_t),
                    ("peak_process", c.c_size_t), ("peak_job", c.c_size_t)]
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.GetCurrentProcess.restype = w.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.process_memory = limit
    if (not job or not kernel.SetInformationJobObject(job, 9, c.byref(info), c.sizeof(info))
            or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess())):
        raise ValueError("Cannot establish parser memory limit")
    return job  # Keep the handle alive until this short-lived worker exits.


def xml_root(data, visit=None):
    parser = expat.ParserCreate(namespace_separator="}")
    depth = nodes = 0
    root = None
    def start(name, attrs):
        nonlocal depth, nodes, root
        depth += 1
        nodes += 1
        if depth > 64 or nodes > 100000:
            raise ValueError("XML budget exceeded")
        root = root or name
        if visit:
            visit(name, attrs)
    def end(name):
        nonlocal depth
        depth -= 1
    def forbidden(*args):
        raise ValueError("DTD and entities are forbidden")
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.Parse(data, True)
    return root


def validate_ooxml(data, fmt):
    main = "word/document.xml" if fmt == "docx" else "xl/workbook.xml"
    expected = ("http://schemas.openxmlformats.org/wordprocessingml/2006/main}document"
                if fmt == "docx" else "http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError("Too many ZIP entries")
        names = [i.filename for i in infos]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP members")
        if not {main, "[Content_Types].xml", "_rels/.rels"}.issubset(names):
            raise ValueError("Missing Office package parts")
        expanded = 0
        roots = {}
        package_link = content_type = False
        targets = []
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename or ":" in info.filename:
                raise ValueError("Unsafe member name")
            if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError("Unsupported archive encoding")
            if info.file_size > MAX_PART_BYTES or info.file_size > max(1, info.compress_size) * MAX_RATIO:
                raise ValueError("Archive expansion limit")
            expanded += info.file_size
            if expanded > MAX_EXPANDED_BYTES:
                raise ValueError("Archive total expansion limit")
            with archive.open(info) as member:
                content = member.read(MAX_PART_BYTES + 1)
            if len(content) != info.file_size or len(content) > MAX_PART_BYTES:
                raise ValueError("Invalid archive member size")
            if info.filename.endswith((".xml", ".rels")):
                def visit(name, attrs):
                    nonlocal package_link, content_type
                    if info.filename.endswith(".rels") and name.endswith("}Relationship"):
                        if attrs.get("TargetMode") != "External":
                            target = attrs.get("Target", "")
                            source_dir = posixpath.dirname(posixpath.dirname(info.filename))
                            resolved = posixpath.normpath(posixpath.join(source_dir, target)).lstrip("/")
                            if not target or resolved.startswith("../"):
                                raise ValueError("Invalid relationship target")
                            targets.append(resolved)
                    if info.filename == "_rels/.rels" and name.endswith("}Relationship"):
                        if attrs.get("Type", "").endswith("/officeDocument"):
                            if attrs.get("Target", "").lstrip("/") != main or attrs.get("TargetMode") == "External":
                                raise ValueError("Invalid main part relationship")
                            package_link = True
                    if info.filename == "[Content_Types].xml" and name.endswith("}Override"):
                        if attrs.get("PartName") == "/" + main:
                            expected_type = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
                                             if fmt == "docx" else
                                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
                            if attrs.get("ContentType") != expected_type:
                                raise ValueError("Wrong main content type")
                            content_type = True
                roots[info.filename] = xml_root(content, visit)
            if info.filename.endswith("vbaProject.bin"):
                raise ValueError("Macro-enabled package not supported")
        if roots.get(main) != expected:
            raise ValueError("Wrong Office document type")
        if not package_link or not content_type:
            raise ValueError("Missing main part declaration")
        if any(target not in names for target in targets):
            raise ValueError("Missing referenced Office part")
        if roots.get("[Content_Types].xml") != "http://schemas.openxmlformats.org/package/2006/content-types}Types":
            raise ValueError("Invalid content types")
        if roots.get("_rels/.rels") != "http://schemas.openxmlformats.org/package/2006/relationships}Relationships":
            raise ValueError("Invalid package relationships")
    return "[Office package validated; text preview unavailable.]", 0


def validate_legacy(data, fmt):
    import olefile
    with olefile.OleFileIO(io.BytesIO(data), raise_defects=olefile.DEFECT_INCORRECT) as ole:
        names = ole.listdir()
        if len(names) > MAX_MEMBERS:
            raise ValueError("Too many OLE streams")
        total = 0
        for name in names:
            size = ole.get_size(name)
            total += size
            if size > MAX_PART_BYTES or total > MAX_EXPANDED_BYTES:
                raise ValueError("OLE stream budget")
            with ole.openstream(name) as stream:
                if len(stream.read(MAX_PART_BYTES + 1)) != size:
                    raise ValueError("Truncated OLE stream")
        target = "WordDocument" if fmt == "doc" else ("Workbook" if ole.exists("Workbook") else "Book")
        with ole.openstream(target) as stream:
            body = stream.read(MAX_PART_BYTES + 1)
        if fmt == "doc":
            if len(body) < 32 or body[:2] != b"\xec\xa5":
                raise ValueError("Invalid Word file information block")
            flags = int.from_bytes(body[10:12], "little")
            if flags & 0x8100 or not ole.exists("1Table" if flags & 0x0200 else "0Table"):
                raise ValueError("Encrypted or incomplete Word document")
        else:
            if body[:2] not in (b"\x09\x08", b"\x09\x04", b"\x09\x02"):
                raise ValueError("Invalid BIFF workbook")
            offset = 0
            saw_eof = False
            while offset < len(body):
                if offset + 4 > len(body):
                    raise ValueError("Truncated BIFF record")
                tag = int.from_bytes(body[offset:offset+2], "little")
                length = int.from_bytes(body[offset+2:offset+4], "little")
                offset += 4 + length
                if offset > len(body) or tag == 0x2F:
                    raise ValueError("Truncated or encrypted workbook")
                saw_eof |= tag == 0x0A
            if not saw_eof:
                raise ValueError("Missing BIFF EOF")
    return "[Legacy Office container validated; text preview unavailable.]", 0


def validate_pdf(data):
    import pypdf
    from pypdf import filters
    from pypdf.generic import IndirectObject, StreamObject
    # pypdf can invoke an external JBIG2 decoder. Validation must never launch
    # external decoders, including while reading compressed xref/object streams.
    def reject_external_decoder(*args, **kwargs):
        raise ValueError("External PDF decoder is not supported")
    filters.JBIG2Decode.decode = reject_external_decoder
    required = ("ZLIB_MAX_OUTPUT_LENGTH", "LZW_MAX_OUTPUT_LENGTH",
                "RUN_LENGTH_MAX_OUTPUT_LENGTH", "MAX_DECLARED_STREAM_LENGTH")
    if not all(hasattr(filters, key) for key in required):
        raise ValueError("Installed PDF parser lacks required resource limits")
    # Private worker process owns these settings, never the Streamlit interpreter.
    for key in required + ("MAX_ARRAY_BASED_STREAM_OUTPUT_LENGTH", "FLATE_MAX_BUFFER_SIZE"):
        if hasattr(filters, key):
            setattr(filters, key, MAX_PART_BYTES)
    if not data.rstrip().endswith(b"%%EOF"):
        raise ValueError("Missing PDF EOF")
    with pypdf.PdfReader(io.BytesIO(data), strict=True) as reader:
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF")
        count = sum(len(entries) for entries in reader.xref.values()) + len(reader.xref_objStm)
        if count > MAX_OBJECTS:
            raise ValueError("PDF object limit")
        expanded = 0
        for generation, entries in reader.xref.items():
            for number in entries:
                if number == 0:
                    continue
                obj = reader.get_object(IndirectObject(number, generation, reader))
                if isinstance(obj, StreamObject):
                    methods = obj.get("/Filter", [])
                    if isinstance(methods, str):
                        methods = [methods]
                    if any(str(m) not in {"/FlateDecode", "/ASCIIHexDecode", "/ASCII85Decode",
                                          "/RunLengthDecode", "/LZWDecode", "/DCTDecode",
                                          "/JPXDecode", "/CCITTFaxDecode"} for m in methods):
                        raise ValueError("Unsupported PDF stream filter")
                    decoded = obj.get_data()
                    expanded += len(decoded)
                    if len(decoded) > MAX_PART_BYTES or expanded > MAX_EXPANDED_BYTES:
                        raise ValueError("PDF decoded stream budget")
        pages = reader.pages
        if not 0 < len(pages) <= MAX_PAGES:
            raise ValueError("PDF page limit")
        extracted = []
        for index, page in enumerate(pages):
            content = page.get_contents()
            if content is not None:
                _ = content.operations
            if index < 3:
                extracted.append((page.extract_text() or "")[:600])
        return ("\n".join(extracted)[:600] or "[PDF validated; no extractable text.]"), len(pages)


if __name__ == "__main__":
    try:
        memory_guard = restrict_memory()
        data = sys.stdin.buffer.read(4 * 1024 * 1024 + 512 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024 + 512 * 1024:
            raise ValueError("File too large")
        fmt = sys.argv[1]
        parser = validate_pdf if fmt == "pdf" else None
        preview, pages = (parser(data) if parser else
                          validate_ooxml(data, fmt) if fmt in ("docx", "xlsx") else
                          validate_legacy(data, fmt))
        print(json.dumps({"preview": preview, "pages": pages}))
    except ImportError:
        print(json.dumps({"error": "Required file validation dependency is unavailable. Upload rejected."}))
    except Exception:
        print(json.dumps({"error": "File is corrupt, unsupported, encrypted, or exceeds parser resource limits."}))
