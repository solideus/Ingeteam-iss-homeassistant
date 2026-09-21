"""Set real GitHub metadata locally when the repository is chosen; no network calls."""

import argparse
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", help="Actual GitHub owner/repository")
    parser.add_argument(
        "--maintainer", required=True, help="Actual GitHub username, without @"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Expected owner/repository")
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.maintainer):
        parser.error("Expected a GitHub username without @")
    root = Path(__file__).resolve().parents[1]
    path = root / "custom_components/ingeteam_iss/manifest.json"
    manifest = json.loads(path.read_text())
    url = f"https://github.com/{args.repository}"
    manifest.update(
        documentation=url,
        issue_tracker=f"{url}/issues",
        codeowners=[f"@{args.maintainer}"],
    )
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print("Updated manifest.json. No repository was created or published.")


if __name__ == "__main__":
    main()
