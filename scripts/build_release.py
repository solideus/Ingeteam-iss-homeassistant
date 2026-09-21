"""Package the source tree as one installable ZIP, excluding local/test caches."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".venv"}


def main():
    manifest = json.loads(
        (ROOT / "custom_components/ingeteam_iss/manifest.json").read_text()
    )
    output = ROOT.parent / f"ingeteam_iss_{manifest['version']}.zip"
    # Refuse to overwrite an existing release artifact by mistake.
    with ZipFile(output, "x", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if (
                not path.is_file()
                or EXCLUDE.intersection(relative.parts)
                or path.suffix in {".pyc", ".zip"}
            ):
                continue
            archive.write(path, relative.as_posix())
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert "custom_components/ingeteam_iss/manifest.json" in archive.namelist()
    digest = hashlib.file_digest(output.open("rb"), "sha256").hexdigest()
    print(f"{output.name}: {output.stat().st_size} bytes; SHA-256 {digest}")


if __name__ == "__main__":
    main()
