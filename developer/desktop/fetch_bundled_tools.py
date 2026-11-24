"""
Download the tools that the package of the desktop application embeds.

The script reads bundled_tools.json, downloads each archive of a platform,
checks its SHA-256 sum before any extraction, and extracts it in
<target>/tools/<name>/. A wrong sum stops the script with a non-zero exit code
and nothing is extracted.

The download cache is a folder given with --cache-dir, or a temporary folder
that the script deletes at the end. It is never in the profile of the user.

@relation(SDOC-SRS-1257, scope=file)
@relation(SDOC-SRS-1258, scope=file)
"""

import argparse
import hashlib
import json
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

MANIFEST_PATH = Path(__file__).resolve().parent / "bundled_tools.json"
PLATFORMS = ("linux64", "win64")
_CHUNK_SIZE = 1024 * 1024
_TIMEOUT_SECONDS = 120


class FetchError(Exception):
    pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the tools embedded in the desktop package."
    )
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    arguments = parser.parse_args(argv)
    try:
        if arguments.cache_dir is not None:
            fetch_tools(
                manifest_path=arguments.manifest,
                platform=arguments.platform,
                target=arguments.target,
                cache_dir=arguments.cache_dir,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="bundled_tools_") as dir_:
                fetch_tools(
                    manifest_path=arguments.manifest,
                    platform=arguments.platform,
                    target=arguments.target,
                    cache_dir=Path(dir_),
                )
    except FetchError as exception_:
        print(f"error: {exception_}", file=sys.stderr)  # noqa: T201
        return 1
    return 0


def fetch_tools(
    *, manifest_path: Path, platform: str, target: Path, cache_dir: Path
) -> None:
    tools = load_tools(manifest_path, platform)
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Every sum is checked before the first extraction: a wrong one leaves
    # the target as it was.
    archives = [(tool_, download_archive(tool_, cache_dir)) for tool_ in tools]
    for tool_, archive_path in archives:
        extract_archive(tool_, archive_path, target)
        print(  # noqa: T201
            f"{tool_['name']} {tool_['version']}: extracted in "
            f"{target / 'tools' / tool_['name']}"
        )


def load_tools(manifest_path: Path, platform: str) -> List[Dict[str, Any]]:
    with manifest_path.open(encoding="utf8") as file_:
        manifest = json.load(file_)
    tools = manifest["platforms"].get(platform)
    if tools is None:
        raise FetchError(f"no tool for the platform {platform}.")
    return list(tools)


def download_archive(tool: Dict[str, Any], cache_dir: Path) -> Path:
    """Return the cached archive of the tool, whose sum is the expected one."""
    archive_path = cache_dir / PurePosixPath(tool["url"]).name
    if archive_path.exists() and compute_sha256(archive_path) == tool["sha256"]:
        return archive_path
    partial_path = archive_path.with_name(archive_path.name + ".part")
    print(f"{tool['name']}: downloading {tool['url']}")  # noqa: T201
    try:
        with urllib.request.urlopen(  # noqa: S310
            tool["url"], timeout=_TIMEOUT_SECONDS
        ) as response:
            with partial_path.open("wb") as file_:
                shutil.copyfileobj(response, file_, _CHUNK_SIZE)
    except OSError as exception_:
        partial_path.unlink(missing_ok=True)
        raise FetchError(
            f"{tool['name']}: download failed: {exception_}"
        ) from exception_
    actual_sum = compute_sha256(partial_path)
    if actual_sum != tool["sha256"]:
        partial_path.unlink()
        raise FetchError(
            f"{tool['name']}: wrong SHA-256 sum {actual_sum}, expected "
            f"{tool['sha256']}. Nothing is extracted."
        )
    partial_path.replace(archive_path)
    return archive_path


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_:
        for chunk_ in iter(lambda: file_.read(_CHUNK_SIZE), b""):
            digest.update(chunk_)
    return digest.hexdigest()


def extract_archive(
    tool: Dict[str, Any], archive_path: Path, target: Path
) -> None:
    """Extract a zip archive, whose sum is already checked, in tools/<name>."""
    strip = int(tool["strip_components"])
    destination = target / "tools" / tool["name"]
    staging = target / "tools" / f".{tool['name']}.staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info_ in archive.infolist():
                parts = PurePosixPath(info_.filename).parts[strip:]
                if len(parts) == 0:
                    continue
                if ".." in parts or PurePosixPath(info_.filename).is_absolute():
                    raise FetchError(
                        f"{tool['name']}: unsafe path in the archive: "
                        f"{info_.filename}"
                    )
                output_path = staging.joinpath(*parts)
                if info_.is_dir():
                    output_path.mkdir(parents=True, exist_ok=True)
                    continue
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info_) as source_:
                    with output_path.open("wb") as file_:
                        shutil.copyfileobj(source_, file_, _CHUNK_SIZE)
                mode = info_.external_attr >> 16
                if stat.S_IMODE(mode) != 0:
                    output_path.chmod(stat.S_IMODE(mode))
        shutil.rmtree(destination, ignore_errors=True)
        staging.replace(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
