#!/usr/bin/env python3
"""
Copies the working tree mounted at /src into /strictdoc, the folder where the
tests run. The copy has the files that git knows (tracked or new, not
ignored), so build/ stays out. Its texts have the line endings of the
repository: a Windows checkout has CRLF, which the Linux tests do not expect.
Its files have the mode of the index: a Windows mount shows every file as
executable. .git is a link to the repository, not a copy.

    snapshot.py /src /strictdoc
"""

import os
import shutil
import subprocess
import sys


def git_output(source: str, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=source,
        check=True,
        capture_output=True,
    ).stdout.decode("utf8")


def main() -> None:
    source, target = sys.argv[1], sys.argv[2]

    # "100755 <hash> <stage><TAB>path"
    executables = set()
    for record_ in git_output(source, "ls-files", "--stage", "-z").split("\0"):
        if record_.startswith("100755 "):
            executables.add(record_.split("\t", 1)[1])

    listing = git_output(
        source,
        "ls-files",
        "--eol",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    )
    copied = converted = 0
    seen = set()
    for record_ in listing.split("\0"):
        if not record_:
            continue
        # "i/lf    w/crlf  attr/    <TAB>path"
        flags, path = record_.split("\t", 1)
        if path in seen:
            continue
        seen.add(path)
        source_path = os.path.join(source, path)
        # A file deleted in the working tree is still in the index.
        if not os.path.isfile(source_path):
            continue
        target_path = os.path.join(target, path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        index_eol, worktree_eol = flags.split()[:2]
        if worktree_eol == "w/crlf" and index_eol != "i/crlf":
            with open(source_path, "rb") as file_:
                content = file_.read()
            with open(target_path, "wb") as file_:
                file_.write(content.replace(b"\r\n", b"\n"))
            converted += 1
        else:
            shutil.copyfile(source_path, target_path)
        os.chmod(target_path, 0o755 if path in executables else 0o644)
        copied += 1

    # The Git information that StrictDoc shows (branch, date of the last
    # commit) comes from the repository, read-only like the rest of /src.
    git_link = os.path.join(target, ".git")
    if not os.path.lexists(git_link):
        os.symlink(os.path.join(source, ".git"), git_link)
    print(  # noqa: T201
        f"snapshot: {copied} files copied, {converted} with CRLF made LF"
    )


if __name__ == "__main__":
    main()
