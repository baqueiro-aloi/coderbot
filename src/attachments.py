"""Channel-independent attachment descriptors and lossless transport preparation."""
import gzip
import hashlib
import json
import mimetypes
from pathlib import Path
import secret_safety


def assert_safe_text(path):
    """Reject detectable secrets before copying/compressing/publishing bytes.

    Text scanning is not a media/content attestation. Binary evidence needs its
    separate trusted capture/publication gate, not a guessed MIME exemption.
    """
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return
    if secret_safety.redact(text) != text:
        raise ValueError('Attachment contains sensitive text; prepare a sanitized copy before publication')


def describe(path, *, role="supporting"):
    path = Path(path)
    size = path.stat().st_size
    return {"id": hashlib.sha256(path.read_bytes()).hexdigest(), "path": str(path),
            "filename": path.name, "media_type": mimetypes.guess_type(path.name)[0]
            or "application/octet-stream", "size": size, "role": role}


def delivery_name(path):
    path = Path(path)
    return path.with_suffix(".txt").name if path.suffix.lower() == ".log" else path.name


def encoded_size(size):
    """Base64 plus MIME line wrapping, rounded up."""
    base64 = 4 * ((size + 2) // 3)
    return base64 + 2 * ((base64 + 75) // 76) + 1024


def prepare(artifact, limit, directory, *, mime=False):
    assert_safe_text(artifact['path'])
    if Path(artifact["path"]).suffix.lower() == ".log":
        # Copy into the durable transport area: keep the source log intact and
        # give both providers a real .txt path for MIME/preview detection.
        text = Path(directory) / artifact["id"] / delivery_name(artifact["path"])
        text.parent.mkdir(parents=True, exist_ok=True)
        text.write_bytes(Path(artifact["path"]).read_bytes())
        artifact = describe(text, role=artifact["role"])
    size_of = encoded_size if mime else lambda n: n
    if size_of(artifact["size"]) <= limit:
        return [artifact]
    if limit < 4096:
        raise ValueError("attachment limit too small for a diagnostic manifest")
    directory = Path(directory) / artifact["id"]
    directory.mkdir(parents=True, exist_ok=True)
    data = gzip.compress(Path(artifact["path"]).read_bytes(), mtime=0)
    compressed = directory / (artifact["filename"] + ".gz")
    compressed.write_bytes(data)
    if size_of(len(data)) <= limit:
        return [describe(compressed, role=artifact["role"])]
    part_size = (limit - 2048) * 3 // 4 if mime else limit
    count = (len(data) + part_size - 1) // part_size
    parts = []
    for index in range(count):
        path = directory / f"{compressed.name}.part-{index + 1:04d}-of-{count:04d}"
        path.write_bytes(data[index * part_size:(index + 1) * part_size])
        parts.append(describe(path, role=artifact["role"]))
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps({"original": artifact["filename"], "sha256": artifact["id"],
        "encoding": "concatenate numbered parts then gzip decompress",
        "parts": [{"filename": p["filename"], "sha256": p["id"]} for p in parts]}, indent=2))
    descriptor = describe(manifest, role=artifact["role"])
    if size_of(descriptor["size"]) > limit:
        # A huge list can exceed limits too; omit hashes in the compact manifest.
        manifest.write_text(json.dumps({"original": artifact["filename"], "sha256": artifact["id"],
            "parts": count, "encoding": "concatenate parts in numeric order; gzip decompress"}))
        descriptor = describe(manifest, role=artifact["role"])
    return [descriptor, *parts]
