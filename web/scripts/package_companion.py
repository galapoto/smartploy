"""SP44: reproducible, allowlisted, installable first-party Chrome companion.

Builds a static ZIP for SmartPloy's production web assets directly from the
same reviewed browser-companion source tree used by all Node/Chromium tests.
No external code, git metadata, credentials, node_modules, source tests, or
background scripts enter the distributable. Uses Python stdlib only.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "browser-companion"
DEFAULT_OUTPUT = ROOT / "web" / "public" / "smartploy-apply-companion.zip"

# Explicit review boundary. New extension code/modules must be consciously
# added to this allowlist before a production package can include them.
FILES = (
    "manifest.json", "popup.html", "popup.css", "popup.mjs",
    "icon16.png", "icon32.png", "icon48.png", "icon128.png",
    "smartploy-mark-v2.svg",
    "logic.mjs", "upload.mjs", "questions.mjs", "page-questions.mjs",
    "page-attachment.mjs", "page-document-fetch.mjs",
    "page-review.mjs", "review-bridge.mjs",
    "page-final-claim.mjs", "page-final-submit.mjs", "attempt-lock.mjs",
)
MAX_SOURCE_BYTES = 500_000
ZIP_TIMESTAMP = (2026, 10, 1, 0, 0, 0)
MODULE_IMPORT = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*)["']([^"'\r\n]+)["']""",
)
HTML_ASSET = re.compile(r"""(?:src|href)=["']([^"']+)["']""")


def _valid_png(data: bytes, expected_size: int) -> bool:
    """Admit only complete, bounded 8-bit RGBA PNGs with valid raster rows."""
    import zlib

    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) > MAX_SOURCE_BYTES:
        return False
    index, seen_header, seen_image = 8, False, False
    idat = bytearray()
    try:
        while index + 12 <= len(data):
            n = int.from_bytes(data[index:index + 4], "big")
            kind = data[index + 4:index + 8]
            start, stop = index + 8, index + 8 + n
            if n > MAX_SOURCE_BYTES or stop + 4 > len(data):
                return False
            chunk = data[start:stop]
            crc = int.from_bytes(data[stop:stop + 4], "big")
            if zlib.crc32(kind + chunk) != crc:
                return False
            if kind == b"IHDR":
                if seen_header or index != 8 or n != 13:
                    return False
                seen_header = True
                if (int.from_bytes(chunk[:4], "big") != expected_size
                    or int.from_bytes(chunk[4:8], "big") != expected_size
                    or chunk[8:] != b"\x08\x06\x00\x00\x00"):
                    return False
            elif kind == b"IDAT":
                if not seen_header:
                    return False
                seen_image = True
                idat.extend(chunk)
            elif kind == b"IEND":
                if n or not seen_image or stop + 4 != len(data):
                    return False
                break
            else:
                # First-party icons intentionally use only IHDR, IDAT, IEND.
                # Even CRC-valid ancillary chunks can be invalid for RGBA.
                return False
            index = stop + 4
        else:
            return False
        # Bound decompression before inspecting scanlines; tiny compressed
        # inputs can otherwise expand far beyond the reviewed icon size.
        row_bytes = 1 + expected_size * 4
        expected_bytes = expected_size * row_bytes
        decoder = zlib.decompressobj()
        raw = decoder.decompress(bytes(idat), expected_bytes + 1)
        return (decoder.eof and not decoder.unused_data
                and not decoder.unconsumed_tail
                and len(raw) == expected_bytes
                and all(raw[at] <= 4 for at in range(0, expected_bytes, row_bytes)))
    except (ValueError, OverflowError, IndexError, zlib.error):
        return False

def reviewed_files() -> tuple[dict[str, bytes], str]:
    manifest_path = SOURCE / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("Manifest symlinks are not permitted")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("manifest_version") != 3
        or manifest.get("permissions") != ["activeTab", "scripting", "storage"]
        or manifest.get("host_permissions") != [
            "https://smartploy.komplyint.fi/*", "https://smartploy.obumai.com/*"
        ]
        or any(field in manifest for field in (
            "optional_host_permissions", "background",
            "content_scripts", "externally_connectable", "update_url",
        ))
        or manifest.get("action", {}).get("default_popup") != "popup.html"
        or manifest.get("icons") != {
            "16": "icon16.png", "32": "icon32.png",
            "48": "icon48.png", "128": "icon128.png",
        }
        or manifest.get("action", {}).get("default_icon") != manifest.get("icons")
        or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(manifest.get("version", "")))
    ):
        raise ValueError("Unexpected companion permissions or manifest configuration")

    files: dict[str, bytes] = {}
    for name in FILES:
        item = SOURCE / name
        if not item.is_file() or item.is_symlink() or item.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError(f"Unapproved, missing, symlinked or oversized asset: {name}")
        files[name] = item.read_bytes()
    for size in (16, 32, 48, 128):
        if not _valid_png(files[f"icon{size}.png"], size):
            raise ValueError(f"The reviewed extension icon{size}.png failed PNG integrity checks")
    # Keep the extension lockup identical to the actual SmartPloy website source.
    if files["smartploy-mark-v2.svg"] != (ROOT / "web" / "public" / "smartploy-mark-v2.svg").read_bytes():
        raise ValueError("Extension mark differs from the approved SmartPloy website mark")
    if files["icon128.png"] != (ROOT / "web" / "public" / "smartploy-mark.png").read_bytes():
        raise ValueError("Extension 128px mark differs from SmartPloy website PNG")
    if b'<script src="popup.mjs" type="module"></script>' not in files["popup.html"]:
        raise ValueError("The packaged popup does not load its reviewed module")
    if b'href="popup.css"' not in files["popup.html"]:
        raise ValueError("The packaged popup does not load its reviewed style")

    # Do not create a broken ZIP where a new static JS import is missing. No
    # remote JS or external install-time code is allowed in this artifact.
    for name, data in files.items():
        if not name.endswith(".mjs"):
            continue
        for imported in MODULE_IMPORT.findall(data.decode("utf-8")):
            if not imported.startswith("./") or imported[2:] not in files:
                raise ValueError(f"{name} references an unreviewed import: {imported}")

    # Verify all local HTML references. The ONE exact SmartPloy first-party
    # host permission is required only to read the signed-in applicant's
    # deterministic reviewed PDFs from the app tab; employer execution is
    # still user-triggered via activeTab. No wildcard employer permissions.
    for asset in HTML_ASSET.findall(files["popup.html"].decode("utf-8")):
        if asset.startswith(("./", "../", "http:", "https:", "//")):
            raise ValueError(f"Unapproved external or relative popup asset: {asset}")
        if asset not in files:
            raise ValueError(f"Popup references missing local asset: {asset}")

    return files, str(manifest["version"])


def make_zip(output: Path) -> str:
    files, version = reviewed_files()
    output.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "SmartPloy Apply Companion v" + version + " — Job intelligence\n\n"
        "1. Extract this ZIP to a local folder on your own desktop computer.\n"
        "2. In Chrome/Chromium open chrome://extensions and enable Developer mode.\n"
        "3. Choose Load unpacked, then select the EXTRACTED folder containing manifest.json.\n"
        "4. Sign in to SmartPloy, review your CV, letter and saved profile once,\n"
        "   then copy the short-lived packet. Use the companion only on the exact\n"
        "   approved job form after reading employer privacy terms. It can\n"
        "   retrieve current reviewed PDFs only from smartploy.komplyint.fi.\n"
        "5. Only individually employer-authorized Lever cases can use a separate\n"
        "   one-use final click when the server operator enables it. Otherwise\n"
        "   personally submit on the employer website and report the result.\n\n"
        "This is an unpacked Chrome extension, NOT a Chrome Web Store install.\n"
        "It does not automatically update, submit jobs in the background, or\n"
        "bypass CAPTCHA, login challenges, required consents or employer terms.\n"
        "Never share an application packet or its private contents.\n"
    ).encode("utf-8")
    sums = "\n".join(
        f"{sha256(data).hexdigest()}  {name}"
        for name, data in sorted(files.items())
    ) + "\n"
    entries = {**files, "INSTALL.txt": text, "SHA256SUMS.txt": sums.encode("ascii")}

    # ZIP_STORED + fixed metadata is deterministic across Python/zlib/runtime
    # versions; a failed build cannot leave an incomplete public download.
    with NamedTemporaryFile(dir=output.parent, prefix=".companion-", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        with zipfile.ZipFile(temp_path, "w", allowZip64=False) as archive:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, data)
        with zipfile.ZipFile(temp_path) as check:
            if check.namelist() != sorted(entries) or check.testzip() is not None:
                raise ValueError("ZIP integrity or reviewed asset list mismatch")
        digest = sha256(temp_path.read_bytes()).hexdigest()
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)

    # Independent checksum can be downloaded/compared without a private API.
    checksum = output.with_name(output.name + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reviewed MV3 companion ZIP")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    digest = make_zip(args.output)
    print(f"SmartPloy reviewed companion: {args.output.name} sha256={digest}")


if __name__ == "__main__":
    main()
