"""
Converts SDoc documents (.sdoc) to the native Markdown format (.md, and .gra.md
for a grammar that is written inside the document). See
developer/design/plan_markdown_natif.md.

    python developer/tools/sdoc_to_markdown.py PATH [PATH ...]
        [--output-dir DIR | --in-place] [--rename-only] [--check]
        [--strict] [--dry-run] [--baseline FILE] [--suspect-fields A,B]
        [--exclude PATTERN ...] [--root DIR]

PATH is an .sdoc file or a folder. A file with the extension .md that still
holds SDoc syntax (a first line [DOCUMENT]) is converted too: that is what
--rename-only leaves.

--output-dir  write the converted files in DIR, with the same relative paths
--in-place    write the converted files next to the sources and remove the
              .sdoc files (git rm when the folder is a Git work tree)
--rename-only with --in-place: only rename x.sdoc to x.md (git mv), without
              converting, so that the rename and the conversion can be two
              commits that Git follows
--check       convert into a staging folder first, read it back with StrictDoc
              and compare the two trees (documents, nodes, fields, relations).
              Nothing is written when they differ, unless --force is given
--force       write even if --check finds differences
--strict      exit with code 1 when a document is skipped, a warning is
              raised or --check finds differences
--dry-run     write nothing, only report
--exclude     a pattern (fnmatch) of the paths, relative to the root, of
              documents to leave as they are. Can be given several times
--root        the folder that StrictDoc reads for --check, when the documents
              to convert are only a part of it (default: the first PATH).
              The paths of --exclude, of the report and of the baseline are
              relative to it
--baseline    the trace_baseline.json of the project (suspect links). The text
              of a field is not the same string in Markdown, so every parent
              would look changed: the entries of the links that were reviewed
              take the hash of the converted parent. A link that was already
              suspect stays suspect. A trace_baseline.json in the given folder
              is used without this option.
--suspect-fields  the fields of the hash, as the suspect_fields option of the
              project (default TITLE,STATEMENT)

Not converted, and left as they are: a document that includes another one
(DOCUMENT_FROM_FILE) and the documents it includes, a document with a grammar
imported from an .sgra file, a document with MARKUP: HTML. The report says which.

Lost on purpose (a warning is raised): the option RELATION_FIELD and the MID of
the document. A document with MARKUP: HTML is not converted. The other options
(ROOT, ENABLE_MID, AUTO_LEVELS, LAYOUT, VIEW_STYLE, NODE_IN_TOC, DEFAULT_VIEW)
are keys of the metadata block of the Markdown document.

Nothing is committed: one commit per document or per project is up to the
person who runs the tool.
"""

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from strictdoc.backend.markdown.reader import SDMarkdownReader
from strictdoc.backend.markdown.writer import (
    MarkdownGrammarWriter,
    SDMarkdownWriter,
)
from strictdoc.backend.sdoc.models.document_from_file import DocumentFromFile
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.features.hierarchy.suspect import (
    BASELINE_FILE_NAME,
    DEFAULT_SUSPECT_FIELDS,
    Baseline,
    content_hash,
)

_FENCE_PATTERN = re.compile(r"^(`{3,}|~{3,})")


@dataclass
class Conversion:
    """The result of the conversion of one document."""

    source: str
    document_markdown: Optional[str] = None
    grammar_markdown: Optional[str] = None
    grammar_file_name: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    skipped_reason: Optional[str] = None
    title: Optional[str] = None
    # The hash of the reviewed content of each node with a UID, by UID, before
    # and after the conversion (see --baseline).
    old_hashes: Dict[str, str] = field(default_factory=dict)
    new_hashes: Dict[str, str] = field(default_factory=dict)


def convert_text(
    text: str,
    source: str,
    suspect_fields: Optional[Sequence[str]] = None,
) -> Conversion:
    """
    Converts the text of one SDoc document. With `suspect_fields`, the hashes
    of the reviewed content of its nodes are computed before and after.
    """
    conversion = Conversion(source=source)
    stem = os.path.splitext(os.path.basename(source))[0]

    document = SDReader().read(text, file_path=source)
    conversion.title = document.title

    if len(_included_files(document)) > 0:
        conversion.skipped_reason = (
            "includes another document (DOCUMENT_FROM_FILE)"
        )
        return conversion

    if document.config.markup == "HTML":
        conversion.skipped_reason = (
            "its fields are in HTML (MARKUP: HTML), which the Markdown format "
            "has no option for"
        )
        return conversion

    grammar = document.grammar
    if grammar is not None and grammar.import_from_file is not None:
        if grammar.import_from_file.endswith(".sgra"):
            conversion.skipped_reason = (
                "its grammar is imported from an .sgra file "
                f"({grammar.import_from_file})"
            )
            return conversion
    elif grammar is not None and not grammar.is_default:
        conversion.grammar_file_name = stem + ".gra.md"
        conversion.grammar_markdown = MarkdownGrammarWriter.write(grammar)
        grammar.import_from_file = conversion.grammar_file_name

    conversion.warnings.extend(_lost_options(document))

    if suspect_fields is not None:
        conversion.old_hashes = _node_hashes(document, suspect_fields)

    markdown = SDMarkdownWriter.write(document)
    conversion.document_markdown = collapse_blank_lines(markdown)

    if suspect_fields is not None:
        converted = SDMarkdownReader().read(
            conversion.document_markdown, file_path=source
        )
        conversion.new_hashes = _node_hashes(converted, suspect_fields)
    return conversion


def _node_hashes(document: Any, fields: Sequence[str]) -> Dict[str, str]:
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
    The text of a field is not the same string in Markdown (a line end more or
    less), so the hash of every converted parent changes and every reviewed
    link would turn suspect. The entries of the links that were reviewed take
    the hash of the converted parent. Returns the number of entries updated
    and the number of links that stay suspect because they were suspect
    before.
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


def collapse_blank_lines(markdown: str) -> str:
    """
    Two blank lines in a row are an error in a Markdown document, outside of
    fenced code. SDoc fields may have them.
    """
    result: List[str] = []
    fence: Optional[str] = None
    previous_blank = False
    for line in markdown.split("\n"):
        fence_match = _FENCE_PATTERN.match(line)
        if fence_match is not None:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
        blank = len(line.strip()) == 0
        if fence is None and blank and previous_blank:
            continue
        previous_blank = blank and fence is None
        result.append(line)
    return "\n".join(result)


def _lost_options(document: Any) -> List[str]:
    """
    The options of the document that the Markdown metadata block has no key
    for (SDOC-MD-39 lists the ones it has).
    """
    lost: List[str] = []
    if document.config.relation_field is not None:
        lost.append(
            f"option RELATION_FIELD: {document.config.relation_field} is lost"
        )
    return lost


def find_documents(paths: List[str]) -> List[str]:
    """The .sdoc files, and the .md files that hold SDoc syntax."""
    found: List[str] = []
    for path in paths:
        if os.path.isfile(path):
            found.append(os.path.abspath(path))
            continue
        for directory, directory_names, file_names in os.walk(path):
            directory_names[:] = sorted(
                name_
                for name_ in directory_names
                if name_ not in (".git", "output", "build", "node_modules")
            )
            for file_name in sorted(file_names):
                full_path = os.path.join(directory, file_name)
                if file_name.endswith(".sdoc") or _is_sdoc_in_md(full_path):
                    found.append(os.path.abspath(full_path))
    return found


def _is_sdoc_in_md(path: str) -> bool:
    if not path.endswith(".md") or path.endswith(".gra.md"):
        return False
    with open(path, encoding="utf8") as file_:
        return file_.readline().strip() == "[DOCUMENT]"


def _included_files(document: Any) -> List[str]:
    """The files that a document includes (an example in a code block is not)."""
    found: List[str] = []

    def walk(section_contents: List[Any]) -> None:
        for node_ in section_contents:
            if isinstance(node_, DocumentFromFile):
                found.append(node_.file)
            else:
                walk(getattr(node_, "section_contents", None) or [])

    walk(document.section_contents)
    return found


def _included_documents(documents: List[str]) -> Set[str]:
    """The documents that others include: they stay as they are."""
    included: Set[str] = set()
    for path in documents:
        with open(path, encoding="utf8") as file_:
            text = file_.read()
        if "[DOCUMENT_FROM_FILE]" not in text:
            continue
        for name in _included_files(SDReader().read(text, file_path=path)):
            for candidate in documents:
                if candidate.endswith(os.sep + name.replace("/", os.sep)):
                    included.add(candidate)
    return included


def _git_root(path: str) -> Optional[str]:
    directory = path if os.path.isdir(path) else os.path.dirname(path)
    result = subprocess.run(
        ["git", "-C", directory, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _move(source: str, target: str) -> None:
    root = _git_root(source)
    if root is not None:
        tracked = subprocess.run(
            ["git", "-C", root, "ls-files", "--error-unmatch", source],
            capture_output=True,
            check=False,
        )
        if tracked.returncode == 0:
            subprocess.run(
                ["git", "-C", root, "mv", source, target], check=True
            )
            return
    os.rename(source, target)


def _remove(path: str) -> None:
    root = _git_root(path)
    if root is not None:
        tracked = subprocess.run(
            ["git", "-C", root, "ls-files", "--error-unmatch", path],
            capture_output=True,
            check=False,
        )
        if tracked.returncode == 0:
            subprocess.run(["git", "-C", root, "rm", "-q", path], check=True)
            return
    os.remove(path)


def _target_paths(source: str) -> Tuple[str, str]:
    stem = os.path.splitext(source)[0]
    return stem + ".md", stem + ".gra.md"


def _export_json(folder: str, output: str) -> Dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "strictdoc.cli.main",
            "export",
            folder,
            "--formats=json",
            "--output-dir",
            output,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error_lines = [
            line_
            for line_ in (result.stdout + result.stderr).splitlines()
            if "rror" in line_
        ]
        raise RuntimeError(
            f"strictdoc could not read {folder}: " + " | ".join(error_lines[:3])
        )
    with open(os.path.join(output, "json", "index.json"), encoding="utf8") as f:
        loaded: Dict[str, Any] = json.load(f)
    return loaded


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, list):
        return [_normalize(item_) for item_ in value]
    if isinstance(value, dict):
        return {
            key_: _normalize(item_)
            for key_, item_ in value.items()
            if key_ not in ("_TOC", "FORMAT")
        }
    return value


def _iterate(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The nodes themselves, children after their parent."""
    found: List[Dict[str, Any]] = []
    for node in nodes:
        found.append(node)
        found.extend(_iterate(node.get("NODES", [])))
    return found


def _flatten(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    The nodes in document order, each with the place of its parent in the list:
    a TEXT that follows the subsections of a section is a child of the section
    in SDoc, and a child of the last subsection in Markdown.
    """
    flat: List[Dict[str, Any]] = []

    def walk(children: List[Dict[str, Any]], parent: int) -> None:
        for node in children:
            entry = {k_: v_ for k_, v_ in node.items() if k_ != "NODES"}
            entry["_PARENT"] = parent
            flat.append(entry)
            walk(node.get("NODES", []), len(flat) - 1)

    walk(nodes, -1)
    return flat


def compare_trees(
    source_json: Dict[str, Any],
    target_json: Dict[str, Any],
    titles: Optional[Set[str]] = None,
) -> List[str]:
    """
    The differences between two JSON exports, as sentences. With `titles`,
    only the documents of these titles are compared: the machine identifiers
    that StrictDoc makes up for a document that is left as it is change with
    every run.
    """
    differences: List[str] = []
    source_documents = {
        d_["TITLE"]: d_
        for d_ in source_json["DOCUMENTS"]
        if titles is None or d_["TITLE"] in titles
    }
    target_documents = {
        d_["TITLE"]: d_
        for d_ in target_json["DOCUMENTS"]
        if titles is None or d_["TITLE"] in titles
    }
    for title in sorted(set(source_documents) - set(target_documents)):
        differences.append(
            f"document {title!r} is missing after the conversion"
        )
    for title in sorted(set(target_documents) - set(source_documents)):
        differences.append(f"document {title!r} appears after the conversion")
    for title in sorted(set(source_documents) & set(target_documents)):
        for key_ in ("ROOT", "VERSION", "CLASSIFICATION", "PREFIX"):
            if source_documents[title].get(key_) != target_documents[title].get(
                key_
            ):
                differences.append(f"{title}: the document key {key_} differs")
        options_before = {
            k_: v_
            for k_, v_ in source_documents[title].get("_OPTIONS", {}).items()
            if k_ != "MARKUP"
        }
        options_after = {
            k_: v_
            for k_, v_ in target_documents[title].get("_OPTIONS", {}).items()
            if k_ != "MARKUP"
        }
        if options_before != options_after:
            differences.append(
                f"{title}: the options differ: {options_before} before, "
                f"{options_after} after"
            )
        source_nodes = _flatten(source_documents[title].get("NODES", []))
        target_nodes = _flatten(target_documents[title].get("NODES", []))
        if len(source_nodes) != len(target_nodes):
            differences.append(
                f"{title}: {len(source_nodes)} nodes before, "
                f"{len(target_nodes)} after"
            )
            continue
        for index_, (before, after) in enumerate(
            zip(source_nodes, target_nodes)
        ):
            before_n, after_n = _normalize(before), _normalize(after)
            if before_n == after_n:
                continue
            names = sorted(
                key_
                for key_ in set(before_n) | set(after_n)
                if before_n.get(key_) != after_n.get(key_)
            )
            label = before.get("UID") or before.get("TITLE") or f"node {index_}"
            differences.append(
                f"{title}: {label}: the field(s) {', '.join(names)} differ"
            )
    return differences


def _drop_volatile_mids(
    first: List[Dict[str, Any]],
    second: List[Dict[str, Any]],
    other: List[Dict[str, Any]],
) -> None:
    """
    StrictDoc makes up a MID for each node that has none, and a different one
    at each run. Where the two exports of the source disagree, the MID is not
    stored in the file: leave it out of the comparison.
    """
    for node_first, node_second in zip(first, second):
        if node_first.get("MID") != node_second.get("MID"):
            node_first.pop("MID", None)
            node_second.pop("MID", None)
    for node_first, node_other in zip(first, other):
        if "MID" not in node_first:
            node_other.pop("MID", None)


def check_conversion(
    source_root: str, staging: str, titles: Optional[Set[str]] = None
) -> List[str]:
    """Reads the source tree and the staged tree with StrictDoc, and compares."""
    with tempfile.TemporaryDirectory() as work:
        before = _export_json(source_root, os.path.join(work, "before"))
        again = _export_json(source_root, os.path.join(work, "again"))
        after = _export_json(staging, os.path.join(work, "after"))
    documents_again = {d_["TITLE"]: d_ for d_ in again["DOCUMENTS"]}
    documents_after = {d_["TITLE"]: d_ for d_ in after["DOCUMENTS"]}
    for document in before["DOCUMENTS"]:
        title = document["TITLE"]
        if title in documents_again and title in documents_after:
            _drop_volatile_mids(
                _iterate(document.get("NODES", [])),
                _iterate(documents_again[title].get("NODES", [])),
                _iterate(documents_after[title].get("NODES", [])),
            )
    return compare_trees(before, after, titles)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sdoc_to_markdown.py", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--output-dir")
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--rename-only", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root")
    parser.add_argument("--baseline")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument(
        "--suspect-fields", default=",".join(DEFAULT_SUSPECT_FIELDS)
    )
    arguments = parser.parse_args(argv)

    if arguments.rename_only and not arguments.in_place:
        parser.error("--rename-only needs --in-place")
    if arguments.output_dir is None and not arguments.in_place:
        parser.error("give --output-dir or --in-place")
    if arguments.output_dir is not None and arguments.in_place:
        parser.error("--output-dir and --in-place exclude each other")

    documents = find_documents(arguments.paths)
    if len(documents) == 0:
        print("No SDoc document found.")  # noqa: T201
        return 0
    source_root = os.path.abspath(arguments.root or arguments.paths[0])
    if os.path.isfile(source_root):
        source_root = os.path.dirname(source_root)

    included = _included_documents(documents)

    if arguments.rename_only:
        for source in documents:
            relative = os.path.relpath(source, source_root)
            if not source.endswith(".sdoc"):
                continue
            skipped = _skip_reason(source, relative, included, arguments)
            if skipped is not None:
                print(f"skip {relative}: {skipped}")  # noqa: T201
                continue
            target = os.path.splitext(source)[0] + ".md"
            print(f"rename {relative} -> {os.path.basename(target)}")  # noqa: T201
            if not arguments.dry_run:
                _move(source, target)
        return 0

    suspect_fields = [
        name_.strip() for name_ in arguments.suspect_fields.split(",")
    ]
    baseline_path: Optional[str] = arguments.baseline
    if baseline_path is None:
        candidate = os.path.join(source_root, BASELINE_FILE_NAME)
        if os.path.isfile(candidate):
            baseline_path = candidate

    problems = 0
    converted: List[Tuple[str, Conversion]] = []
    for source in documents:
        relative = os.path.relpath(source, source_root)
        skipped = _skip_reason(source, relative, included, arguments)
        if skipped is not None:
            print(f"skip {relative}: {skipped}")  # noqa: T201
            if skipped != "excluded":
                problems += 1
            continue
        with open(source, encoding="utf8") as file_:
            conversion = convert_text(
                file_.read(),
                source,
                suspect_fields if baseline_path is not None else None,
            )
        if conversion.skipped_reason is not None:
            print(f"skip {relative}: {conversion.skipped_reason}")  # noqa: T201
            problems += 1
            continue
        for warning in conversion.warnings:
            print(f"warning {relative}: {warning}")  # noqa: T201
            problems += 1
        converted.append((source, conversion))

    with tempfile.TemporaryDirectory() as staging:
        # The staging folder is the whole tree, so that the documents that are
        # not converted stay in it and the links between documents resolve.
        shutil.copytree(
            source_root,
            staging,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".git", "output", "build", "node_modules", "__pycache__"
            ),
        )
        for source, conversion in converted:
            relative = os.path.relpath(source, source_root)
            os.remove(os.path.join(staging, relative))
            document_path, grammar_path = _target_paths(
                os.path.join(staging, relative)
            )
            os.makedirs(os.path.dirname(document_path), exist_ok=True)
            assert conversion.document_markdown is not None
            with open(document_path, "w", encoding="utf8") as file_:
                file_.write(conversion.document_markdown)
            if conversion.grammar_markdown is not None:
                with open(grammar_path, "w", encoding="utf8") as file_:
                    file_.write(conversion.grammar_markdown)

        if arguments.check:
            reading_root = _reading_root(source_root, converted)
            try:
                differences = check_conversion(
                    reading_root,
                    staging,
                    {c_.title for _, c_ in converted if c_.title is not None},
                )
            except RuntimeError as error_:
                differences = [str(error_)]
            finally:
                if reading_root != source_root:
                    shutil.rmtree(reading_root, ignore_errors=True)
            for difference in differences:
                print(f"difference {difference}")  # noqa: T201
            if len(differences) == 0:
                print("check: the converted tree reads as the same tree")  # noqa: T201
            else:
                problems += 1
                if not arguments.force:
                    print("Nothing written: --force writes anyway.")  # noqa: T201
                    return 1

        if arguments.dry_run:
            print(f"{len(converted)} document(s) would be converted.")  # noqa: T201
            return 1 if arguments.strict and problems > 0 else 0

        for source, conversion in converted:
            relative = os.path.relpath(source, source_root)
            document_staged, grammar_staged = _target_paths(
                os.path.join(staging, relative)
            )
            if arguments.in_place:
                document_target, grammar_target = _target_paths(source)
            else:
                document_target, grammar_target = _target_paths(
                    os.path.join(arguments.output_dir, relative)
                )
            os.makedirs(os.path.dirname(document_target), exist_ok=True)
            shutil.copyfile(document_staged, document_target)
            if conversion.grammar_markdown is not None:
                shutil.copyfile(grammar_staged, grammar_target)
            if arguments.in_place and document_target != source:
                _remove(source)
            print(f"converted {relative}")  # noqa: T201

        if baseline_path is not None:
            target_baseline = (
                baseline_path
                if arguments.in_place
                else os.path.join(
                    arguments.output_dir,
                    os.path.relpath(baseline_path, source_root),
                )
            )
            _rebaseline_file(baseline_path, target_baseline, converted)

    return 1 if arguments.strict and problems > 0 else 0


def _rebaseline_file(
    baseline_path: str,
    target_path: str,
    converted: List[Tuple[str, Conversion]],
) -> None:
    old_hashes: Dict[str, str] = {}
    new_hashes: Dict[str, str] = {}
    for _, conversion in converted:
        old_hashes.update(conversion.old_hashes)
        new_hashes.update(conversion.new_hashes)
    baseline = Baseline.load(baseline_path)
    updated, suspect = rebaseline(baseline, old_hashes, new_hashes)
    if updated > 0 or target_path != baseline_path:
        os.makedirs(
            os.path.dirname(os.path.abspath(target_path)), exist_ok=True
        )
        baseline.save(target_path)
    print(  # noqa: T201
        f"Baseline {target_path}: {updated} links reviewed again, "
        f"{suspect} links that were suspect stay suspect."
    )


def _skip_reason(
    source: str,
    relative: str,
    included: Set[str],
    arguments: argparse.Namespace,
) -> Optional[str]:
    """Why a document stays as it is, before any conversion."""
    if any(
        fnmatch.fnmatch(relative, pattern_) for pattern_ in arguments.exclude
    ):
        return "excluded"
    if source in included:
        return "another document includes it"
    if arguments.rename_only:
        with open(source, encoding="utf8") as file_:
            return convert_text(file_.read(), source).skipped_reason
    return None


def _reading_root(
    source_root: str, converted: List[Tuple[str, Conversion]]
) -> str:
    """
    The folder that StrictDoc reads as "before". A document that --rename-only
    renamed to .md still holds SDoc syntax: StrictDoc reads it as a copy where
    it is an .sdoc again.
    """
    renamed = [source for source, _ in converted if source.endswith(".md")]
    if len(renamed) == 0:
        return source_root
    before = tempfile.mkdtemp()
    shutil.copytree(
        source_root,
        before,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            ".git", "output", "build", "node_modules", "__pycache__"
        ),
    )
    for source in renamed:
        copied = os.path.join(before, os.path.relpath(source, source_root))
        os.rename(copied, os.path.splitext(copied)[0] + ".sdoc")
    return before


if __name__ == "__main__":
    sys.exit(main())
