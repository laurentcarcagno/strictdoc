"""
Converts the RST fields of SDoc files to Markdown. A throw-away tool: it goes
away with docutils when the RST markup is removed from StrictDoc (the git tag
pre-markdown-only keeps it).

    python developer/tools/rst_to_markdown.py PATH [PATH ...]
        [--dry-run] [--report DIR] [--strict] [--force] [--verify]
        [--baseline FILE] [--suspect-fields TITLE,STATEMENT] [--text]

PATH is an .sdoc file or a folder. The tool changes the text of the multiline
fields (and of the STATEMENT, RATIONALE, COMMENT, DESCRIPTION and CONTENT
fields when they are on one line) of the documents that are in RST (without a
MARKUP option, or with MARKUP: RST), and writes MARKUP: Markdown in them. The
rest of the file is left as it is. A file whose text does not change and that
has no MARKUP: RST is not touched, so a second run changes nothing.

A document that another document includes (DOCUMENT_FROM_FILE) has the markup
of the document that includes it.

--dry-run   write nothing, only report
--report    a folder for conversion_report.md and conversion_report.json
--strict    exit with code 1 when anything could not be converted faithfully
--force     convert even when the Git working tree has changes in the paths
--verify    compare the words of every field before and after, and list the
            fields that differ
--baseline  the trace_baseline.json of the project (suspect links). The text of
            the parents changes with the conversion, so every link would turn
            suspect: the entries of the links that were reviewed take the hash
            of the converted parent. A link that was already suspect stays
            suspect. A trace_baseline.json in a folder that is given is used
            without this option.
--text      also convert the documents with MARKUP: Text (their text is
            escaped, and a new line is a hard break)
--suspect-fields  the fields of the hash, as the suspect_fields option of the
            project (default TITLE,STATEMENT)

Nothing is committed: one commit per document or per project is up to the
person who runs the tool.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

from strictdoc.backend.markdown.markdown_to_html_fragment_writer import (
    MarkdownToHtmlFragmentWriter,
)
from strictdoc.backend.rst.rst_to_markdown import RstToMarkdownConverter
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.features.hierarchy.suspect import (
    BASELINE_FILE_NAME,
    DEFAULT_SUSPECT_FIELDS,
    Baseline,
    content_hash,
)

_MULTILINE_START = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*): >>>[ \t]*$")
_SINGLE_LINE = re.compile(r"^([A-Z_]+): (\S.*)$")
_UID_LINE = re.compile(r"^UID: (\S+)")
_NODE_START = re.compile(r"^\[\[?/?[A-Z_]+\]?\]$")
_MARKUP_LINE = re.compile(r"^  MARKUP:[ \t]*(\S+)")
_INCLUDE = re.compile(
    r"^\[DOCUMENT_FROM_FILE\]\r?\nFILE: (.+?)\r?$", re.MULTILINE
)

# The fields that hold markup when they are on one line.
_SINGLE_LINE_FIELDS = {
    "STATEMENT",
    "RATIONALE",
    "COMMENT",
    "DESCRIPTION",
    "CONTENT",
}
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass
class FieldSpan:
    name: str
    # Indexes of the lines: the line of the name, and the line of "<<<" (the
    # same line for a field on one line).
    first: int
    last: int
    multiline: bool
    uid: str = ""


@dataclass
class FieldReport:
    path: str
    line: int
    uid: str
    name: str
    status: str  # converted | unchanged | differs
    warnings: List[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class FileReport:
    path: str
    status: str  # converted | unchanged | skipped
    reason: str = ""
    fields: List[FieldReport] = field(default_factory=list)


def scan_fields(lines: List[str]) -> List[FieldSpan]:
    spans: List[FieldSpan] = []
    uid = ""
    index = 0
    while index < len(lines):
        line = lines[index].rstrip("\r\n")
        if _NODE_START.match(line) is not None:
            uid = ""
        uid_match = _UID_LINE.match(line)
        if uid_match is not None:
            uid = uid_match.group(1)
        start = _MULTILINE_START.match(line)
        if start is not None:
            end = index + 1
            while end < len(lines) and lines[end].rstrip("\r\n") != "<<<":
                end += 1
            spans.append(FieldSpan(start.group(1), index, end, True, uid))
            index = end + 1
            continue
        single = _SINGLE_LINE.match(line)
        if single is not None and single.group(1) in _SINGLE_LINE_FIELDS:
            spans.append(FieldSpan(single.group(1), index, index, False, uid))
        index += 1
    return spans


def header_range(lines: List[str]) -> Optional[Tuple[int, int]]:
    """The lines of the [DOCUMENT] header, after "[DOCUMENT]"."""
    for index_, line_ in enumerate(lines):
        if line_.rstrip("\r\n") == "[DOCUMENT]":
            end = index_ + 1
            while end < len(lines):
                stripped = lines[end].rstrip("\r\n")
                if stripped == "" or stripped.startswith("["):
                    break
                end += 1
            return index_ + 1, end
    return None


def declared_markup(lines: List[str]) -> Optional[str]:
    bounds = header_range(lines)
    if bounds is None:
        return None
    for line_ in lines[bounds[0] : bounds[1]]:
        match = _MARKUP_LINE.match(line_.rstrip("\r\n"))
        if match is not None:
            return match.group(1)
    return None


def set_markup(lines: List[str], newline: str) -> List[str]:
    """The lines with MARKUP: Markdown in the options of the header."""
    bounds = header_range(lines)
    assert bounds is not None
    start, end = bounds
    new_line = f"  MARKUP: Markdown{newline}"
    result = list(lines)
    options_at: Optional[int] = None
    for index_ in range(start, end):
        if lines[index_].rstrip("\r\n") == "OPTIONS:":
            options_at = index_
    if options_at is None:
        block = [f"OPTIONS:{newline}", new_line]
        metadata_at = next(
            (
                index_
                for index_ in range(start, end)
                if lines[index_].rstrip("\r\n") == "METADATA:"
            ),
            end,
        )
        return result[:metadata_at] + block + result[metadata_at:]
    option_end = options_at + 1
    while option_end < end and lines[option_end].startswith("  "):
        option_end += 1
    for index_ in range(options_at + 1, option_end):
        if _MARKUP_LINE.match(lines[index_].rstrip("\r\n")) is not None:
            result[index_] = new_line
            return result
    # The writer puts MARKUP after ENABLE_MID and RELATION_FIELD.
    insert_at = options_at + 1
    for index_ in range(options_at + 1, option_end):
        if lines[index_].startswith(("  ENABLE_MID:", "  RELATION_FIELD:")):
            insert_at = index_ + 1
    return result[:insert_at] + [new_line] + result[insert_at:]


class _VisibleWords(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def words_of_markdown(markdown: str) -> List[str]:
    parser = _VisibleWords()
    parser.feed(str(MarkdownToHtmlFragmentWriter().write(markdown)))
    text = re.sub(r"\\tag\{\d+\}", " ", " ".join(parser.parts))
    return [word_.lower() for word_ in _WORD.findall(text)]


def words_of_rst(text: str) -> List[str]:
    text = re.sub(r"\\tag\{\d+\}", " ", text)
    return [word_.lower() for word_ in _WORD.findall(text)]


@dataclass
class LoadedFile:
    path: str
    lines: List[str]
    newline: str
    own_markup: Optional[str]
    parents: List[str] = field(default_factory=list)


def find_sdoc_files(paths: List[str]) -> List[str]:
    found: List[str] = []
    for path_ in paths:
        if os.path.isfile(path_):
            found.append(os.path.abspath(path_))
            continue
        for root_, dirs_, files_ in os.walk(path_):
            dirs_[:] = [
                dir_
                for dir_ in dirs_
                if dir_
                not in (".git", ".sandbox", "output", "build", "node_modules")
            ]
            for file_ in files_:
                if file_.endswith(".sdoc"):
                    found.append(os.path.abspath(os.path.join(root_, file_)))
    return sorted(set(found))


def load_files(paths: List[str]) -> Dict[str, LoadedFile]:
    loaded: Dict[str, LoadedFile] = {}
    for path_ in paths:
        with open(path_, encoding="utf8", newline="") as file_:
            text = file_.read()
        lines = text.splitlines(keepends=True)
        newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
        loaded[path_] = LoadedFile(
            path_, lines, newline, declared_markup(lines)
        )
    for file_ in loaded.values():
        text = "".join(file_.lines)
        for match_ in _INCLUDE.finditer(text):
            included = os.path.normpath(
                os.path.join(os.path.dirname(file_.path), match_.group(1))
            )
            if (
                included in loaded
                and file_.path not in loaded[included].parents
            ):
                loaded[included].parents.append(file_.path)
    return loaded


def effective_markup(
    loaded: Dict[str, LoadedFile], path: str, seen: Optional[List[str]] = None
) -> Optional[str]:
    """The markup of the file, or of the document that includes it."""
    seen = (seen or []) + [path]
    file_ = loaded[path]
    for parent_ in file_.parents:
        if parent_ not in seen:
            return effective_markup(loaded, parent_, seen)
    return file_.own_markup


def convert_file(
    file_: LoadedFile, verify: bool, plain_text: bool = False
) -> Tuple[List[str], FileReport, Counter]:  # type: ignore[type-arg]
    """The new lines of the file, and what was done."""
    spans = scan_fields(file_.lines)
    converter = RstToMarkdownConverter(base_dir=os.path.dirname(file_.path))
    constructs: Counter = Counter()  # type: ignore[type-arg]
    values: List[str] = []
    for span_ in spans:
        values.append(_value_of(file_.lines, span_))
    # Two passes: the equations are numbered in the order of the file, so a
    # reference to an equation of a later field finds its number.
    convert = converter.convert_plain_text if plain_text else converter.convert
    for value_ in values:
        convert(value_)
    report = FileReport(file_.path, "unchanged")
    replacements: List[Tuple[FieldSpan, str]] = []
    for span_, value_ in zip(spans, values):
        result = convert(value_)
        constructs.update(result.constructs)
        new_value = result.markdown.rstrip("\n")
        status = (
            "unchanged" if new_value == value_.rstrip("\n") else "converted"
        )
        detail = ""
        if verify and len(value_.strip()) > 0:
            old_words = words_of_rst(
                value_ if plain_text else converter.reference_text(value_)
            )
            new_words = words_of_markdown(new_value)
            if old_words != new_words:
                status = "differs"
                detail = _first_difference(old_words, new_words)
        report.fields.append(
            FieldReport(
                file_.path,
                span_.first + 1,
                span_.uid,
                span_.name,
                status,
                result.warnings,
                detail,
            )
        )
        if new_value != value_.rstrip("\n"):
            replacements.append((span_, new_value))
    lines = list(file_.lines)
    for span_, new_value in reversed(replacements):
        lines[span_.first : span_.last + 1] = _field_lines(
            span_, new_value, file_.newline
        )
    if len(replacements) > 0 or file_.own_markup in ("RST", "Text"):
        lines = set_markup(lines, file_.newline)
        report.status = "converted"
    return lines, report, constructs


def _value_of(lines: List[str], span: FieldSpan) -> str:
    if span.multiline:
        body = lines[span.first + 1 : span.last]
        return "".join(line_.rstrip("\r\n") + "\n" for line_ in body).rstrip(
            "\n"
        )
    return _SINGLE_LINE.match(lines[span.first].rstrip("\r\n")).group(2)  # type: ignore[union-attr]


def _field_lines(span: FieldSpan, value: str, newline: str) -> List[str]:
    if not span.multiline and "\n" not in value and value != "":
        return [f"{span.name}: {value}{newline}"]
    body = [line_ + newline for line_ in value.split("\n")]
    return [f"{span.name}: >>>{newline}", *body, f"<<<{newline}"]


def _first_difference(old: List[str], new: List[str]) -> str:
    for index_, (old_word, new_word) in enumerate(zip(old, new)):
        if old_word != new_word:
            return (
                f"word {index_}: '{old_word}' became '{new_word}' "
                f"({len(old)} words before, {len(new)} after)"
            )
    return f"{len(old)} words before, {len(new)} after"


def node_hashes(path: str, fields: List[str]) -> Dict[str, str]:
    """The hash of the reviewed content of every node of a file, by UID."""
    with open(path, encoding="utf8") as file_:
        document = SDReader.read(file_.read(), path)
    hashes: Dict[str, str] = {}
    iterator = SDocDocumentIterator(document=document, node_filter=None)
    for node_, _ in iterator.all_content(print_fragments=False):
        if isinstance(node_, SDocNode) and node_.reserved_uid:
            hashes[node_.reserved_uid] = content_hash(node_, fields)
    return hashes


def rebaseline(
    baseline: Baseline,
    old_hashes: Dict[str, str],
    new_hashes: Dict[str, str],
) -> Tuple[int, int]:
    """
    The entries of the reviewed links take the hash of the converted parent.
    Returns the number of entries that were updated and the number of links
    that stay suspect because they were suspect before.
    """
    updated = 0
    suspect = 0
    for key_, reviewed_ in list(baseline.entries.items()):
        parent = key_.rsplit(" < ", 1)[-1]
        if parent not in old_hashes or parent not in new_hashes:
            continue
        if reviewed_ == old_hashes[parent]:
            if new_hashes[parent] != reviewed_:
                baseline.entries[key_] = new_hashes[parent]
                updated += 1
        else:
            suspect += 1
    return updated, suspect


def git_is_clean(paths: List[str]) -> bool:
    try:
        output = subprocess.run(
            ["git", "status", "--porcelain", "--", *paths],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return True
    return output.strip() == ""


def write_report(
    folder: str,
    reports: List[FileReport],
    constructs: Counter,  # type: ignore[type-arg]
) -> None:
    os.makedirs(folder, exist_ok=True)
    converted = sum(
        1 for r_ in reports for f_ in r_.fields if f_.status == "converted"
    )
    unchanged = sum(
        1 for r_ in reports for f_ in r_.fields if f_.status == "unchanged"
    )
    differs = [
        f_ for r_ in reports for f_ in r_.fields if f_.status == "differs"
    ]
    warnings = [
        (f_, w_) for r_ in reports for f_ in r_.fields for w_ in f_.warnings
    ]
    document = {
        "files": [
            {
                "path": r_.path,
                "status": r_.status,
                "reason": r_.reason,
                "fields": [f_.__dict__ for f_ in r_.fields],
            }
            for r_ in reports
        ],
        "constructs": dict(constructs),
    }
    with open(
        os.path.join(folder, "conversion_report.json"), "w", encoding="utf8"
    ) as file_:
        json.dump(document, file_, indent=2, ensure_ascii=False)
    lines = [
        "# RST to Markdown conversion report",
        "",
        (
            f"- Files: {len(reports)} "
            f"({sum(1 for r_ in reports if r_.status == 'converted')} converted, "
            f"{sum(1 for r_ in reports if r_.status == 'unchanged')} unchanged, "
            f"{sum(1 for r_ in reports if r_.status == 'skipped')} skipped)"
        ),
        (
            f"- Fields: {converted} converted, {unchanged} unchanged, "
            f"{len(differs)} that differ"
        ),
        f"- Warnings: {len(warnings)}",
        "",
        "## Constructs",
        "",
    ]
    lines.extend(
        f"- {name_}: {count_}" for name_, count_ in constructs.most_common()
    )
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(
            f"- {f_.path}:{f_.line} {f_.uid or '-'} {f_.name}: {w_}"
            for f_, w_ in warnings
        )
    if differs:
        lines.extend(["", "## Fields that differ", ""])
        lines.extend(
            f"- {f_.path}:{f_.line} {f_.uid or '-'} {f_.name}: {f_.detail}"
            for f_ in differs
        )
    skipped = [r_ for r_ in reports if r_.status == "skipped"]
    if skipped:
        lines.extend(["", "## Skipped files", ""])
        lines.extend(f"- {r_.path}: {r_.reason}" for r_ in skipped)
    with open(
        os.path.join(folder, "conversion_report.md"), "w", encoding="utf8"
    ) as file_:
        file_.write("\n".join(lines) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--baseline")
    parser.add_argument(
        "--suspect-fields", default=",".join(DEFAULT_SUSPECT_FIELDS)
    )
    args = parser.parse_args(argv)
    suspect_fields = [f_.strip() for f_ in args.suspect_fields.split(",")]
    baseline_path = args.baseline
    if baseline_path is None:
        for path_ in args.paths:
            candidate = os.path.join(path_, BASELINE_FILE_NAME)
            if os.path.isfile(candidate):
                baseline_path = candidate

    if not args.dry_run and not args.force and not git_is_clean(args.paths):
        print(  # noqa: T201
            "error: the Git working tree has changes in these paths. Commit "
            "them, or use --force.",
            file=sys.stderr,
        )
        return 2

    files = load_files(find_sdoc_files(args.paths))
    reports: List[FileReport] = []
    constructs: Counter = Counter()  # type: ignore[type-arg]
    old_hashes: Dict[str, str] = {}
    converted_paths: List[str] = []
    for path_, file_ in files.items():
        markup = effective_markup(files, path_)
        convertible = (None, "RST", "Text") if args.text else (None, "RST")
        if markup not in convertible:
            reports.append(FileReport(path_, "skipped", f"MARKUP: {markup}"))
            continue
        lines, report, file_constructs = convert_file(
            file_, args.verify, plain_text=markup == "Text"
        )
        constructs.update(file_constructs)
        reports.append(report)
        if report.status == "converted" and not args.dry_run:
            if baseline_path is not None:
                old_hashes.update(node_hashes(path_, suspect_fields))
            with open(path_, "w", encoding="utf8", newline="") as output_:
                output_.write("".join(lines))
            converted_paths.append(path_)

    if baseline_path is not None and not args.dry_run:
        new_hashes: Dict[str, str] = {}
        for path_ in converted_paths:
            new_hashes.update(node_hashes(path_, suspect_fields))
        baseline = Baseline.load(baseline_path)
        updated, suspect = rebaseline(baseline, old_hashes, new_hashes)
        if updated > 0:
            baseline.save(baseline_path)
        print(  # noqa: T201
            f"Baseline {baseline_path}: {updated} links reviewed again, "
            f"{suspect} links that were suspect stay suspect."
        )
    if args.report:
        write_report(args.report, reports, constructs)
    converted_files = sum(1 for r_ in reports if r_.status == "converted")
    warnings = sum(len(f_.warnings) for r_ in reports for f_ in r_.fields)
    differing = sum(
        1 for r_ in reports for f_ in r_.fields if f_.status == "differs"
    )
    print(  # noqa: T201
        f"{len(reports)} files, {converted_files} converted, "
        f"{warnings} warnings, {differing} fields that differ"
        + (" (dry run)" if args.dry_run else "")
    )
    if args.strict and (warnings > 0 or differing > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
