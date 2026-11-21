# Development Plan

**Grammar**: strictdoc_24_development_plan.gra.md \
**Version**: Git commit: @GIT_VERSION, Git branch: @GIT_BRANCH \
**Date**: @GIT_COMMIT_DATETIME \
**Enable MID**: True \
**View style**: Narrative \
**Node in TOC**: True

**Type**: TEXT \
**MID**: 2ba509874f1744cf899643b58a6a2095

This document presents the goals of the StrictDoc project and describes how the
project is developed.

## Project goals

**Type**: SECTION \
**MID**: 24b0bc5efe074a419b441900d30b2876

**Type**: TEXT \
**MID**: bdbd5aecefdc41bca1c88b9bce71d512

StrictDoc is an open-source tool for writing technical documentation and
requirements management. The long-term goal of the project is to provide a
capable, open-source platform for creating and managing technical documentation.

**Requirements automation**

The tool aims to automate the requirements documentation process at various
levels.

**Target groups**

The project targets different user groups including those in software, hardware,
systems (systems engineering, electrical, thermal), as well as quality
assurance, safety, management, and non-technical areas.

**Use on individual computers and cloud**

The project is already usable on individual personal computer, the long-term
goal is to enable its use on cloud.

**Open data**

An important feature of StrictDoc is its focus on open data, ensuring ease of
data transfer both into and out of the system.

**Synergies with other tools**

StrictDoc shall be compatible with other software and engineering tools. This
includes at least the compatibility with the Python ecosystem, the model-based
systems engineering tools, such as Capella, and the formats providing Software
Bill of Materials, such as SPDX.

## Roadmap

**Type**: SECTION \
**MID**: 10fba42c4c444be89823d82944f7326f

**Type**: TEXT \
**MID**: ae3ab626e10a4aff9b7748bee75fd816

All StrictDoc work is tracked on GitHub via the
[StrictDoc issues](https://github.com/strictdoc-project/strictdoc/issues) and
[StrictDoc Pull Requests](https://github.com/strictdoc-project/strictdoc/pulls)
on GitHub.

As an open-source project, StrictDoc is developed without strict deadlines.
However, there are certain high-level priorities that influence its development.
In particular, features aligned with the core roadmap and those strongly
requested by active users are usually given the highest priority. StrictDoc also
benefits from contributions by users who want a particular feature and are
willing to develop it themselves.

### Project milestones

**Type**: SECTION \
**MID**: f1e3c17829fd4eebbd390fceaeb95619 \
**UID**: SECTION-DP-Project-milestones

**Type**: TEXT \
**MID**: fd9294fdd2b546de993f649767371394

The work is loosely organized in quarters which are maintained as
[GitHub milestones](https://github.com/strictdoc-project/strictdoc/milestones),
such as 2025-Q1, 2025-Q2, etc.

<table>
<thead>
<tr><th><strong>Quarter</strong></th><th><strong>Planned / accomplished work</strong></th></tr>
</thead>
<tbody>
<tr><td>2019-Q2</td><td>Pre-StrictDoc development in a fork of Doorstop.</td></tr>
<tr><td>2019-Q3</td><td>StrictDoc, first prototype. Markdown-based C++ program. Custom requirements metadata in YAML.</td></tr>
<tr><td>2020-Q1</td><td>The second prototype of StrictDoc based on RST/Sphinx. Using Sphinx extensions to manage meta information. First integration tests.</td></tr>
<tr><td>2020-Q2</td><td>StrictDoc created on GitHub. The code still uses RST for parsing requirements meta information and PySide for GUI.</td></tr>
<tr><td>2020-Q3</td><td>The RST parsing is replaced with a TextX-based DSL, new StrictDoc grammar is created. The PySide is replaced with a simple export to HTML using Jinja templates. Export to Sphinx HTML/PDF is introduced.</td></tr>
<tr><td>2020-Q4</td><td>Improvements in the styles of HTML/PDF exports. First Table, Traceability, and Deep Traceability screens.</td></tr>
<tr><td>2021-Q1</td><td>Excel export. The first implementation for forward and reverse traceability between SDoc and source files.</td></tr>
<tr><td>2021-Q2</td><td>Further work on the SDoc-source traceability.</td></tr>
<tr><td>2021-Q3</td><td>Further work on the SDoc-source traceability. Tree cycles detection, validations. MathJax support.</td></tr>
<tr><td>2021-Q4</td><td>Improvements of the traceability index generation and validation. Initial implementation of ReqIF. First support of custom grammars.</td></tr>
<tr><td>2022-Q1</td><td>Further work on ReqIF and custom grammars. Document fragments feature.</td></tr>
<tr><td>2022-Q2</td><td>Excel conversion improvements. Improvements of how meta information is displayed in HTML export.</td></tr>
<tr><td>2022-Q3</td><td>No work in this quarter.</td></tr>
<tr><td>2022-Q4</td><td>Installation using PyInstaller. The first prototype of a Web-based interface. First end-to-end Web tests using SeleniumBase. Improvements of the ReqIF support.</td></tr>
<tr><td>2023-Q1</td><td>Improvements of the Web-based interface towards first release. Improvements of the ReqIF support.</td></tr>
<tr><td>2023-Q2</td><td>Further stabilization of the Web interface. RST markup stability improvements. Work on StrictDoc's own requirements traceability.</td></tr>
<tr><td>2023-Q3</td><td>Anchors and incoming links. Improvements of the ReqIF interface. Work on StrictDoc's own requirements traceability. Mermaid diagramming tool. Reverse parent / child links. Project statistics screen. Performance improvements.</td></tr>
<tr><td>2023-Q4</td><td>Requirements relations and roles. UI improvements and stabilization. Further ReqIF work. Search engine and requirements filters. Project tree Diff/Changelog screens. Basic Git operations.</td></tr>
<tr><td>2024-Q1</td><td>Experimental SPDX support. JSON export. Custom views (static HTML). Basic traceability matrix screen.</td></tr>
<tr><td>2024-Q2</td><td>Includable/composable documents. FREETEXT-to-TEXT migration. ReqIF improvements.</td></tr>
<tr><td>2024-Q3</td><td>HTML2PDF improvements. ReqIF roundtrip for RELATION/ROLE. Consistent automatic escaping of Jinja templates. Passthrough-&gt;export command migration.</td></tr>
<tr><td>2024-Q4</td><td>Connecting requirements to functions (C, Python) and classes (Python) in source code. Support the linking in both directions independently: from requirements to source using RELATION/File and from source to requirements using @relation markers. LINK to documents.</td></tr>
<tr><td>2025-Q1</td><td>Connecting requirements to source code – further work. StrictDoc containerized in Docker. JUnit XML report generation.</td></tr>
<tr><td>2025-Q2</td><td>Gcov coverage justification report. SDoc node VERSIONs. External links.</td></tr>
<tr><td>2025-Q3</td><td>Static HTML search. Testing large documentation trees (100+ documents). Tree map visualization. Initial work for Ada support.</td></tr>
<tr><td>2025-Q4</td><td>Python file for StrictDoc configuration instead of TOML. Requirement validations and node constraints. Reading SDoc nodes from source files, e.g., <code>SPDX-*</code> identifiers.</td></tr>
<tr><td>2026-Q1</td><td>Parse Rust code. Preparing the server for concurrent use. WHAT-WHY-HOW tutorial. Markdown support. Static HTML search on server.</td></tr>
<tr><td>2026-Q2</td><td>Further Markdown work. Parse C macros. Table screen editing. Rust's cargo-nextest. Drag-and-drop image upload (WIP).</td></tr>
<tr><td>2026-Q3</td><td>Further Markdown work. Drag-and-drop image upload (WIP). Nix flake, migrate from Tox to uv. Lazy loading of documents. Moving nodes between sections/documents. Performance improvements for large documents.</td></tr>
</tbody>
</table>

### Roadmap diagram

**Type**: SECTION \
**MID**: bf9f3f05501140da8d35cde39493c72f

**Type**: TEXT \
**MID**: 53e101acb20e44e89de27f0f77c5f0cb

Additionally, a StrictDoc project maintains a high-level roadmap overview using
a draw.io diagram.

The diagram contains work items at both the epic and single-task levels. It
represents the already open StrictDoc GitHub issues, as well as some concepts in
the backlog that are yet to be worked on.

<img src="_assets/StrictDoc_Workspace-Roadmap.drawio.png" alt="Development plan diagram" width="100%" />

### Backlog

**Type**: SECTION \
**MID**: 0adcf781ba5b47b0b2e421db2fd97acb

**Type**: TEXT \
**MID**: 4c253eba99644f2dad971e0b0d79f143

StrictDoc maintains its backlog in a dedicated SDoc document (see
[LINK: SDOC_BACKLOG]), as well as among the GitHub issues specifically tracked
under the milestone
[Backlog](https://github.com/strictdoc-project/strictdoc/issues?q=is%3Aissue%20state%3Aopen%20milestone%3A20XX-Backlog).

### Backlog diagram

**Type**: SECTION \
**MID**: 21917df7f66d464a9d9a717def2e10db

**Type**: TEXT \
**MID**: c34b77865324416f98a36aa8bdb0fcaa

The following diagram contains the backlog work items at the epic and single
task levels.

<img src="_assets/StrictDoc_Workspace-Backlog.drawio.png" alt="StrictDoc Backlog" width="100%" />

## Versioning

**Type**: SECTION \
**MID**: 625560c790a3492eaf45466b787602d7

**Type**: TEXT \
**MID**: ae2a2af6e3f24f65845c6c37ea7da2e2

As of release 0.1.0 (2024-11-01), StrictDoc follows a
[semantic versioning](https://semver.org)-oriented release scheme. The
MAJOR.MINOR.PATCH components are managed according to the guidelines of the
semantic versioning specification.

## Quality

**Type**: SECTION \
**MID**: ef6bde37e1c54f49afdbd3c6785fd01c

**Type**: TEXT \
**MID**: 14d0e79fcadc43f1a1cee2d66ae6b763

StrictDoc's development incorporates quality measures to ensure a high standard
of code quality.

### Bug reporting and tracking

**Type**: SECTION \
**MID**: 185776da602c49589f9252b46a9ce663

**Type**: TEXT \
**MID**: a7874a49450448dfbfb557f9495f2b6e

StrictDoc provides an issue template for bug reports, which users can use to
report bugs and other issues.

All known bugs in StrictDoc are reported as GitHub issues and labeled with the
Bug tag:

[Known StrictDoc issues and bugs](https://github.com/strictdoc-project/strictdoc/issues?q=is%3Aissue%20state%3Aopen%20type%3ABug)

### Linting of code

**Type**: SECTION \
**MID**: bc49b1e28fff4386b3bf5788a6686a79

**Type**: TEXT \
**MID**: f6de78d4a95b4970ab55563e18472a92

StrictDoc uses [Ruff](https://docs.astral.sh/ruff/formatter/) to ensure
consistent code formatting and to check for common issues in Python code.

### Static analysis

**Type**: SECTION \
**MID**: 38ce17138405490b80e06037b40dc49d

**Type**: TEXT \
**MID**: ad63541e341d4648ab59b4a0817a7e3c

StrictDoc uses [mypy](https://github.com/python/mypy) to statically check the
robustness of its Python type system.

### Testing

**Type**: SECTION \
**MID**: 2834756354a7420499d0deecfe0ee9c4

**Type**: TEXT \
**MID**: ee541e7062704b3f919bcaac2bce2723

StrictDoc has three groups of tests: unit, integration, end-to-end tests.

The unit tests are based on [pytest](https://docs.pytest.org/en/stable/).

The integration tests are based on the
[LLVM Integrated Tester](https://llvm.org/docs/CommandGuide/lit.html) and
[FileCheck.py](https://github.com/mull-project/FileCheck.py/blob/main/pyproject.toml).
These tools are not very common, refer to
[How to test command-line programs with Python tools: LIT and FileCheck](https://stanislaw.github.io/2020-11-20-how-to-test-command-line-programs-with-python.html)
for a good description.

The end-to-end web interface tests are based on the
[SeleniumBase](https://seleniumbase.io/) test framework.

### Traceability between StrictDoc requirements, code, and tests

**Type**: SECTION \
**MID**: 2004550abd54486d9aa5f98282eef6e1

**Type**: TEXT \
**MID**: f829d28d2e3d4bcaa38f44ffb1ac0373

Most of StrictDoc's implemented features are tested through its own
documentation artifacts. In terms of traceability, StrictDoc maintains a growing
number of trace links between:

- Documentation and source files
- Source files and tests
- Tests, test results, and code coverage data

The goal is to achieve 100% traceability across all artifacts in the StrictDoc
codebase.

### Continuous integration (CI)

**Type**: SECTION \
**MID**: 30b874ab3eac4d429633537e1e89677f

**Type**: TEXT \
**MID**: 85e3915270f144c7a76ccfa0e088d93d

Contributions to StrictDoc are made through GitHub pull requests. Each pull
request is validated by a series of checks and test jobs run on GitHub Actions
CI servers.

## Python baseline

**Type**: SECTION \
**MID**: 2ae3a8822a424a9e8ad6976c2476d109

**Type**: TEXT \
**MID**: 081ee6266bab4a3a80f290c95e055a25

The supported version of Python is kept to be as low as possible. As of 2025-Q4,
the currently supported version is Python 3.10.

Ideally, the lowest Python version should only be raised when it is consistently
deprecated by the major software platforms like Ubuntu or GitHub Actions.

Another reason for upgrading the minimum Python version is due to the upstream
dependencies. As these dependencies stop supporting the older versions of
Python, StrictDoc must be upgraded to maintain compatibility. With the existing
dependency graph, this happens rather infrequently as most dependencies also
maintain the compatibility with the older Python versions.
