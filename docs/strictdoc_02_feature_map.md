# StrictDoc Feature Map

**Grammar**: strictdoc_02_feature_map.gra.md \
**UID**: SDOC_FEATURE_MAP \
**Version**: Git commit: @GIT_VERSION, Git branch: @GIT_BRANCH \
**Date**: @GIT_COMMIT_DATETIME \
**Prefix**: SDOC-FEAT- \
**Enable MID**: True \
**View style**: Narrative

**Type**: TEXT \
**MID**: f405431dc66e4d6786be020a62a4e5a3

This document provides a comprehensive overview of all available features in
StrictDoc from the user's perspective. It includes descriptions and relevant
screenshots to illustrate each feature's functionality. Each entry is linked to
additional documentation, such as the [LINK: SDOC_UG], offering further details,
usage instructions, and examples to help users understand and effectively
utilize StrictDoc’s capabilities.

## SDoc text markup

**Type**: SECTION \
**MID**: 01c07ca347a24181a92a5be6c8431094 \
**UID**: SECTION-FM-SDoc-text-markup

### Definition

**Type**: SECTION \
**MID**: dfd4d2d77c7247819e476f360ffff639

#### SDoc text markup

**Type**: FEATURE \
**MID**: 4c40803dd0f04af88fd722ba6b732270 \
**UID**: SDOC-FEAT-1 \
**Status**: Stable

**Statement**: The SDoc markup language is a hybrid format inspired by TOML, YAML, ASN.1, and
HTML/XML, designed specifically for structuring technical documents with large
volumes of requirements. It aims to encode documents that span up to several
hundred or even a few thousand A4-printed pages, while keeping the markup noise
minimal to maintain readability. The format supports both shallow and deeply
nested document structures, accommodating up to 9-10 levels of chapter nesting,
and allows for multiple meta-information fields around each requirement.

**DOCUMENTATION**:

- [LINK: SECTION-UG-SDoc-syntax]

### Use case

**Type**: SECTION \
**MID**: 3f422abd9abe4717a995ae4150df12e3

**Type**: TEXT \
**MID**: 8ea5b080819e47afa78bc346d671cf30

The main use case for SDoc is to model a structure of a technical document that
consists of tens and hundreds of technical requirements. The following
high-level requirements for the markup are therefore relevant:

- Encode documents of reasonable size (up to several hundreds or few thousands
  of A4-printed pages).
- Visualize large blocks of requirements text without too much markup noise.
- Support documents with nested (2-4 levels) or deeply nested structure
  (detailed technical specifications with up to 9-10 levels of chapter nesting).
- Support multiple fields for requirement meta information which makes a
  requirement look like "a text with some meta information around it".

The SDoc markup has been pretty stable since its inception but the flexibility
of the TextX parser allows easy modifications of the language in case of future
evolutions. Any feedback to the current design of the markup language is
appreciated.

### Inspirations

**Type**: SECTION \
**MID**: fa7b37153def4eb4a6e9dcee079cba2a

**Type**: TEXT \
**MID**: 104b6ff4623f4ac9a965aa789c4cf001

The SDoc markup is a hybrid of TOML and YAML with some influence from HTML/XML
and [ASN.1](https://en.wikipedia.org/wiki/ASN.1). Using each of these formats
as-is, and also the JSON format, was considered but discarded during the design.

**TOML: Square bracket syntax**

From TOML, StrictDoc borrowed the `[]` bracket syntax to create the
`[REQUIREMENT]`, `[SECTION]` and other blocks but uses the YAML-like syntax
for these blocks' fields, for example:

```
[REQUIREMENT]
TITLE: Requirement ABC
STATEMENT: The system A shall do B when C.
```

**TOML/YAML: Arrays/dictionaries**

StrictDoc has a rudimentary support of arrays and dictionaries. For example, the
syntax for defining the document's `[GRAMMAR]` resembles what would look like
an array of records in YAML:

```
[GRAMMAR]
ELEMENTS:
- TAG: REQUIREMENT
  FIELDS:
  - TITLE: UID
    TYPE: String
    REQUIRED: True
  - TITLE: LEVEL
    TYPE: String
    REQUIRED: False
```

**Capitalization of reserved keywords from ASN.1**

From ASN.1, StrictDoc borrows the idea of having all reserved fields
capitalized. This helps to visually distinguish between the grammar content and
user content.

**Nested sections**

From HTML, the idea of opening and closing tags is taken to avoid any nesting
that would otherwise be required to support the deeply nested documents with up
to 6 or 8 levels, e.g., 1.1.1.1.1.1.1...

```
[[SECTION]]
TITLE: Section 1

[[SECTION]]
TITLE: Section 1.1

...

[[/SECTION]]

[[/SECTION]]
```

Taking HTML or XML as-is didn't seem like a good option because of the heavy
visual noise that is produced around the actual content by the surrounding tags.

**Multiline strings**

The support of multiline strings is arranged by a custom solution which helps to
avoid any nesting of multiline text as well as to visually indicate the start
and end parts of the multiline string in a visually unambiguous way. This is how
the multiline string is declared:

```
[REQUIREMENT]
TITLE: Requirement ABC
STATEMENT: >>>
The multiline requirement statement
without any nesting.
>>>
```

**Discarded options**

Taking TOML or YAML as-is didn't seem like a good option because these formats
are designed to be used for configuration files or data serialization and not
for large documents with hundreds of requirements. The most obvious problems for
reusing either of TOML or YAML directly would have been with encoding the deeply
nested documents and supporting readable and non-nested multiline strings.

### Screenshots

**Type**: SECTION \
**MID**: 87b1538be72a4ff7945b5bb95f856471

**Type**: TEXT \
**MID**: f48ae881c5134f77885202b019e124d4

<img src="_assets/Feature_Screenshot_SDoc.png" alt="SDoc markup" width="100%" />

## HTML export

**Type**: SECTION \
**MID**: 27bb9f0875d84d79bb882f6ca98ee1fa

### Definition

**Type**: SECTION \
**MID**: 4a0844b5938a488a89ac4b379fc7d956

#### StrictDoc HTML export

**Type**: FEATURE \
**MID**: 8e6604c8b27b450cbd21c12dc8572291 \
**UID**: SDOC-FEAT-2

**Statement**:

StrictDoc's static HTML export feature allows users to generate comprehensive
documentation from .sdoc files into a well-structured HTML format. It leverages
an efficient in-memory representation of document trees, supporting large-scale
documents with thousands of requirements while maintaining decent performance.

The HTML output preserves the hierarchy of requirements, including parent-child
relationships, to facilitate traceability and coverage analysis.

Additionally, StrictDoc's incremental generation mechanism ensures quick updates
by only regenerating modified documents, enabling efficient handling of
extensive requirements specifications.

**DOCUMENTATION**:

- [LINK: SECTION-UG-Static-HTML-export]

### Screenshots

**Type**: SECTION \
**MID**: 4e46063e2031418298b55a1861179900

**Type**: TEXT \
**MID**: 586f8745588b483b8e027021d90931ac

<img src="_assets/Feature_Screenshot_HTMLExport_01_Index.png" alt="StrictDoc HTML export – Project tree" width="100%" />

## Web-based graphical user interface

**Type**: SECTION \
**MID**: 3ef4254efd8547a8adaf37e100f22724

### Definition

**Type**: SECTION \
**MID**: bd3e1273cb244616956bddfc22c05638

#### StrictDoc web-based graphical user interface

**Type**: FEATURE \
**MID**: 2c1cde585d5944b5b7b5a0d5f72a98ed \
**UID**: SDOC-FEAT-3 \
**Status**: Stable

**Statement**: StrictDoc features an editable web interface that enables users to view and
modify requirements directly within their browser. This interface provides a
user-friendly way to interact with .sdoc files, allowing real-time editing of
documents and requirements. Changes made through the web interface are
automatically saved back to the original text files, ensuring synchronization
between the user interface and the underlying document structure. The web
interface also supports visualization of requirement hierarchies and
relationships, making it easier to manage complex documents with multiple nested
levels and linked requirements.

**DOCUMENTATION**:

- [LINK: SECTION-UG-Web-server]
- [LINK: SDOC_UG_LIMIT_WEB]

### Screenshots

**Type**: SECTION \
**MID**: 6b5989db0e984c42b12440993c885987

**Type**: TEXT \
**MID**: 28ce32fe182c45ce882b65c835620339

<img src="_assets/Feature_Screenshot_WebUI.png" alt="StrictDoc web interface" width="100%" />

<img src="_assets/Feature_Screenshot_WebUI_2.png" alt="StrictDoc web interface" width="100%" />

## Traceability between requirements and source code

**Type**: SECTION \
**MID**: 5ac3e3c690494371bd9de04be5eae0b0

### Definition

**Type**: SECTION \
**MID**: 538d26fae4644debbc8f244709b8be7b

#### Traceability between requirements and source code

**Type**: FEATURE \
**MID**: e14eee106ea443e598378e55401914dc \
**UID**: SDOC-FEAT-4

**Statement**: StrictDoc supports traceability between requirements and source code, enabling
the creation of links from requirements specified in .sdoc files to relevant
source code files. This feature ensures that each requirement is adequately
addressed in the implementation by associating it with corresponding segments of
the codebase. Traceability links are defined using custom references, allowing
teams to track which parts of the code fulfill specific requirements. This
capability is essential for compliance, validation, and maintaining consistency
between documentation and actual implementation. These connections can be
visualized in the generated HTML exports, providing a clear and navigable
overview of the relationship between requirements and the codebase​.

**DOCUMENTATION**:

- [LINK: SECTION-TRACEABILITY-REQS-TO-SOURCE-CODE]

### Screenshots

**Type**: SECTION \
**MID**: ceec313d9ec040b9bcaaf64967ed6af8

**Type**: TEXT \
**MID**: 363aae23cbb44f30aff42ef6a430ffdf

<img src="_assets/Feature_Screenshot_TraceabilityToSource_1.png" alt="Traceability to source 1" width="100%" />

<img src="_assets/Feature_Screenshot_TraceabilityToSource_2.png" alt="Traceability to source 2" width="100%" />

## Document grammar

**Type**: SECTION \
**MID**: a436d31c5f324eb0bb6b35f0a6ce598d

### Definition

**Type**: SECTION \
**MID**: f20223cddcb14e40b45f99045e2d3a3a

#### Custom document grammars

**Type**: FEATURE \
**MID**: 0bfcb6144dde487791d4f01164dd7e7c \
**UID**: SDOC-FEAT-5

**Statement**: The "Document grammar" feature allows users to extend the default grammar to fit
specific project needs, particularly useful for industries with specialized
requirements documentation, such as automotive or aerospace. This feature
supports defining custom fields like "PRIORITY," "VERIFICATION," or
domain-specific tags like "ASIL" for automotive safety standards. Custom
grammars are declared at the document level using the `[GRAMMAR]` directive,
enabling users to specify custom fields and their data types, such as
`String`, `SingleChoice`, `MultipleChoice`. These fields can be marked as
mandatory, ensuring consistency across requirements documents.

**DOCUMENTATION**:

- [LINK: SECTION-UG-DOCUMENT-GRAMMAR]

### Screenshots

**Type**: SECTION \
**MID**: f4763b00f9624cfd8b44f8e571f2aec6

**Type**: TEXT \
**MID**: 3d3d3e2c1c974ed4a2382770225212d7

<img src="_assets/Feature_Screenshot_Grammar.png" alt="Document grammar" width="75%" />

## Composable documents

**Type**: SECTION \
**MID**: 5b511eac439c4e0a8aa2c60499be88d0

### Definition

**Type**: SECTION \
**MID**: ab4bc7b948154dbfbd4956d41cda8b75

#### Composable documents

**Type**: FEATURE \
**MID**: e7b2d61545eb414f97345ecac25c52cc \
**UID**: SDOC-FEAT-6

**Statement**: The "Composable Documents" feature in StrictDoc enables users to create
composite documents made up of smaller, independent SDoc documents. This modular
approach allows each document fragment to be managed separately, which is
particularly useful when dealing with large, complex requirements documents.

**DOCUMENTATION**:

- [LINK: UG_COMPOSABLE_DOCUMENTS]

## Export to PDF

**Type**: SECTION \
**MID**: 2e8e39a2198e4f8aa18a470a892e4d25

### Definition

**Type**: SECTION \
**MID**: 381ebcd10ee241aaaa9fe3654870961c

#### Export to PDF

**Type**: FEATURE \
**MID**: 5be4f35be2eb49faae7c33b5a2d83251 \
**UID**: SDOC-FEAT-10 \
**Status**: Experimental

**Statement**:

The HTML2PDF feature in StrictDoc enables web-based printing to PDF by
leveraging ChromeDriver and Google Chrome. This approach uses the Selenium
Python library to automate the printing of HTML content directly to PDF format,
ensuring that the final document mirrors the exact HTML content rendered in the
browser.

The feature allows the user to export content to PDF via a web interface or
through a command-line interface. This ensures that the output closely resembles
the web page, with no need for additional formatting or adjustments to the
content.

**DOCUMENTATION**:

- [LINK: SECTION-UG-HTML2PDF-document-generator]

### Screenshots

**Type**: SECTION \
**MID**: 2d8b04efe57d4c0aa543ed974ace868e

## Query engine and search screen

**Type**: SECTION \
**MID**: 15d6e791674c4c0ab54afb6a781f35c9

### Definition

**Type**: SECTION \
**MID**: 91177d3444d9437e87032875ac8fcd7d

#### Query engine and search screen

**Type**: FEATURE \
**MID**: 9c1e6cb601294891bcaae2b8c9042c59 \
**UID**: SDOC-FEAT-7 \
**Status**: Experimental

**Statement**: The "Query Engine and Search Screen" feature in StrictDoc offers tools for
searching and filtering requirements within documents. It uses a Python-inspired
syntax to perform complex queries on the document tree, allowing users to find
specific sections or requirements based on attributes like titles, parent-child
relationships, or custom fields. The search screen is integrated into the web
interface, where users can craft queries with logical operators (e.g., AND, OR)
and attribute filters (e.g., `node.is_requirement`).

**DOCUMENTATION**:

- [LINK: SECTION-UG-Search-and-filtering]

### Screenshots

**Type**: SECTION \
**MID**: 631f1620053342c8a398a1a5d458f873

**Type**: TEXT \
**MID**: 64afc2abdab847439c0c18420db7ba47

<img src="_assets/Feature_Screenshot_SearchScreen_01.png" alt="StrictDoc Search Screen" width="100%" />

## Project statistics

**Type**: SECTION \
**MID**: 3475f60f31b5488aab981fd2b7b12d4c

### Definition

**Type**: SECTION \
**MID**: 9bbcc02a46194852b9616ea4437ce976

#### Project Statistics

**Type**: FEATURE \
**MID**: 2dd0b514a24f43a287a4096d0be0af58 \
**UID**: SDOC-FEAT-11 \
**Status**: Experimental

**Statement**: The "Project Statistics" feature in StrictDoc provides insights into the overall
status and details of a documentation project. It offers statistical data that
can include information about requirements, document structure, and coverage.

**DOCUMENTATION**:

- [LINK: SECTION-UG-Project-statistics-screen]

### Screenshots

**Type**: SECTION \
**MID**: 7d215ba517fc4aee9dfb381279297cc7

**Type**: TEXT \
**MID**: bd5a4763e2ca4df497dbaeeff9ffbd71

<img src="_assets/Feature_Screenshot_StatisticsScreen_01.png" alt="Project statistics" width="100%" />

<img src="_assets/Feature_Screenshot_StatisticsScreen_02.png" alt="Project statistics" width="100%" />

## Documentation diff/changelog

**Type**: SECTION \
**MID**: 0b3d7fad0ee643ef83617745c51e8e72

### Definition

**Type**: SECTION \
**MID**: 9cdf4d3af1014aea923f77b112e6b1e3

#### Documentation diff/changelog

**Type**: FEATURE \
**MID**: e9da42f8e39b438a8e8eada16b280706 \
**UID**: SDOC-FEAT-12 \
**Status**: Experimental

**Statement**: The "Documentation diff/changelog" feature in StrictDoc allows users to track
and compare changes made between different versions of project documentation.
This feature can highlight modifications at a granular level, such as added,
deleted, or altered content within the document.

**DOCUMENTATION**:

- [LINK: SECTION-UG-Diff-changelog-screen]

### Screenshots

**Type**: SECTION \
**MID**: c60c6fab5740469aa251bfa3a805f21f

**Type**: TEXT \
**MID**: 1fad67b63724450bb63738cf7e29d051

<img src="_assets/Feature_Screenshot_DiffChangelog_1.png" alt="StrictDoc Diff/Changelog 1" width="100%" />

<img src="_assets/Feature_Screenshot_DiffChangelog_2.png" alt="StrictDoc Diff/Changelog 2" width="100%" />

## ReqIF support

**Type**: SECTION \
**MID**: f655f9a2bde044489233fa03d2891de1

### Definition

**Type**: SECTION \
**MID**: 1627a126e1184c5e9050206f2f1ab725

#### ReqIF support

**Type**: FEATURE \
**MID**: 2845463f977d4b51ac788c2fc9cbd894 \
**UID**: SDOC-FEAT-13 \
**Status**: Experimental

**Statement**:

The ReqIF support feature in StrictDoc allows for both importing and exporting
to the ReqIF format, facilitating interoperability with other requirements
management tools.

ReqIF is a widely used XML-based standard for requirements data exchange. The
import flow allows ReqIF files to be converted into SDoc documents, while the
export flow enables SDoc content to be converted back into ReqIF format.

The implementation of ReqIF support is tool-specific due to the flexibility of
the ReqIF standard. Different tools may structure and name their fields
differently, which means the export/import workflows may require adjustments
depending on the tools involved. StrictDoc provides its own model for converting
between ReqIF and SDoc, making it adaptable for specific use cases while
striving for compatibility with the ReqIF format recommended by the ReqIF
Implementation Guide​.

**DOCUMENTATION**:

- [LINK: SECTION-UG-ReqIF-support]

## Word support

**Type**: SECTION \
**MID**: 52b0247b93234fc1a78cf497740b740d

### Definition

**Type**: SECTION \
**MID**: fae1ff97e14642b2b0024c161e759aaf

#### Word support

**Type**: FEATURE \
**MID**: 73ad2b34824f401da05022e6504764e6 \
**UID**: SDOC-FEAT-14 \
**Status**: Experimental

**Statement**:

The Word support feature in StrictDoc imports requirements from a Word (.docx)
document into SDoc and exports SDoc back to Word.

A mapping profile describes how the document is organized: which styles are
headings and how a requirement table is laid out. The import merges a changed
Word document into the existing SDoc files by UID. The export can fill a Word
template. When a Word document is already under review, the export can instead
update it and write the differences as Word tracked changes.

The web interface offers the same actions as dialogs, with a preview of the
report, when the `DOCX` feature is activated.

**DOCUMENTATION**:

- [LINK: SECTION-UG-Word-support]

## Project configuration

**Type**: SECTION \
**MID**: e1109c5b3b1c4068a0eace811684f0c0

### Definition

**Type**: SECTION \
**MID**: 3c2a1a37e11c425184042d6dab3f050a

#### Project configuration

**Type**: FEATURE \
**MID**: 8fc72d79bfe940aba2cf041e263b92df \
**UID**: SDOC-FEAT-9

**Statement**:

The "strictdoc_config.py" file is a project-level configuration file used in
StrictDoc to manage various project settings. This configuration file allows
customization for features such as selected functionalities, document paths,
source file paths, etc.

Key options configurable via "strictdoc_config.py" include:

- Project title: Defines a project title.
- Feature selection: Selects additional features to activate or deactivate, such
  as traceability features or experimental tools.
- Paths customization: cache dir, asset dir, document include/exclude paths,
  source file include/exclude paths, etc.

This configuration ensures that StrictDoc works according to the specific needs
of a given project, making it more flexible and adaptable​.

StrictDoc previously used a "strictdoc.toml" file for the same purpose. TOML
configuration is deprecated and will trigger a warning; see
SECTION-UG-MIGRATE-CONFIG-2025-Q4 for migration instructions.

**DOCUMENTATION**:

- [LINK: SDOC_UG_OPTIONS_PROJECT_LEVEL]

### Screenshots

**Type**: SECTION \
**MID**: 275658296e5342acab72102589096f15

**Type**: TEXT \
**MID**: 100daefc4121415989324de1978d1f59

<img src="_assets/Feature_Screenshot_StrictDocTOML.png" alt="StrictDoc config file (legacy strictdoc.toml format, superseded by strictdoc_config.py)" width="100%" />
