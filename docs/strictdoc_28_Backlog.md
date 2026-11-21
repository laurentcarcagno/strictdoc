# StrictDoc Backlog

**Grammar**: strictdoc_28_Backlog.gra.md \
**UID**: SDOC_BACKLOG \
**Version**: Git commit: @GIT_VERSION, Git branch: @GIT_BRANCH \
**Date**: @GIT_COMMIT_DATETIME \
**Prefix**: SDOC-BACKLOG- \
**Enable MID**: True

**Type**: TEXT \
**MID**: 35bc1e28ec724aefbcff864c89399877

This document outlines the future work items for StrictDoc.

The following items are listed in descending order of priority, with the topmost
items either currently in progress or scheduled to be implemented next.

While this backlog overlaps with StrictDoc's
[GitHub issues tracker](https://github.com/strictdoc-project/strictdoc/issues)
by more than 50%, it includes more strategic items compared to the GitHub
issues, which are primarily focused on actual implementation work.

## Backlog

**Type**: SECTION \
**MID**: 7614a9f4f7bd4b1c9899995ac3d1e6ad \
**UID**: SECTION-SB-Backlog

### Auto-commit to Git repository

**MID**: e61e7224e27d41ceacad9bf6051bd6f0 \
**UID**: SDOC-BACKLOG-6 \
**Status**: Backlog

### Auto-generate section UIDs

**MID**: 07a9636655314912a996ecf5692ae3d5 \
**UID**: SDOC-SRS-86 \
**Status**: Backlog

**Statement**: TBD

### Screen: Project home

**Type**: SECTION \
**MID**: 0425151bf3944e0ebc1c5acabcb35905 \
**UID**: SECTION-SRS-Screen-Project-home

#### View project home page

**MID**: 0a158ddac310483489ef08f618ba8741 \
**UID**: SDOC-SRS-52 \
**Status**: Backlog

### Screen: Traceability navigator

**Type**: SECTION \
**MID**: 1d8a2c3cf8c24e1b92fe212ab7efacf2

#### Traceability navigator

**MID**: dbfe92e9ec3b44e9a3e1c9e89a0e9ef5 \
**UID**: SDOC-SRS-113 \
**Status**: Backlog
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-56`

**Statement**: StrictDoc shall provide a traceability navigator screen.

**Rationale**: Provide an interactive 1000-ft view of a requirements project.

### Formal modeling

**Type**: SECTION \
**MID**: 2654d541d5ce4cb6ad9fcfe2eaa9abb4 \
**UID**: SECTION-SB-Formal-modeling

#### Integration with other systems engineering processes

**MID**: 5958a5c0aad8486b84ad31bc014d4ad3 \
**UID**: SDOC-RMC-27 \
**Status**: Backlog

**Statement**: The Requirements Tool shall provide capabilities for integration with other
systems engineering tools.

#### Integration with Capella

**MID**: 99e84f704c074cf28de51ce6fb183a66 \
**UID**: SDOC-RMC-29 \
**Status**: Backlog

**Statement**: The Requirements Tool shall provide integration with Capella MBSE tool.

**Rationale**: Eclipse Capella is a capable open-source tool for Model-Based Systems
Engineering, <https://www.eclipse.org/capella/>. It should be beneficial for the
requirements tool to interface with the Capella engineering community.

**Comment**: At the very least, the integration can happen through the ReqIF interface that
Capella is known to support.

#### Support STPA method

**MID**: 44b30591f6674ede821324fe527babd9 \
**UID**: SDOC-RMC-55 \
**Status**: Backlog

**Statement**: The Requirements Tool shall provide support for the STPA method.

#### Formalized statements

**MID**: 045aee37b0a24b3cb62cabd8b614aaf7 \
**UID**: SDOC-RMC-28 \
**Status**: Backlog

**Statement**: The Requirements Tool shall provide capabilities for hardening requirements
content with formal semantics.

**Comment**:

The directions to explore:

- NASA FRET
- bmw-software-engineering/trlc

#### AI Assistant

**MID**: 7e0fd5af118b4f5d8ecbf0d8ef3841e6 \
**UID**: SDOC-RMC-30 \
**Status**: Backlog

**Statement**: The Requirements Tool shall provide integration with AI tools (e.g., ChatGPT).

### LaTeX export

**Type**: SECTION \
**MID**: 061392f275b04c93b664faad9ed4f483 \
**UID**: SECTION-SRS-LaTeX-export

#### Export to Tex

**MID**: 9ec7f471ccb243ea9d86cf2756403b8f \
**UID**: SDOC-SRS-76 \
**Status**: Backlog

### Focused mode: Edit a single section / requirement

**MID**: 5a0304abcd8a44dab5d032dce6625a5d \
**UID**: SDOC-BACKLOG-1 \
**Status**: Backlog

**Statement**: StrictDoc shall allow focused editing of single sections and requirements on a
dedicated screen.

**Comment**: This is partially implemented with the composable documents feature. An included
document can be edited as a standalone document.

### Interoperability with Doxygen

**MID**: 162a3da4d9d74c15b5078c9859657ce3 \
**UID**: SDOC-BACKLOG-2 \
**Status**: Backlog

### Derived requirements

**MID**: 0e69828e1d914e20852aef7cfc4e87c4 \
**UID**: SDOC-BACKLOG-9 \
**Status**: Backlog
**Relations**:
- **Type**: `Parent` \
  **ID**: `DO178-18`

**Statement**: StrictDoc shall provide first-class support for Derived requirements.

### Language Server Protocol (LSP)

**MID**: 3f50a97bc70842dbabeea911f653ef90 \
**UID**: SDOC-BACKLOG-7 \
**Status**: Backlog

### UML

**MID**: 72285f9b09de48a29fef8f85431e4a94 \
**UID**: SDOC-BACKLOG-8 \
**Status**: Backlog

### Web API

**MID**: bdedcdd91c7f4efb8787b5a82cfec49b \
**UID**: SDOC-SRS-114 \
**Status**: Backlog
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-68`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-79`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-85`

**Statement**: StrictDoc shall provide a web API.

**Rationale**: A web API allows integration with tools and workflows external to StrictDoc
itself.

### Multi-user workflow

**Type**: SECTION \
**MID**: 478c38d2cca94107b18fe3dc5b8bfefd

#### User accounts

**MID**: e5b2aff0c1db4b11a8c75c278813300b \
**UID**: SDOC-SRS-130 \
**Status**: Backlog
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-65`

**Statement**: StrictDoc shall support user accounts.

#### Update notifications

**MID**: 440f0bc311b84421a7e8bea9dfd2448b \
**UID**: SDOC-SRS-131 \
**Status**: Backlog
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-66`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-74`

**Statement**: StrictDoc shall support notifying a user (users) about updated requirements.

### Requirement validation according to EARS syntax

**MID**: caecd704ed634d718deff07ba0db7fa6 \
**UID**: SDOC-SRS-116 \
**Status**: Backlog
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-57`

**Statement**: The SDoc model shall provide validation of requirements according to the EARS
syntax.

### WYSIWYG editing

**MID**: b74a7a3209d247f6b357513b0cce5000 \
**UID**: SDOC-SRS-121 \
**Status**: Backlog
**Relations**:
- **Type**: `Parent` \
  **ID**: `DO178-19`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-80`

**Statement**: StrictDoc shall provide WYSIWYG kind of editing for all multiline text input
fields.

**Rationale**: WYSIWYG improves the user experience, especially for non-programmer users.

### Tables HTML editor

**MID**: fa7fd8fd3a694d8e93953fd60e19fdde \
**UID**: SDOC-SRS-61 \
**Status**: Backlog

**Statement**: StrictDoc shall provide a solution for editing tables in its web interface.

### Attach image to requirement

**MID**: 45b8513623744776899abfbf99c95286 \
**UID**: SDOC-SRS-58 \
**Status**: Backlog

### Provide contextual help about RST markup

**MID**: c02a65f2716f4a86b8f83e3a7b4cd31c \
**UID**: SDOC-SRS-60 \
**Status**: Backlog

### TBL: Hide/show columns

**MID**: 7aa5316dd056465e97044e221412290b \
**UID**: SDOC-SRS-63 \
**Status**: Backlog

**Statement**: StrictDoc's Table screen shall allow hiding/showing columns.

### TBL: Select/deselect tags

**MID**: 229378602d1847cb83c61ab3e97bb22b \
**UID**: SDOC-SRS-64 \
**Status**: Backlog

**Statement**: StrictDoc's Table screen shall allow filtering content based on the
selection/deselection of available tags.

### Screen: Impact analysis

**Type**: SECTION \
**MID**: b3472533d57145bc9790724efe56075c

#### Impact analysis

**MID**: f5feb38777064d9db939279d32f79130 \
**UID**: SDOC-SRS-117 \
**Status**: Backlog
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-74`
- **Type**: `Parent` \
  **ID**: `DO178-11`

**Statement**:

StrictDoc shall provide the Impact Analysis screen.

NOTE: The Impact Analysis screen helps to get information about the impact that
a given change to a requirement has on the other requirements in the project
tree.

**Rationale**: The impact analysis is one of the core functions of a requirements management
tool. Analyzing the impact that a requirement has on other requirements and an
overall project's technical definition helps to perform effective change
management.

### ReqXLS

**MID**: a7c504087df04cedb5541d83ed988e9b \
**UID**: SDOC-SRS-75 \
**Status**: Backlog

## Backlog: Web-based user interface

**Type**: SECTION \
**MID**: 4a49c79a1bdd4d4aae5f62bc1d2a56d0 \
**UID**: SECTION-SB-Backlog-Web-based-user-interface

**Type**: TEXT \
**MID**: d10cddd846de4961bbb0bc8b8c6550d3

- Uploading images via Web interface.
- Editing remaining document options: Inline/Table, Requirements in TOC, etc.
- **Integration with Git repository.** Make the server commit changes to .sdoc
  files automatically. To a user, provide visibility to what happens under the
  hood.
- TBL view: Column filters to show/hide columns.
- TBL view: Completely empty columns are hidden by default.
- Contextual help about the RST markup.
- How to edit tables conveniently?
- What to do with web content going out of sync with the server/file system
  state?
- Issue when adding a child section from a nested section. The child section
  appears right after the nested section, not after its farthest descendant
  child.
- ReqIF: Export complete documentation tree or a single document.
- ReqIF: Import complete documentation tree or a single document.

## Backlog: Nice to have

**Type**: SECTION \
**MID**: 866a55f2e47b477ebcd52ea57da4f037 \
**UID**: SECTION-SB-Backlog-Nice-to-have

**Type**: TEXT \
**MID**: d02e104a518c4627ac918a33ad165c96

- Configuration file options:
  - CLI command to dump default config file
  - Project prefix?
- **StrictDoc as a Python library**. Such a use allows a more fine-grained
  access to the StrictDoc's modules, such as Grammar, Import, Export classes,
  etc.
- **Data exchange with Capella tool.** The current idea would be to implement
  this using ReqIF export/import features.
- **Language Server Protocol.** The LSP can enable editing of SDoc files in IDEs
  like Eclipse, Visual Studio, PyCharm. A smart LSP can enable features like
  syntax highlighting, autocompletion and easy navigation through requirements.
  The promising base for the implementation:
  <https://github.com/openlawlibrary/pygls>.
- Support creation of FMEA/FMECA safety analysis documents.
- Calculation of checksums for requirements. This feature is relatively easy to
  implement, but the implementation is postponed until the linking between
  requirements and files is implemented.
- Filtering of requirements by tags.
- Import/export: Confluence, Tex, Doorstop.
- **Partial evaluation of Jinja templates.** Many of the template variables
  could be made to be evaluated once, for example, config object's variables.
- UI version for mobile devices (at least some basic tweaks).
- Similar to the possibility of creating a child requirement to a section, one
  could provide a button for each of the relations defined in the grammar which
  would allow to quickly build a tree structure.

## Backlog: Technical debt

**Type**: SECTION \
**MID**: eb1fab2bbea541c8b00f70780326c9fc \
**UID**: SECTION-SB-Backlog-Technical-debt

**Type**: TEXT \
**MID**: 85e94802132048d29ca73cf2096c6758

- When a document is added, the whole documentation is rebuilt from the file
  system from scratch. A more fine-grained re-indexing of documentation tree can
  be implemented. The current idea is to introduce a layer of pickled cached
  data: preserve the whole in-memory traceability graph in a cache, and then use
  the cached data for making decisions about what should be regenerated.
- The "no framework" approach with FastAPI and Turbo/Stimulus allows writing
  almost zero Javascript, however some proto-framework conventions are still
  needed. Currently, all code is written in the `main_controller` which
  combines all responsibilities, such as parsing HTTP request fields, accessing
  traceability graph, validations, rendering back the updated AJAX templates. A
  lack of abstraction is better than a poor abstraction, but some solution has
  to be found.
- Request form object vs Response form object. The workflow of form validations
  is not optimal.
- For Web development, the responsibilities of the `TraceabilityIndex` class
  compared to the `ExportAction`, `MarkupRenderer`, `LinkRenderer` classes
  are unstable. A more ecological composition of classes has to be found.
  `Traceability` index is rightfully a "god object" because it contains all
  information about the in-memory documentation graph.

## Open questions

**Type**: SECTION \
**MID**: 6ef8c2ad683d46af948674727c7a52b4 \
**UID**: SECTION-SB-Open-questions

### One or many input sdoc trees

**Type**: SECTION \
**MID**: 717df91623014fb98ba34ab8173b94ab \
**UID**: SECTION-SB-One-or-many-input-sdoc-trees

**Type**: TEXT \
**MID**: b778a18ede89464c936be2b2af492e24

StrictDoc supports this for HTML already but not for RST.

When passed `strictdoc export ... /path/to/doctree1, /path/to/doctree2, /path/to/doctree3`, the following is generated:

```text
output folder:
- doctree1/
  - contents
- doctree2/
  - contents
- doctree3/
  - contents
```

and all three doctrees' requirements are merged into a single documentation
space with cross-linking possible.

The question is if it is worth supporting this case further or StrictDoc should
only work with one input folder with a single doc tree.
