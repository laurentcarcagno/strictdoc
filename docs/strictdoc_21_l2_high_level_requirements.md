# StrictDoc High-Level Requirements (L2)

**Grammar**: strictdoc_21_l2_high_level_requirements.gra.md \
**Version**: Git commit: @GIT_VERSION, Git branch: @GIT_BRANCH \
**Date**: @GIT_COMMIT_DATETIME \
**Prefix**: SDOC-SRS- \
**Enable MID**: True

## SDoc data model

**Type**: SECTION \
**MID**: bd8a7931c1e04df9bf08d291488c67aa

### Data model

**MID**: e8d5b55055254144b96d1ffeb587ec72 \
**UID**: SDOC-SRS-18 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-88`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-58`

**Statement**: StrictDoc shall be based on a data model.

**Rationale**:

Designing StrictDoc with a goal of having a consistent data model ensures that
the tool:

1) can support a rich set of use cases,
2) model the existing documentation templates used by the industries,
3) interface well with other formats for storing documentation and requirements,
   e.g., ReqIF and SPDX.

**Comment**: Verification: data model diagram TBD.

### Requirement model

**MID**: 3b31cad22529476db01aca41caf39750 \
**UID**: SDOC-SRS-26 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-4`

**Statement**: StrictDoc's data model shall support modeling requirements.

### Requirement model fields

**MID**: 8e2ffffd33af4a969d5bb7ca40cb49a4 \
**UID**: SDOC-SRS-100 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-62`

**Statement**: StrictDoc's "Requirement" model shall support configurable fields system.

### Requirement model default fields

**MID**: 2d4020ba06d74571aef7aafe8604215b \
**UID**: SDOC-SRS-132 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-61`

**Statement**:

By default, the Requirement shall support the following fields:

- MID
- UID
- STATUS
- TITLE
- STATEMENT
- RATIONALE
- COMMENT.

**Rationale**: These fields are the most typical fields found in requirement documents.

### Document model

**MID**: f94419a390f2403daa3c4cd0e96f6cb6 \
**UID**: SDOC-SRS-98 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-64`

**Statement**: StrictDoc's data model shall support modeling documents.

### Document metadata

**MID**: 435f856197d743c1b9b1dcbe91a22863 \
**UID**: SDOC-SRS-110 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-53`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-75`

**Statement**:

StrictDoc's data model shall support a Document metadata model including at
least:

- UID
- Document version
- Document classification
- Document authors.

### Document configuration

**MID**: abcced8724d743c1b9b1dcbe91a22863 \
**UID**: SDOC-SRS-151 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-53`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-75`

**Statement**:

StrictDoc's data model shall support configuring the document options:

- Enable/disable MID
- Markup choice: Markdown (default) or HTML
- Levels (automatic or manual)
- Node style
- Default presentation view.

### Section model

**MID**: 63821c507d584cf985f05904710b9779 \
**UID**: SDOC-SRS-99 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-51`

**Statement**: StrictDoc's data model shall support a concept of a "Section" which nests other
Sections, Requirements, Texts.

**Rationale**: "Section" corresponds to a chapter or a section in a document and helps to
organize a document by grouping text nodes, requirements and other sections.

### Free text

**MID**: 899d2f68749b4be1a3124fe4d01de1aa \
**UID**: SDOC-SRS-135 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-3`

**Statement**: StrictDoc's data model shall support a "Free Text" model, representing
non-normative documentation content.

**Rationale**: Documentation comprises normative components, such as uniquely identifiable
elements like requirements or design items, and non-normative components,
including introductory text, overview chapters, and other content. The
non-normative parts help provide a general understanding for the reader but do
not contribute to traceability information. StrictDoc's free text is designed to
store this type of non-normative information in SDoc documents.

### Composeable document

**MID**: 983653fc26214f46977dc792d65ae65f \
**UID**: SDOC-SRS-109 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-52`
- **Type**: `Parent` \
  **ID**: `DO178-4`

**Statement**: StrictDoc's data model shall allow composing a Document from other Documents.

**Rationale**: The logic behind the parent requirement remains fully relevant. Additionally, an
alternative approach could involve using a dedicated entity, like "Fragment", to
allow a Document to be composed of includable sections or document fragments.
Managing composition at the Document level eliminates the need in additional
entities like "Fragment", streamlining both the conceptual understanding and the
practical implementation of composability.

**Comment**: The corresponding UI capability for Fragments CRUD is TBD.

### Requirement relations

**MID**: fad4cf5dcf4d40518c7c9826fd6bd18a \
**UID**: SDOC-SRS-31 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-7`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-48`

**Statement**: The StrictDoc data model shall support connecting requirements using Parent and
Child relations.

**Rationale**: Support of both Parent and Child relations allows to build typical requirements
relations such as child-to-parent and less common relations when one document
can have parent links to a parent document and child links to a child document
(e.g., the so-called "compliance" or "tailoring matrix" documents may use this
structure).

### Requirement relation roles

**MID**: 9930894b08c44f5eba996c0a255e9e3f \
**UID**: SDOC-SRS-101 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-8`

**Statement**:

Each SDoc relation shall be optionally configurable with a relation role.

NOTE: A relation role is a string value. Typical examples: "refines",
"verifies", "implements".

### Inline links

**MID**: fa090bc6976c4275aadbf522da6b920b \
**UID**: SDOC-SRS-149 \
**Status**: Active

**Statement**: StrictDoc shall support referencing any node by embedding a hyperlink within the
text content of another node.

**Rationale**: The inline links do not replace the relations between SDoc nodes. Instead, an
inline link could be an easy way to refer from one textual node to a chapter or
a document. A common use case is "See section ABC for more details".

### Inline anchors

**MID**: 54132bc6976c4275aadbf522da6b920b \
**UID**: SDOC-SRS-150 \
**Status**: Active

**Statement**: StrictDoc shall support adding anchors within the text content of any node, such
that these anchors can be referenced by inline links from other nodes.

**Rationale**: Anchors allow authors to define precise reference points within SDoc node
fields.

### Capability: Automatic generation of UID

**Type**: SECTION \
**MID**: 26a0233258ec4d7ab6338d915ddea3e6

#### Default UID generation algorithm

**MID**: 1ff58c59c8ab48cdabfba942ba98bab7 \
**UID**: SDOC-SRS-206 \
**Status**: Active

**Statement**:

StrictDoc shall generate a missing UID for a node according to the following
algorithm:

- The node's applicable UID prefix shall be resolved by evaluating, in order
  of precedence: the node's own PREFIX field, the grammar element's PREFIX
  property, the parent section's prefix, and the document's PREFIX setting,
  which shall default to "REQ-" if not configured.
- The highest numeric suffix currently in use with the resolved prefix shall
  be determined by scanning the entire document tree.
- The node shall be assigned a UID composed of the resolved prefix and the
  next unused integer suffix, computed as the highest existing suffix
  incremented by one, or one if no existing suffix is found.
- Where multiple nodes share the same resolved prefix and lack a UID,
  consecutive integer suffixes shall be assigned to them in document order.

#### Custom UID algorithms

**MID**: 4ed550f6074c4d8cb27196184f7fe234 \
**UID**: SDOC-SRS-207 \
**Status**: Active

**Statement**: StrictDoc shall allow a user to customize the UID algorithm to their needs.

**Comment**:

An example of a custom algorithm suggested by a user:

The expected behavior could be:

- The prefix of a type is defined in the grammar.
- A document can optionally define an additional prefix.
- If both prefixes are present, they are concatenated.
- If only the grammar prefix is present, it is used on its own.
- If only the document prefix is present, it is used on its own.
- If neither is present, the existing behavior should be preserved.

## SDoc text markup

**Type**: SECTION \
**MID**: cbc7f72c6e0b4c858817bf17357105a5

### SDoc markup language

**MID**: 27a6da48c65445539e536ee034921fb5 \
**UID**: SDOC-SRS-20 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-88`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/grammar/grammar.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/grammar/grammar_builder.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/reader.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/writer.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/processor.py`

**Statement**: StrictDoc shall implement its own text markup language called S-Doc
(strict-doc).

**Rationale**: The most commonly used Markdown format lacks the ability to store requirements
metadata. While the Markdown syntax can carry metadata only by convention, its visual appearance contradicts other
requirements of StrictDoc, such as the type-safety of the grammar and visual
readability. Therefore, a markup language tailored specifically to the needs of
the requirements tool provides direct control over the capabilities implemented
in both the markup and the user interface.

### Identical SDoc content by import/export roundtrip

**MID**: 1f147feed60245378de2e099facd196d \
**UID**: SDOC-SRS-136 \
**Status**: Active
**Relations**:
- **Type**: `File` \
  **Path**: `tests/unit/strictdoc/backend/sdoc/test_dsl_passthrough.py`
- **Type**: `File` \
  **Path**: `tests/unit/strictdoc/backend/sdoc/test_dsl_passthrough_document_views.py`
- **Type**: `File` \
  **Path**: `tests/unit/strictdoc/backend/sdoc/test_dsl_passthrough_grammar.py`
- **Type**: `File` \
  **Path**: `tests/unit/strictdoc/backend/sdoc/test_dsl_passthrough_relations.py`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-94`

**Statement**: StrictDoc shall ensure that identical SDoc content is produced every time
StrictDoc reads an SDoc file and then writes it to another SDoc file.

**Rationale**: A consistent import/export roundtrip implementation and testing reduces the risk
of the SDoc bi-directional import/export corruption.

### SDoc and Git storage

**MID**: f48a57c0cd764951a667127ce92fdb12 \
**UID**: SDOC-SRS-127 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-87`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-33`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-84`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-94`

**Statement**: StrictDoc shall assume and implement capabilities for storage of SDoc files
using Git version control system.

### SDoc file extension

**MID**: 9df34a7ab79842d99ee68303f334d4eb \
**UID**: SDOC-SRS-104 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-80`

**Statement**: The SDoc markup content shall be stored in files with .sdoc extension.

**Rationale**: Given that the name of the model is S-Doc (strict-doc), it is reasonable to make
the document files have the `.sdoc` extension. This helps to identify the
document files.

### One document per one SDoc file

**MID**: 8dd6dd3979484dadbe71ac91aab50608 \
**UID**: SDOC-SRS-105 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-64`
- **Type**: `Parent` \
  **ID**: `DO178-1`

**Statement**: StrictDoc's SDoc file shall represent content of a single document.

**Comment**: A "Document" corresponds to a "Document" of the SDoc data model.

### Fixed grammar

**MID**: e5e3033c13f24fa083423230da7994f7 \
**UID**: SDOC-SRS-19 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `DO178-2`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-55`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-54`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-94`

**Statement**: StrictDoc's markup language shall be based on a well-defined grammar.

### Default grammar fields

**MID**: b97418ceccff438cb0457ed4bdf1be47 \
**UID**: SDOC-SRS-93 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-61`

**Statement**:

The StrictDoc grammar shall have at least the following fields activated by
default:

- UID
- STATUS
- TITLE
- STATEMENT
- RATIONALE
- COMMENT
- RELATIONS (references to other requirements)

### Custom grammar / fields

**MID**: 8924c29136944f65ac5efc8b6b90a07b \
**UID**: SDOC-SRS-21 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-62`

**Statement**: The SDoc markup shall support custom grammars.

**Rationale**: A custom grammar allows a user to define their own configuration of requirement
fields.

### Importable grammars

**MID**: 10d23bfbf4504c2e8c995ae89c500be4 \
**UID**: SDOC-SRS-122 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `DO178-9`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-52`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/grammar_reader.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/grammar/grammar_grammar.py`

**Statement**: StrictDoc shall support an inclusion of a grammar stored in a separate file.

**Rationale**: A single grammar defined for several documents helps to standardize the
structure of all documents in a documentation tree and removes the effort needed
to create identical grammars all the time.

### UID identifier format

**MID**: 5405c74a9eba4e9193007f01ea98bc85 \
**UID**: SDOC-SRS-22 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-89`

**Statement**: The SDoc markup shall only accept UID identifiers that consist of alphanumeric
characters separated by a limited set of ("\_", "-", ".") characters (TBD).

**Rationale**: A standardized UID format supports easier unique identification of requirements.
It is easier to visually identify UIDs that look similar and common to a given
industry.

**Comment**: This requirement may need a revision to accommodate for more UID formats.

### Format-specific markup-to-HTML fragment writers

**MID**: f871dfc381354daf820cc1e2b94fdb05 \
**UID**: SDOC-SRS-24 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-63`

**Statement**: StrictDoc shall render supported markup formats (Markdown and HTML) to
HTML fragments via dedicated format-specific writers selected by markup type.

### MathJAX

**MID**: b1b4f03d4e404a14be481626803fcfc2 \
**UID**: SDOC-SRS-27 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-63`

**Statement**: StrictDoc's markup language shall support integration with MathJax.

### No indentation

**MID**: 39f117b79cfa4a8485c458280b3d36ce \
**UID**: SDOC-SRS-23 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-55`

**Statement**: SDoc text markup blocks shall all start from column 1, i.e., the nesting of the
blocks is not allowed.

**Rationale**: Nesting large text blocks of free text and requirements compromises readability.

### Type-safe fields

**MID**: 98628e1db3ca4f52b7632674b69dd657 \
**UID**: SDOC-SRS-25 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-55`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/grammar/type_system.py`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-94`

**Statement**:

SDoc markup shall provide "type safety" for all fields.

NOTE: "Type safety" means that each field has a type and a corresponding set of
validation checks.

## Markdown markup

**Type**: SECTION \
**MID**: 8e175c1aff9c4bc1b20b032d6811e853

### Markdown support

**MID**: 1e1685d8be084a6c98729daae5637860 \
**UID**: SDOC-SRS-202 \
**Status**: Active

**Statement**: StrictDoc shall support Markdown markup.

**Rationale**: Markdown is the most popular markup language among programmers. Compared to the
StrictDoc native SDoc markup, Markdown is much more familiar to developers,
which lowers the entry barrier for writing formal requirements with StrictDoc or
other tools. It is also used extensively by AI tools.

### Markdown as the default markup

**MID**: 0a95844e4269458394a6bb6fe9869d89 \
**UID**: SDOC-SRS-1217 \
**Status**: Active
**Relations**:
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/processor.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc/constants.py`

**Statement**: StrictDoc shall read the text fields of a document as Markdown unless the
document declares the HTML markup, and shall refuse the RST and Text markups
with an error that names the migration tool.

**Rationale**: One markup keeps the rendering, the editor and the exports consistent. A
document that still declares a removed markup must fail loudly instead of
rendering its text wrongly.

### HTML elements for what Markdown lacks

**MID**: 8bcd4472afb743faab9212cdaac83aca \
**UID**: SDOC-SRS-1218 \
**Status**: Active
**Relations**:
- **Type**: `File` \
  **Path**: `strictdoc/backend/markdown/markdown_to_html_fragment_writer.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/docx/export/markdown_to_paragraphs.py`

**Statement**: StrictDoc shall render the HTML elements that stand for the constructs that
Markdown does not have (admonitions, definition lists, tables with spans,
subscripts, superscripts and numbered equations) in a Markdown field, and
shall export them to HTML, PDF and DOCX.

**Rationale**: Documents migrated from RST use these constructs. HTML keeps them readable in
the source and in every export.

### Sanitization of the HTML of a Markdown field

**MID**: 3e95bb7953ac44c29a196ae26b814959 \
**UID**: SDOC-SRS-1219 \
**Status**: Active
**Relations**:
- **Type**: `File` \
  **Path**: `strictdoc/backend/markdown/html_sanitizer.py`

**Statement**: StrictDoc shall keep only the allow-listed HTML elements, attributes, URL
schemes and styles when it renders the raw HTML of a Markdown field.

**Rationale**: A requirements document is shared and rendered by the web server. Raw HTML
must not run scripts or load active content.

## Desktop application

**Type**: SECTION \
**MID**: 1f67ad607292411786ab6f57302a7c1b \
**UID**: SECTION-SRS-Desktop-application

### Desktop command

**MID**: e9774c344e6e4ffcb20ef9d05225be17 \
**UID**: SDOC-SRS-1220 \
**Status**: Active

**Statement**: StrictDoc shall provide the `strictdoc desktop` command, which starts the web
server of a project on the address 127.0.0.1 only, on a free port, shows it in a
window of the application, and stops the server when the user closes the window.

**Rationale**: A user opens a project from a window, like a word processor, without a
browser or a terminal. A server that listens on the loopback address only is not
reachable from the network, and no server is left running after the window is
closed.

### Session token of the desktop server

**MID**: 2552519420d349ac87c46d2605f8dabc \
**UID**: SDOC-SRS-1221 \
**Status**: Active

**Statement**: StrictDoc shall refuse with the HTTP status 403 every request to the desktop
server that does not carry a valid session cookie, and shall set that cookie
with the HttpOnly and SameSite=Strict attributes in answer to a single-use
bootstrap code. The server shall also refuse a WebSocket connection that comes
from another origin.

**Rationale**: Any local process or web page can send requests to a port on 127.0.0.1. The
session cookie restricts the server to the window that started it, and the
single-use code keeps the cookie out of the command line and the logs once the
window is open. A web page open in a browser of the computer must not be able to
open a WebSocket to the server.

### Host header check of the desktop server

**MID**: 1bc79a7105704c4abd8cd4514acd515d \
**UID**: SDOC-SRS-1222 \
**Status**: Active

**Statement**: StrictDoc shall refuse every request to the desktop server whose Host header
is neither `127.0.0.1:<port>` nor `localhost:<port>`, where `<port>` is the port
of the server.

**Rationale**: A DNS rebinding attack makes a hostile web page reach a local server under
the name of the attacker. Checking the Host header rejects such requests even
when the browser sends the cookie.

### Application settings file

**MID**: 9d93cf0b13e946e7bb900b97be7d966f \
**UID**: SDOC-SRS-1223 \
**Status**: Active

**Statement**: StrictDoc shall store the settings of the desktop application in a JSON file
in the configuration folder of the user, and shall write that file atomically.

**Rationale**: The settings belong to the user and not to a project. An atomic write
leaves the previous settings intact when the application stops during the
write.

### Secrets in the system keyring

**MID**: 07598bea13be4080a4a220c05a1a1389 \
**UID**: SDOC-SRS-1224 \
**Status**: Active

**Statement**: StrictDoc shall store the secrets of the desktop application, such as access
tokens, in the keyring of the operating system and never in the settings file.

**Rationale**: A settings file is readable by other tools and is easily copied or committed
by mistake. The system keyring protects a secret with the session of the user.

### Output and cache in the user cache folder

**MID**: 6e314a22bc6f425483af45c52c583271 \
**UID**: SDOC-SRS-1225 \
**Status**: Active

**Statement**: StrictDoc shall write the HTML output and the cache of a project opened by the
desktop application in the cache folder of the user, in one sub-folder per
project.

**Rationale**: The project folder stays free of generated files, and two projects never
share the same output or cache.

### Project catalog interface

**MID**: 019b824b1eb34238a4597363b3a00f18 \
**UID**: SDOC-SRS-1226 \
**Status**: Active

**Statement**: StrictDoc shall list the projects that the user can open through a generic
`ProjectCatalog` interface, and shall select the provider of that list by its
name in the settings of the desktop application.

**Rationale**: The source of the project list can change without a change to the screens
that show it. A name in the settings lets an installation pick its provider.

### GitLab project catalog

**MID**: 481f4a97de63460e87562bdfb5c838e4 \
**UID**: SDOC-SRS-1227 \
**Status**: Active

**Statement**: StrictDoc shall provide a project catalog that lists the GitLab projects of
the configured root group and of all its sub-groups on which the user has the
Reporter access level or a higher one.

**Rationale**: The projects of a team are spread over sub-groups. A user sees the projects
that GitLab lets them read, and no others.

### Role from the GitLab access level

**MID**: 6bb2cedfae694f3298aa860f8834a55a \
**UID**: SDOC-SRS-1228 \
**Status**: Active

**Statement**: StrictDoc shall give the user, on a project of the GitLab catalog, the
reader role for the Reporter access level, the author role for the Developer
access level, and the administrator role for the Maintainer and Owner access
levels, and shall not list a project on which the user is a Guest.

**Rationale**: The rights of a user on a document follow the rights that GitLab gives on
the project, so that the two never disagree.

### Empty start screen with the project catalog

**MID**: a067a7460fbd41b98441f641e22850b5 \
**UID**: SDOC-SRS-1229 \
**Status**: Active

**Statement**: StrictDoc shall start the desktop application on a screen with no open
project when the user has not yet opened a project, and shall show on that
screen the project catalog as a tree, with a search by project name.

**Rationale**: A new user has no project to open yet. The tree follows the organization of
the groups, and the search finds a project without browsing the tree.

### Choice of a folder for a project

**MID**: ab5bb59f5a7f48c9a43f0ed52b320651 \
**UID**: SDOC-SRS-1230 \
**Status**: Active

**Statement**: StrictDoc shall ask the user for a folder when the user opens a project for
the first time, shall clone the project into that folder when it is empty, shall
use the folder as is when it already contains the repository of the project, and
shall refuse any other folder with a message.

**Rationale**: The user chooses where the working copy lives. Cloning into a folder that
holds other files, or reusing the copy of another project, would mix or lose
data.

### Project and folder association

**MID**: 50e51af02fa84082b0bd37b4d3b6cdec \
**UID**: SDOC-SRS-1231 \
**Status**: Active

**Statement**: StrictDoc shall keep in the settings of the desktop application the folder
chosen for each project, and shall open a project with a known folder without
asking the user again.

**Rationale**: The choice of a folder is made once per project. The next launch goes
straight to the documents.

### Servers of the recent projects kept running

**MID**: d6b838d004ce4399a7f16fa47f91b460 \
**UID**: SDOC-SRS-1232 \
**Status**: Active

**Statement**: StrictDoc shall keep running the servers of the most recently opened
projects, in a number that the user can set in the settings of the desktop
application, shall stop the oldest one when that number is exceeded, and shall
show a project whose server is running in less than 0.5 second.

**Rationale**: A user moves often between a few projects. A server that is still running
makes the return to a project immediate, and the limit bounds the memory used.

### Background update of a project

**MID**: dc16964a4c134674aff06974d8a7fd42 \
**UID**: SDOC-SRS-1233 \
**Status**: Active

**Statement**: StrictDoc shall update the working copy of a project from its remote in the
background when the user opens the project, without delaying the display of the
project, and without showing an error to the user when the remote is not
reachable.

**Rationale**: The user sees the documents at once and gets the changes of the others as
soon as they arrive. Working offline stays possible.

### Sign-in through GitLab OAuth in the application window

**MID**: 78dc36e9fbf341f29598d400ddc8bf94 \
**UID**: SDOC-SRS-1234 \
**Status**: Active

**Statement**: StrictDoc shall sign the user in with the OAuth authorization code flow of GitLab,
with PKCE and a `state` value, shall receive the callback on the loopback
address of the computer, and shall show the sign-in page in the window of the
desktop application and not in the browser of the system. When the user signs
out, StrictDoc shall delete the cookies of the application window and revoke the
token of the user.

**Rationale**: PKCE and `state` protect the code against interception and forgery. The user
sees only the sign-in page of the identity provider, in the application. After
the sign-out, neither the window nor a copy of the token can open a session
again.

### Tokens in the keyring and renewal

**MID**: ec6e9681ccd7432fadb9d577ec344c46 \
**UID**: SDOC-SRS-1235 \
**Status**: Active

**Statement**: StrictDoc shall keep the access and refresh tokens of the user in the keyring of
the operating system, shall renew the access token before it expires, and shall
send the user back to the sign-in page when the renewal fails.

**Rationale**: The user stays signed in without a new login at each launch. A refused renewal
means that the access is gone, and the user has to sign in again.

### Desktop authentication mode

**MID**: d121afc34a0d43a888c8fcf0dd2b5355 \
**UID**: SDOC-SRS-1236 \
**Status**: Active

**Statement**: StrictDoc shall provide an authentication mode named `desktop` in which the user
of the project server is the GitLab user who signed in to the desktop
application.

**Rationale**: The server of a project knows who edits without a second account or a second
password.

### Role per project from the GitLab access level

**MID**: f1bf392233ca4740ab49c65b520f99bd \
**UID**: SDOC-SRS-1237 \
**Status**: Active

**Statement**: StrictDoc shall compute the role of the user on a project from the GitLab access
level of the user on that project, and shall compute it again each time the
user opens the project.

**Rationale**: An access level can change on GitLab while the application runs. Computing the
role at each opening keeps the rights of the user in line with GitLab.

### Author of the commits

**MID**: bd4adca7fef04edfbf17d96b484aaf5d \
**UID**: SDOC-SRS-1238 \
**Status**: Active

**Statement**: StrictDoc shall record the signed-in GitLab user as the author of the commits made
by the desktop application, and shall not use a default author.

**Rationale**: The history of a project shows who made each change. A default author would
hide it.

### Token passed to Git through the environment

**MID**: fb8a1dd1b6e84861be1732200b1ce652 \
**UID**: SDOC-SRS-1239 \
**Status**: Active

**Statement**: StrictDoc shall pass the GitLab access token to Git through the environment of
the Git process, and shall never write the token in a file, in the Git
configuration or in a remote address.

**Rationale**: A token written in a file or in a remote address is easy to copy and to leak. The
environment of one process lives only as long as that process.

### GitLab catalog after sign-in

**MID**: f8fccae9906b419a9be3d7516e0ec134 \
**UID**: SDOC-SRS-1240 \
**Status**: Active

**Statement**: StrictDoc shall use the GitLab project catalog as soon as the user is signed in,
with the access token of that user.

**Rationale**: The projects listed are those that GitLab lets this user read, with no separate
configuration of the catalog.

### Git with the token of the signed-in user only

**MID**: 1e964d01e44644798acaf89f043a7ec1 \
**UID**: SDOC-SRS-1241 \
**Status**: Active

**Statement**: StrictDoc shall give the token of the signed-in user to Git, in the desktop
application, only for the origin (scheme, host and port) of the GitLab session
of that user, and shall let no other credential helper supply or store a
credential for these Git commands.

**Rationale**: The token of the user must not reach another host, and a credential helper of
the computer must not take its place or store it.

### Transparent saving and sending

**MID**: 92238e725dcd4efb82869659c7b4263f \
**UID**: SDOC-SRS-1242 \
**Status**: Active

**Statement**: StrictDoc shall record each saved change of a document in the desktop
application as a commit and shall send that commit to the remote at once,
without making the user wait for the sending.

**Rationale**: The user saves as in a word processor. The sharing of the change happens in the
background.

### Queue of the commits not sent

**MID**: e0539a8fcdac4b06accf86bb9920de71 \
**UID**: SDOC-SRS-1243 \
**Status**: Active

**Statement**: StrictDoc shall keep each commit that was not sent until it is sent, including
after the application stops, shall try again when the network returns, and shall
send it only under the user who made it.

**Rationale**: Working offline must not lose a change. A commit sent under another user would
give a wrong author and wrong rights.

### Indicator of the changes not sent

**MID**: 2558ebaa8ec9437c82055d72e06744a2 \
**UID**: SDOC-SRS-1244 \
**Status**: Active

**Statement**: StrictDoc shall show a discreet indicator of the changes not sent, and shall
tell apart a wait for the network, a refusal of the server and a failure of the
saving.

**Rationale**: The user sees that a change is not shared yet and knows whether to wait, to ask
for an access or to call for help.

### Periodic synchronization

**MID**: 0ca55bd40e4e4c0c8c9a83848a97f184 \
**UID**: SDOC-SRS-1245 \
**Status**: Active

**Statement**: StrictDoc shall synchronize a project with its remote when the user opens it and
then every N minutes, with 5 minutes as the default value of N and with N set by
the user, and shall suspend the synchronization while a merge waits for the
user.

**Rationale**: The user receives the changes of the others without asking for them. A merge in
progress must not be disturbed by a new update.

### Updates and typing in progress

**MID**: 05020f7165bc4b87a9055b5f6064bf59 \
**UID**: SDOC-SRS-1246 \
**Status**: Active

**Statement**: StrictDoc shall apply an update of the working copy to the open documents in a
way that neither loses the text that the user is typing nor overwrites the
update with the old text of the screen.

**Rationale**: The server writes a whole document from memory. A careless update would erase
the typing of the user or the change of the others.

### Conflict and merge window

**MID**: af9af88902c34264a1e865ac80d30dc4 \
**UID**: SDOC-SRS-1247 \
**Status**: Active

**Statement**: StrictDoc shall open the merge window when a synchronization finds a conflict,
and shall send the resolution once the user has validated it. When the conflict
concerns a file that is not a document, StrictDoc shall keep the local version
of the file, and shall keep the version of the colleague on the computer,
outside of any commit.

**Rationale**: A conflict needs the choice of the user. The resolution is shared like any other
change. Only documents can be merged. For any other file, the user keeps the
local version and the other version is not lost.

### No Git vocabulary in the application

**MID**: 6f71e73dc71c4f8eb0867cc792dd4ca5 \
**UID**: SDOC-SRS-1248 \
**Status**: Active

**Statement**: StrictDoc shall not show Git vocabulary, such as commit, push, pull, branch or
rebase, nor the name GitLab, in the interface of the desktop application, and
shall not offer the comparison of Git revisions (DIFF).

**Rationale**: The users of the application are authors, not developers. The labels use the
vocabulary of their work. A comparison of revisions shows Git concepts that
they do not need.

### Publication of a version

**MID**: ffa1100a5f0e4fd1b24ea4dcd0bfb7a0 \
**UID**: SDOC-SRS-1249 \
**Status**: Active

**Statement**: StrictDoc shall provide a "Publish a version" action that creates the next
version tag of the project and sends it to the remote, and shall reserve that
action to the administrator of the project.

**Rationale**: A published version marks a state of the documents that the team agrees on. Only
the administrator decides it.

### Rights on the merge in the desktop application

**MID**: 22f8e397af5e48e1a5b1f9a8e0c88c98 \
**UID**: SDOC-SRS-1250 \
**Status**: Active

**Statement**: StrictDoc shall let, in the desktop application, an author and an administrator
update, resolve and abandon a merge, shall let a reader receive the updates
without sending anything, and shall keep the rules of the web server unchanged.

**Rationale**: An author must not stay blocked by a conflict on a document that the author
edits. A reader only follows the work of the others.

### Settings screen

**MID**: 0390e85fedfd45e7aac7e272729c4975 \
**UID**: SDOC-SRS-1252 \
**Status**: Active

**Statement**: StrictDoc shall provide a settings screen of the desktop application, always
accessible, with the language of the application and the interval of the
synchronization, and shall not make the language depend on the open project.

**Rationale**: The language belongs to the user, not to the project. Opening a project must not
change the language of the home page.

### Several AI servers

**MID**: a102d20c3d0a4fda91b125b7a283ed02 \
**UID**: SDOC-SRS-1253 \
**Status**: Active

**Statement**: StrictDoc shall let the user declare several AI servers, internal or external,
shall keep the key of each one in the keyring of the operating system, and shall
apply any change without restarting the application.

**Rationale**: A team may use a server of the company and a server of a provider at the same
time. A key written in a file is easy to leak.

### AI buttons only with a complete server

**MID**: bedc6d0386d54e10bf9b072c891d03e1 \
**UID**: SDOC-SRS-1254 \
**Status**: Active

**Statement**: StrictDoc shall show the AI buttons in the desktop application only when at
least one AI server is complete, that is a URL and a key for an external server,
and a URL for an internal server, whose key is optional.

**Rationale**: A button that cannot work only confuses the user.

### Policy of the external AI servers

**MID**: dcf92cb4abf54291adca7ca4c33e5390 \
**UID**: SDOC-SRS-1255 \
**Status**: Active

**Statement**: StrictDoc shall read the policy of the external AI servers from a file deployed
with the application, which the user cannot change, and shall use no external
server when that file is missing or invalid.

**Rationale**: The company decides what leaves its network. A missing policy must not let any
external server through. The Python configuration of a project is trusted code,
and this policy does not constrain it.

### Linux package

**MID**: fe207b355c9f4419abd63c85ac6d3958 \
**UID**: SDOC-SRS-1256 \
**Status**: Active

**Statement**: StrictDoc shall provide a `.deb` package that installs the desktop application
with its menu entry, that declares its system dependencies, and whose removal
deletes everything the package installed.

**Rationale**: The user installs the application with the usual tools of the system. A
removal that leaves files behind makes later installations unreliable.

### Windows installer

**MID**: 17a29fd2bac446dea948f96eeaaaed82 \
**UID**: SDOC-SRS-1257 \
**Status**: Active

**Statement**: StrictDoc shall provide a Windows installer for one user, which includes an
embedded Git (MinGit), and shall provide a signing step that stays off while
Windows is used for tests only.

**Rationale**: The installer needs no administrator rights and no Git on the computer. The
signing step is ready for the day Windows is delivered.

### PDF without a browser of the computer

**MID**: 944da7c1bcb64709b5c48f03356f2b1f \
**UID**: SDOC-SRS-1258 \
**Status**: Active

**Statement**: StrictDoc shall export the PDF of the desktop application with the headless
Chrome and the chromedriver of the package, without any download at run time,
and shall check at build time the SHA-256 sum of each embedded file.

**Rationale**: The PDF export works offline and does not depend on the browser of the user.
A wrong sum stops the build, so a modified file cannot be shipped.

### Version and updates

**MID**: 0df341d8299741468957bff52a3a3933 \
**UID**: SDOC-SRS-1259 \
**Status**: Active

**Statement**: StrictDoc shall show its version in the settings screen of the desktop
application, and shall not check for updates over the network.

**Rationale**: The user and the support know which version runs. The deployment tools of the
company deliver the updates, so the application makes no request for them.

## Graph database

**Type**: SECTION \
**MID**: 34b4abc6bb4649de9e56af31c229b0d1 \
**UID**: SECTION-SRS-Graph-database

### Traceability index

**MID**: 2c8d7940a23c443f81a7eb373340894e \
**UID**: SDOC-SRS-28 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-7`

**Statement**: StrictDoc shall maintain a complete Traceability Index of all documentation- and
requirements-related information available in a project tree.

### Uniqueness UID in tree

**MID**: 272b8933276d4cd48a78fcfa11899573 \
**UID**: SDOC-SRS-29 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-89`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-94`

**Statement**: For each requirement node, the Traceability Index shall ensure its uniqueness
throughout the node's lifecycle.

**Rationale**: The requirement ensures that the Traceability Index takes of care of validating
the uniqueness of all nodes in a document/requirements graph.

### Detect links cycles

**MID**: 8330d61fd5b1438fa90f127f88903a0d \
**UID**: SDOC-SRS-30 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-47`
- **Type**: `File` \
  **Path**: `strictdoc/core/tree_cycle_detector.py`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-94`

**Statement**: The Traceability Index shall detect cycles between requirements.

### Link document nodes

**MID**: 07a1e7bef11d4fcca86cd31ee5245d8d \
**UID**: SDOC-SRS-32 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-47`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-13`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-14`

**Statement**: The Traceability Index shall recognize and maintain the relations between all
documents of a project tree.

**Rationale**:

The relations between all documents are a summary of all relations between these
documents' requirements. This information is useful for:

1) Structural analysis of a requirements/documents graph.
2) Incremental regeneration of only those documents whose content was modified.

### Automatic resolution of reverse relations

**MID**: 2dad5f293bc442eaa98859c4b5eac0d5 \
**UID**: SDOC-SRS-102 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-71`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-48`

**Statement**:

The StrictDoc's graph database shall maintain the requirement relations and
their reverse relations as follows:

- For a Parent relation, the database shall calculate the reverse Child
  relation.
- For a Child relation, the database shall calculate the reverse Parent
  relation.

**Rationale**: The calculation of the reverse relations allows the user interface code to get
and display both requirement's parent and child relations.

**Comment**:

Example: If a child requirement REQ-002 has a parent requirement REQ-001, the
graph database first reads the link `REQ-002 -Parent> REQ-001`, then it
creates a corresponding `REQ-001 -Child> REQ-002` on the go. Both relations
can be queried as follows, in pseudocode:

```
get_parent_requirements(REQ-002) == [REQ-001]
get_children_requirements(REQ-001) == [REQ-002]
```

## Documentation tree

**Type**: SECTION \
**MID**: 4dce611287954289b1c2a6a15c413611

### Finding documents recursively

**MID**: 50b2d5d6eb1140f0a2b980203468a5f7 \
**UID**: SDOC-SRS-115 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-34`
- **Type**: `Parent` \
  **ID**: `DO178-3`

**Statement**: StrictDoc shall discover SDoc documents recursively based on a specified input
path.

**Rationale**: Recursive search allows working with documents located in multiple folders,
potentially spanning over several Git repositories.

## Web/HTML frontend

**Type**: SECTION \
**MID**: fcbf717009ce4cb2a8def7eb7b377654 \
**UID**: SECTION-SRS-Web-HTML-frontend

### General export requirements

**Type**: SECTION \
**MID**: a3603184d571449792f5cd752c978686 \
**UID**: SECTION-SRS-General-export-requirements-2

#### Export to static HTML website

**MID**: 37f17fdd57ff47e9b7f4147adaeabde1 \
**UID**: SDOC-SRS-49 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-30`
- **Type**: `File` \
  **Path**: `strictdoc/export/html/html_generator.py`

**Statement**: StrictDoc shall support generating requirements documentation into static HTML.

#### Web interface

**MID**: 37399be2a8ac46889e3437209f9dffa9 \
**UID**: SDOC-SRS-50 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-31`
- **Type**: `Parent` \
  **ID**: `DO178-6`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-79`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-80`
- **Type**: `File` \
  **Path**: `strictdoc/server/app.py`
- **Type**: `File` \
  **Path**: `strictdoc/server/routers/main_router.py`

**Statement**: StrictDoc shall provide a web interface.

#### Multi-user editing of documents

**MID**: f97dc050ddab4a08bf1689200118faaa \
**UID**: SDOC-SRS-123 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `DO178-17`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-81`

**Statement**: StrictDoc shall support concurrent use and editing of a single StrictDoc web
server instance by multiple users.

#### Preserve generated file names

**MID**: 8811f0ef33de4365bc66a602a8c184f6 \
**UID**: SDOC-SRS-48 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-80`

**Statement**: For all export operations, StrictDoc shall maintain the original filenames of
the documents when producing output files.

**Rationale**: Name preservation helps to visually identify which input file an output file
corresponds to.

### Screen: Project tree

**Type**: SECTION \
**MID**: b99ebebdadb94fec968785429cef9002 \
**UID**: SECTION-SRS-Screen-Project-tree

#### View project tree

**MID**: 100fa410f4b443e69c48738899cfb5bd \
**UID**: SDOC-SRS-53 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-91`

**Statement**: StrictDoc's "Project tree" screen shall provide browsing of a documentation
project tree.

**Rationale**: This screen is the main tool for visualizing the project tree structure.

#### Create document

**MID**: eb04abcfd64146f3b7be509afd1693f9 \
**UID**: SDOC-SRS-107 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-3`

**Statement**: StrictDoc's Project Tree screen shall allow creating documents.

#### Delete document

**MID**: de7cda1156e043d7999933a2df630a30 \
**UID**: SDOC-SRS-108 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-3`

**Statement**: StrictDoc's Project Tree screen shall allow deleting documents.

### Navigation

**Type**: SECTION \
**MID**: 9051dac14e9c4080ad433c5c102126b2 \
**UID**: SECTION-SRS-Navigation

#### Sidebar groups

**MID**: f37c01700de3410793f418281988d388 \
**UID**: SDOC-SRS-1208 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-91`

**Statement**: StrictDoc's sidebar shall group the links to the screens of a project by
purpose: analysis, review, versions and administration. A group without
links shall not be shown.

**Rationale**: A flat list of screens grows with every feature. Groups let a user find a
screen by what it is for, and keep the administration apart from the daily
work.

#### Location of a document

**MID**: a409ac97218d40dba56e61d83ed73e3d \
**UID**: SDOC-SRS-1209 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-91`

**Statement**: On every screen of a document, StrictDoc shall show the title of the project
and the folders that hold the document, from the root of the document tree.

**Rationale**: Two documents can have the same title in different folders. The location
tells the user which one is open.

#### Version of a document

**MID**: ad80d79c75f04a64a60ce1ea2472b13f \
**UID**: SDOC-SRS-1210 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-75`

**Statement**: When the GIT feature is activated, StrictDoc shall show on every screen of a
document the latest version tag of the Git repository that holds the
document, or that the repository has no version tag.

**Rationale**: A reader must know whether the text on the screen is a released version or
work in progress.

#### Screens in the frame of the project

**MID**: 6e19316108704fb6aaf551eec43c15f9 \
**UID**: SDOC-SRS-1211 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-91`

**Statement**: StrictDoc's web server shall show every screen of a project with the
sidebar and the page header of the project, and the sidebar shall link to
every screen that the project activates.

**Rationale**: A screen without the sidebar leaves the user with no way back and no sign
of the project they are in. A screen that no link reaches is only found by
those who know its address.

#### Actions that the role does not allow

**MID**: ac0078efef484878a1934a0c019263d7 \
**UID**: SDOC-SRS-1212 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-80`

**Statement**: StrictDoc's web server shall show an action that the role of the user does
not allow as disabled, with the role that the action needs, and shall do
nothing when the user activates it. A screen that the role does not allow
shall say why and link back to the project, in the frame of the project.

**Rationale**: A hidden action tells the user nothing: they do not know that it exists,
nor whom to ask. A disabled action with its reason does.

#### Page of an item

**MID**: ca1b47d75302400aa97519c744abad60 \
**UID**: SDOC-SRS-1213 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-91`

**Statement**: StrictDoc's web server shall show one page per item, with its content, its
links grouped by relation role, its comments and its history in Git, and a
link back to the item in its document. A tab that the project cannot fill
shall be disabled and say why.

**Rationale**: A reader who follows a UID wants to see the item with its links and its
history, without scrolling through the whole document.

#### Simple search

**MID**: dea380e50aed4dee98e3746d215b3e3b \
**UID**: SDOC-SRS-1214 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-95`

**Statement**: When a user searches for a text that is exactly the UID of an item, the web
server shall open the page of that item. The search screen shall offer the kind
of the item, its status and its links as choices, and shall search with the
query that these choices make, together with the text if there is one.

**Rationale**: Most searches look for one known item or for the items of one kind and
status. The query language does that, but a user who does not know it should
not need it.

#### Versions of a document

**MID**: ce411ac26a194ae790c096e03ea3b26c \
**UID**: SDOC-SRS-1215 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-91`

**Statement**: Where the project uses the GIT feature, the web server shall list the version
tags of a document with their date, show the items of the document as they
were at a tag without changing any file, and compare two tags by listing the
items that were added, removed or changed between them.

**Rationale**: A reviewer who receives version B of a document needs to know what changed
since version A, and to read version A again.

#### Layout on a narrow screen

**MID**: 87f09186a8464886b41df190cb8bce04 \
**UID**: SDOC-SRS-1216 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-91`

**Statement**: While the width of the screen is 768 pixels or less, StrictDoc's web server
shall show the content of a screen alone, with a button that switches to the
sidebar and back. The screens that open in the frame of the project, and the
project home, shall not scroll sideways.

**Rationale**: A reviewer who opens an item from a phone has no room for a sidebar next to
the text.

### Screen: Document (DOC)

**Type**: SECTION \
**MID**: 185cfc2d1ed4429ebaf0689f70a8cb0a \
**UID**: SECTION-SRS-Screen-Document-DOC

#### Format-specific document handling

**MID**: 93e6f08c949a48fa98cf86288492d8fd \
**UID**: SDOC-SRS-201 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-3`

**Statement**:

StrictDoc's Document screen shall arrange all CRUD operations according to the
input document format.

Example: If an SDoc document is read from a Markdown file using a dedicated
reader, it shall be written back using a Markdown writer.

#### Read document

**MID**: 9c962637ef7f45b6af6c83964b0a06d9 \
**UID**: SDOC-SRS-54 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-3`

**Statement**: StrictDoc's Document screen shall allow reading documents.

#### Create node

**MID**: 201187122be14ea48d69106d396c6790 \
**UID**: SDOC-SRS-106 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-3`

**Statement**: StrictDoc's Document screen shall allow creating document nodes.

#### Clone node from existing node

**MID**: 9b291b5df5914f13b23fb8c367be0a24 \
**UID**: SDOC-SRS-161 \
**Status**: Active

**Statement**: StrictDoc shall support cloning regular, non-composite document nodes from
existing nodes.

**Rationale**: Simplifies the creation of similar nodes.

#### Update node

**MID**: 13968ae160744e10ba8979eaee2f4f54 \
**UID**: SDOC-SRS-55 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-4`

**Statement**: StrictDoc's Document screen shall allow update document content.

#### Delete node

**MID**: 0ec87f08626a4839b5951d98fef9e0e1 \
**UID**: SDOC-SRS-162 \
**Status**: Active

**Statement**: StrictDoc's Document screen shall support the deletion of document nodes.

#### Create node relation

**MID**: b805e36294764e8f8cb5a88ab8fa0467 \
**UID**: SDOC-SRS-159 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-7`

**Statement**: StrictDoc's Document screen shall creating updating node relations.

#### Update node relation

**MID**: f32c091454c94bc5bd2091e2c4f38582 \
**UID**: SDOC-SRS-158 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-7`

**Statement**: StrictDoc's Document screen shall allow updating node relations.

#### Move requirement / section nodes within document

**MID**: edc02a3a97704007b70b93102c76b278 \
**UID**: SDOC-SRS-92 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-5`

**Statement**: StrictDoc's Document screen shall provide a capability to move the nodes within
a document.

**Rationale**: Moving the nodes within a document is a convenience feature that speeds up the
requirements editing process significantly.

#### Move requirement / section nodes between documents

**MID**: 7a06d1433e4c4b0eaf55ede14507eac9 \
**UID**: SDOC-SRS-94 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-70`

**Statement**: StrictDoc's Document screen shall provide a capability to move the nodes between
documents.

**Rationale**: Moving the nodes within a document is a convenience feature that speeds up the
requirements editing process significantly.

#### Edit Document grammar

**MID**: 197e00dd3b1d42309250c89de23ea51b \
**UID**: SDOC-SRS-56 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-62`

**Statement**: StrictDoc's screen shall allow editing a document's grammar.

**Rationale**: Editing document grammar allows a user to customize the requirements fields.

#### Edit Document options

**MID**: 2706ac7ccb8148edb7b200a1b78c25d6 \
**UID**: SDOC-SRS-57 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-93`

**Statement**: StrictDoc's Document screen shall provide controls for configuring the
document-specific options.

#### Auto-generate requirements UIDs

**MID**: d64f7a0f6ba54672a62634304c54e2d4 \
**UID**: SDOC-SRS-96 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-6`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-80`
- **Type**: `File` \
  **Path**: `strictdoc/core/analyzers/document_uid_analyzer.py`
- **Type**: `File` \
  **Path**: `strictdoc/commands/manage_autouid_command.py`

**Statement**: StrictDoc's Document screen shall provide controls for automatic generation of
requirements UIDs.

#### Auto-completion for requirements UIDs

**MID**: 956371b6a7824d0b91caa5603faeeae2 \
**UID**: SDOC-SRS-120 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-6`
- **Type**: `Parent` \
  **ID**: `DO178-14`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-80`

**Statement**: StrictDoc's Document screen shall provide controls for automatic completion of
requirements UIDs.

**Comment**: The automatic completion can be especially useful when a user has to fill in a
parent relation UID.

#### Buttons to copy text to buffer

**MID**: 738b63b7f55b43eb99f5600bd65f5ba7 \
**UID**: SDOC-SRS-59 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-80`
- **Type**: `File` \
  **Path**: `strictdoc/export/html/_static/copy_to_clipboard.js`

**Statement**: StrictDoc shall provide a "copy text to buffer" button for all requirement's
text fields.

### Screen: Table (TBL)

**Type**: SECTION \
**MID**: 2b5d74dafd6d43f4bab4c05ed4da6f0d \
**UID**: SECTION-SRS-Screen-Table-TBL

#### View TBL screen

**MID**: e12b4c5b4f13444d99279ab445df5bcc \
**UID**: SDOC-SRS-62 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-73`
- **Type**: `File` \
  **Path**: `strictdoc/export/html/generators/document_table.py`

**Statement**: StrictDoc's Table screen shall allow reading documents in a table-like manner.

### Screen: Traceability (TR)

**Type**: SECTION \
**MID**: 3c589969eb6a41c19b1dd246dabadbc8 \
**UID**: SECTION-SRS-Screen-Traceability-TR

#### View TR screen

**MID**: 35d4c1dd30814c2a80918a90081a88b7 \
**UID**: SDOC-SRS-65 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-28`

**Statement**:

StrictDoc shall provide a single document-level traceability screen.

NOTE: This screen helps to read a document like a normal document while the
traceability to this document's parent and child elements is visible at the same
time.

### Screen: Deep traceability (DTR)

**Type**: SECTION \
**MID**: 9d337068b6a940b7a98d40697ea200a8 \
**UID**: SECTION-SRS-Screen-Deep-traceability-DTR

#### View DTR screen

**MID**: 48bc17d898c94605b17d0267480f57ee \
**UID**: SDOC-SRS-66 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `DO178-12`

**Statement**: StrictDoc shall provide a deep traceability screen.

### Screen: HTML2PDF

**Type**: SECTION \
**MID**: 181dfbcbbfac41e18f7fb09af0df8f4e

#### Export to HTML content to PDF (HTML2PDF)

**MID**: f2fd90ad8a2946e7b085233a9c7a8a75 \
**UID**: SDOC-SRS-51 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `DO178-5`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-96`

**Statement**: StrictDoc shall allow exporting documents and entire documentation trees to PDF.

**Rationale**: As required by the parent requirement, PDF is one of the most common
documentation formats.

#### Cross-linking PDF documents from same project tree

**MID**: 50eabada50be47a1938e55fc10814972 \
**UID**: SDOC-SRS-203 \
**Status**: Active

**Statement**: When exporting multiple HTML documents from a same project tree into PDF,
StrictDoc shall preserve all cross-document linking in the output PDF documents.

**Rationale**: This enables navigation between PDF documents within the same project tree,
which can be useful for simplifying the review and tracing work performed by
readers.

#### Custom PDF export template

**MID**: 6cfcb21b3f1949f49d13af6b00d3d37a \
**UID**: SDOC-SRS-160 \
**Status**: Active

**Statement**: StrictDoc shall support the customization of the PDF export template.

### Screen: Project statistics

**Type**: SECTION \
**MID**: ddf15b3113a54107979752ec192e2ded

#### Display project statistics

**MID**: 19f7c2d35237423e950584a4a7aa95a7 \
**UID**: SDOC-SRS-97 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-49`
- **Type**: `Parent` \
  **ID**: `DO178-12`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-29`

**Statement**:

StrictDoc shall provide a Project Statistics screen that displays the following
project information:

- Project title
- Date of generation
- Git revision
- Total documents
- Total requirements
- Requirements status breakdown
- Total number of TBD/TBC found in documents.

**Rationale**: TBD

#### Support for user-provided custom statistics generators

**MID**: 7968fb7612f64504b5a430ccbffe80f1 \
**UID**: SDOC-SRS-154 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-49`

**Statement**: StrictDoc shall support customization of the project statistics screen, enabling
users to define and display their own project-specific statistics.

**Rationale**: Projects often have unique traceability and reporting requirements, and
supporting custom statistics allows StrictDoc to display metrics that are most
relevant to each project's context.

### Screen: Document tree map

**Type**: SECTION \
**MID**: d84e3a79b3e443cabe96d7c18ea5d322

#### Tree map

**MID**: 1520fa85ed7a4f1aa80c49ed858f402f \
**UID**: SDOC-SRS-157 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-29`

**Statement**:

StrictDoc shall provide a tree map screen, visualizing the following
information:

- Document tree map
- Requirements coverage by source code
- Requirements coverage by test files.

**Rationale**: Enables the visualization and browsing of the overall document tree and
requirements coverage information.

### Screen: Source coverage

**Type**: SECTION \
**MID**: 63df985038374acb82e9b4185eff5a7e

#### Project source code coverage

**MID**: 3aeb1eea0dba4041a9161a1a8d291999 \
**UID**: SDOC-SRS-35 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-72`
- **Type**: `Parent` \
  **ID**: `DO178-13`

**Statement**:

StrictDoc shall generate project source code coverage information.

NOTE: Source code information can be visualized using both web or CLI
interfaces.

### Screen: Single source file coverage

**Type**: SECTION \
**MID**: 9c19eea544ec4d90bb65fd8fd9b13cc4

#### Single source file coverage

**MID**: 56ecfb19152e45b09c0e55de2d1d5f05 \
**UID**: SDOC-SRS-36 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-72`

**Statement**: StrictDoc shall generate single file traceability information.

**Rationale**: With this capability in place, it is possible to focus on a single
implementation file's links to requirements which helps in the code reviews and
inspections.

### Screen: Traceability matrix

**Type**: SECTION \
**MID**: 14ad600308434e6baaeef02d3e90b720

#### Traceability matrix

**MID**: 167f6fe66d7247a6bf628ed6c1949275 \
**UID**: SDOC-SRS-112 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-28`
- **Type**: `Parent` \
  **ID**: `DO178-10`
- **Type**: `Parent` \
  **ID**: `DO178-12`

**Statement**: StrictDoc shall provide a traceability matrix screen.

### Screen: Project tree diff

**Type**: SECTION \
**MID**: 544f8ffed8604e63a269a3f953681163

#### Project tree diff

**MID**: aef80cc1a3144564bf23bf3c2a1cfd7f \
**UID**: SDOC-SRS-111 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-75`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-74`
- **Type**: `Parent` \
  **ID**: `DO178-15`

**Statement**: StrictDoc shall provide a project tree diff screen.

### Content search

**Type**: SECTION \
**MID**: 8380fb39beb04d1c9370733bcfafbc01

#### Content search

**MID**: 3e85dd6bf05a4cecb8e070fd81aa333a \
**UID**: SDOC-SRS-155 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-95`

**Statement**: StrictDoc shall provide searching documentation content with queries via a
search bar.

**Rationale**: As per the parent requirement, a search bar with query support enables users to
interactively find specific content without navigating the entire documentation
tree.

## Requirements-to-source traceability

**Type**: SECTION \
**MID**: 2d4dc6fc901f4b28aaf414fcfbdfabca \
**UID**: SECTION-SRS-Requirements-to-source-traceability

### Link requirements with source files

**MID**: 221b544dab2e4b96be124e1caf84a7c2 \
**UID**: SDOC-SRS-33 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-72`

**Statement**: StrictDoc shall support bi-directional linking requirements with source files.

### Language-aware parsing of source code

**Type**: SECTION \
**MID**: 2f63252320d546d88462849b521f45ba

#### Language-aware parsing of source code

**MID**: 79a8080f6e41485f9835ccda067b34bc \
**UID**: SDOC-SRS-142

**Statement**:

StrictDoc shall support parsing the most commonly used formats and programming
languages to the Abstract Syntax Tree (AST) level.

The format examples: C, C++, Python, Rust, Ada, Robot, Gherkin, etc.

**Rationale**: StrictDoc must be capable of traversing the AST of common formats and
programming languages to identify and extract function and class markers.

#### Language-aware parsing of C/C++ code

**MID**: 85a8080f8441485f9111ccda063b34bc \
**UID**: SDOC-SRS-146 \
**Status**: Active

**Statement**:

StrictDoc shall support parsing the C and C++ source files which includes:

- Recognizing functions and their Doxygen comments.
- Recognizing function declarations and function definitions.

**Rationale**: C and C++ languages are common languages for embedded and general systems
programming. These languages have to be handled with a dedicated parser because
of these languages' specifics.

#### Language-aware parsing of Python code

**MID**: 3456080f1358485f9bacdcda063b34bc \
**UID**: SDOC-SRS-147 \
**Status**: Active

**Statement**:

StrictDoc shall support parsing the Python source files which includes:

- Recognizing Python functions, including nested functions.
- Recognizing Python classes, including nested classes.
- Recognizing decorated functions.

**Rationale**: Python language has to be handled with a dedicated parser because of this
language's specifics.

#### Language-aware parsing of Rust code

**MID**: e71074247fbe47bfb5265f3bd631170f \
**UID**: SDOC-SRS-204 \
**Status**: Active

**Statement**: StrictDoc shall support parsing the Rust source files.

**Rationale**: Rust language has to be handled with a dedicated parser because of this
language's specifics.

#### Language-aware parsing of Robot framework code

**MID**: 9183080f1358485f9bacdcda0635109 \
**UID**: SDOC-SRS-148 \
**Status**: Active

**Statement**: StrictDoc shall support parsing the Robot framework test files.

**Rationale**: Robot framework's markup has to be handled with a dedicated parser because of
this language's specifics.

### Link requirements with test files and test reports

**MID**: bdeda4b89d82446281e2c7c2eae46708 \
**UID**: SDOC-SRS-143 \
**Status**: Active

**Statement**: StrictDoc shall support bi-directional linking between requirements, test files,
and test reports.

**Rationale**: Tracing requirements to not just test files but also the test report information
closes the verification cycle more completely.

### Link requirements with code coverage information

**MID**: aefeb5b89d82446281e2c7c2eae12345 \
**UID**: SDOC-SRS-144 \
**Status**: Active

**Statement**: StrictDoc shall support linking between requirements, source files, and code
coverage information.

**Rationale**: Tracing requirements to not just test files but also to the code coverage
information closes the verification cycle more completely.

### Forward linking from requirements to source code

**Type**: SECTION \
**MID**: 5fedbaba39d24da79d074501198ff654

#### SDoc markup's forward relations

**MID**: 21637d9bec434d32bb6b97ba5a4e70e6 \
**UID**: SDOC-SRS-145

**Statement**: StrictDoc shall support forward linking from SDoc nodes to source files.

**Rationale**: There are cases when it is not possible to modify source code directly. The
forward linking enables to refer to the files or their parts from SDoc nodes.
Depending on a project structure, the forward linking from requirements to
source files can replace the backward linking from source code back to
requirements, or both approaches can co-exist.

### Source code markup – Relations

**Type**: SECTION \
**MID**: 9c1dd6cbabd44ac680985c403cf710a7

#### Relation markers syntax

**MID**: b9144222a7f3454da2989f494cd9647c \
**UID**: SDOC-SRS-34 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-72`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc_source_code/grammar.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc_source_code/reader.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc_source_code/models/range_marker.py`
- **Type**: `File` \
  **Path**: `strictdoc/backend/sdoc_source_code/models/source_file_info.py`

**Statement**: StrictDoc shall support annotating source code with links that reference the
requirements.

#### Line marker

**MID**: 61c25cab106e4283b2c6d64bf1db96b2 \
**UID**: SDOC-SRS-124 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-72`

**Statement**:

StrictDoc's shall support line markers that can be attached to single source
code lines.

NOTE: A single-line marker points to a single line in a source file.

**Rationale**: Sometimes a requirement can influence only a single line in the source code. The
advantage of a single-line marker compared to a range marker is that a
single-line marker is not intrusive and does not clutter source code.

#### Language element marker

**MID**: 61c23c1b106e4583b2c6d64bf1d296ba \
**UID**: SDOC-SRS-137 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-72`

**Statement**:

StrictDoc shall support relation markers that can be attached to individual
source code elements. StrictDoc shall support an optional scope attribute to
disambiguate the target element where StrictDoc can't infer it solely from the
marker position.

Note: The most basic example of such traceable elements are functions and
classes, but generally supported elements and available scope attributes depend
on the programming language.

**Rationale**:

Source code elements can often be considered as the next level to trace from a
requirement. For example, a low level element is implemented by a function, or a
test case is implemented by a test function.

Sometimes it's also feasible to consider the source code elements as lean
replacement for prose requirement or test-case definitions.

#### File marker

**MID**: 82345cab106e4283b2c7774bf1db96b1 \
**UID**: SDOC-SRS-139 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-72`

**Statement**: StrictDoc's shall support file markers that can be attached to entire source
files.

**Rationale**: There are cases when a requirement can be attached to an entire file.

#### Range marker

**MID**: 11c23c1b105e4583b2c6d64bf1d296cc \
**UID**: SDOC-SRS-138 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-72`

**Statement**:

StrictDoc shall support relation markers that can be attached to source code
ranges.

NOTE: Compared to other marker types, to indicate a range, two markers are
needed: one to start a range and one to end a range.

**Rationale**: There are cases when a requirement implementation results in the requirement
affecting only a range/block of source code.

### Source code markup – Nodes

**Type**: SECTION \
**MID**: 5ce2ea410dd94927807a258f482483a5

#### Parse nodes from source code

**MID**: f44df3c6a84f4b4e9201a61023446d9c \
**UID**: SDOC-SRS-141 \
**Status**: Active

**Statement**: StrictDoc shall support parsing nodes from source code.

**Rationale**:

It can be practical to define the requirement and other nodes directly in source
comments and then let a requirements tool generate documents from these nodes'
content automatically.

A reference example: Generating test specifications from the TEST_SPEC nodes
which are defined directly in source code comments.

## Export/import formats

**Type**: SECTION \
**MID**: 1acdd6ddf9d24dbaa320230402152226 \
**UID**: SECTION-SRS-Export-import-formats

### ReqIF

**Type**: SECTION \
**MID**: a906dfb776334b8985f778f0fe1b79e4 \
**UID**: SECTION-SRS-ReqIF

#### Export/import from/to ReqIF

**MID**: 2bf94015818e4770b2b1947b5fdbb969 \
**UID**: SDOC-SRS-72 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-58`

**Statement**: StrictDoc shall support exporting/importing requirements content from/to ReqIF
format.

#### Standalone ReqIF layer

**MID**: bb52b698d7a544aca420d606e4e51356 \
**UID**: SDOC-SRS-73 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-90`

**Statement**: StrictDoc shall maintain the core ReqIF implementation as a separate software
component.

**Rationale**: ReqIF is a well-defined standard which exists independently of StrictDoc's
development. It is reasonable to maintain the ReqIF codebase as a separate
software component to allow independent development and easier maintainability.

### Excel and CSV

**Type**: SECTION \
**MID**: 0ffda51372b641f6ba460bf5ac8b3627 \
**UID**: SECTION-SRS-Excel

#### Export to Excel

**MID**: f7b587f66dda402dbd58768e2740742f \
**UID**: SDOC-SRS-74 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-60`
- **Type**: `File` \
  **Path**: `strictdoc/backend/excel/export/excel_generator.py`
- **Type**: `File` \
  **Path**: `tests/integration/features/excel/export/20_excel_export_multiple_docs/test.itest`

**Statement**: StrictDoc shall allow exporting SDoc documents to Excel, one Excel sheet per
document.

#### Import from Excel

**MID**: 97b587f66dda402dbd58768e2740742f \
**UID**: SDOC-SRS-152 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-60`
- **Type**: `File` \
  **Path**: `strictdoc/backend/excel/export/excel_generator.py`
- **Type**: `File` \
  **Path**: `tests/integration/features/excel/export/20_excel_export_multiple_docs/test.itest`

**Statement**: StrictDoc shall allow importing Excel documents to SDoc documents, one Excel
sheet per document.

#### Selected fields export

**MID**: 5aa75848972249d5bec8a40812b99d86 \
**UID**: SDOC-SRS-134 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-60`
- **Type**: `File` \
  **Path**: `tests/integration/features/excel/export/03_custom_fields_to_export/test.itest`

**Statement**: StrictDoc Excel export shall allow exporting SDoc documents to Excel with only
selected fields.

## Command-line interface

**Type**: SECTION \
**MID**: 53cfa6296eec45479544e6c5165d7fb9 \
**UID**: SECTION-SRS-Command-line-interface

### General CLI requirements

**Type**: SECTION \
**MID**: 63373c3875404f1c820add84ea057c73

#### Command-line interface

**MID**: 598647eed3a446fe93e2c54b197f830e \
**UID**: SDOC-SRS-103 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-32`
- **Type**: `File` \
  **Path**: `strictdoc/cli/main.py`
- **Type**: `File` \
  **Path**: `strictdoc/cli/cli_arg_parser.py`

**Statement**: StrictDoc shall provide a command-line interface.

### Command: Manage

**Type**: SECTION \
**MID**: 7c6a0efe76b84dcd842ef371796e787e \
**UID**: SECTION-SRS-Command-Manage

#### Command: Auto UID

**Type**: SECTION \
**MID**: bea76afe9bf241eaaf5984b54e00ff76 \
**UID**: SECTION-SRS-Command-Auto-UID

##### Auto-generate requirements UIDs

**MID**: 7daa1310876a421f8e39f8ac25b99c1d \
**UID**: SDOC-SRS-85 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-6`

**Statement**: StrictDoc shall allow automatic generation of requirements UIDs.

## Python API

**Type**: SECTION \
**MID**: a0ed7cdd06ec4f0ab6d3ba56cced8c7e

### StrictDoc Python API

**MID**: a20c5b6a021f4dd5a5a5dda2880c1b87 \
**UID**: SDOC-SRS-125 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-79`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-86`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-87`

**Statement**:

StrictDoc shall provide a Python API for its core functions:

- Reading SDoc files
- Creating traceability graph
- Generating HTML exports
- Converting SDoc to other formats.

## Web server

**Type**: SECTION \
**MID**: 590121ded2074757aa1720b4d8013426

### Web server

**MID**: 409f462f1f4645c8ad24980727a72521 \
**UID**: SDOC-SRS-126 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-83`

**Statement**: StrictDoc shall provide a web server.

**Rationale**: A web server is a precondition for StrictDoc's web interface. A web server can
be available to a single user on their local machine or it can be deployed to a
network and be made accessible by several computers.

## User experience

**Type**: SECTION \
**MID**: 44eb09d0e5b542d5984d234167e6f337

### StrictDoc identification

**MID**: 2bfb3703b218411b87864733bffb59cf \
**UID**: SDOC-SRS-163 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-97`

**Statement**: StrictDoc shall provide 'about' and 'version' commands that display the
project's title, current version, license, and links to the project's web pages.

### Strict mode by default

**Type**: SECTION \
**MID**: 821c01118a9643a188a4ecc5b0cec6a5 \
**UID**: SECTION-SSRS-Strict-mode-by-default

#### Warnings are errors

**MID**: c4e9dce647654deeab8471d04573f8cb \
**UID**: SDOC-SRS-6 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`

**Statement**: StrictDoc's default mode of operation shall treat all warnings as errors.

**Rationale**: When warnings are treated as errors, the user becomes aware of potential issues
as soon as they appear.

## Configurability

**Type**: SECTION \
**MID**: 40e7bd8aabdf4cb889e9d7b01b8729e6 \
**UID**: SECTION-SRS-Configurability

### Python configuration file

**MID**: 8777318f4a5b481596ac1f43e73b24c9 \
**UID**: SDOC-SRS-205 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-92`

**Statement**: StrictDoc shall allow configuration of projects settings using a Python file.

### Feature toggles

**MID**: a6e70c0619204a26b135d1e5fca45dd7 \
**UID**: SDOC-SRS-39 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-92`

**Statement**: StrictDoc shall allow a user to select a subset of StrictDoc's available
features by listing them in the Python configuration file.

### 'Host' parameter

**MID**: a8a17295d3e24601891c7d19d5ca67d9 \
**UID**: SDOC-SRS-119 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `DO178-8`

**Statement**: StrictDoc shall support configuring a host/port on which the StrictDoc web
server is run.

## Performance

**Type**: SECTION \
**MID**: bb14fb2c46f34cf1a82b417b57e95853 \
**UID**: SECTION-SSRS-Performance

### Process-based parallelization

**MID**: acd97ca6b9d2451da53168917d96705e \
**UID**: SDOC-SRS-1 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-13`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-14`

**Statement**: StrictDoc shall support process-based parallelization for time-critical tasks.

**Rationale**: Process-based parallelization can provide a good speed-up when several large
documents have to be generated.

### Caching of parsed SDoc documents

**MID**: 54602f6d120548c8bbd70d1d25113d53 \
**UID**: SDOC-SRS-95 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-13`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-14`

**Statement**: StrictDoc shall implement caching of parsed SDoc documents.

### Incremental generation of documents

**MID**: 6fec2f8c0baa4ddba95bee05ad03a785 \
**UID**: SDOC-SRS-2 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-13`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-14`

**Statement**:

StrictDoc shall support incremental generation of documents.

NOTE: "Incremental" means that only the modified documents are regenerated when
StrictDoc is run repeatedly against the same project tree.

### On-demand loading of HTML pages

**MID**: d0c4828ed8434613aae844481bbef1ca \
**UID**: SDOC-SRS-4 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-13`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-14`

**Statement**: StrictDoc's web interface shall generate the HTML content only when it is
directly requested by a user.

**Rationale**: Generating a whole documentation tree for a user project can be time consuming.
The on-demand loading ensures the "do less work" approach when it comes to
rendering the HTML pages.

### Precompiled Jinja templates

**MID**: 4e014d3291ce460c993a0ff334eff4a7 \
**UID**: SDOC-SRS-5 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-13`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-14`
- **Type**: `File` \
  **Path**: `strictdoc/export/html/html_templates.py`

**Statement**: StrictDoc shall support a precompilation of HTML templates.

**Rationale**: The StrictDoc-exported HTML content visible to a user is assembled from numerous
small HTML fragments. Precompiling the HTML templates from which the content
gets rendered improves the performance of the HTML rendering.

## Development process requirements

**Type**: SECTION \
**MID**: de3a4de44f474784bf233ea7610eac6c \
**UID**: SECTION-SRS-Quality-requirements

### General process

**Type**: SECTION \
**MID**: cbee3d3e8a9d440abaa58387c342602c

#### Priority handling of critical issues in StrictDoc

**MID**: 27319e3866b8423099774d8770950acd \
**UID**: SDOC-SRS-133 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`

**Statement**: All critical issues reported in relation to StrictDoc shall be addressed with
utmost priority.

**Rationale**: Prioritizing major issues ensures StrictDoc remains stable and reliable,
preventing serious problems that could compromise its performance and integrity.

### Requirements engineering

**Type**: SECTION \
**MID**: 47cec130eb3d4583825355f2635e7011 \
**UID**: SECTION-SRS-Requirements-engineering

#### Requirements-based development

**MID**: d0ab977bbb494cbf818c92a1cab1bef0 \
**UID**: SDOC-SRS-128 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-76`

**Statement**: StrictDoc's development shall be requirements-based.

#### Self-hosted requirements

**MID**: b3fff332c2e342ec9dd372ebd49cb64d \
**UID**: SDOC-SRS-91 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-50`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`

**Statement**: StrictDoc's requirements shall be written using StrictDoc.

### Implementation requirements

**Type**: SECTION \
**MID**: dfbaabc0529f4cc987358ae0563910e9 \
**UID**: SECTION-SRS-Implementation-requirements

#### Programming languages

**Type**: SECTION \
**MID**: 5eb734a4b8944531aa75f0b71ef22d52 \
**UID**: SECTION-SRS-Programming-languages

##### Python language

**MID**: 4053ea6c8f6c4c29b89fea0e39912861 \
**UID**: SDOC-SRS-8 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-69`

**Statement**: StrictDoc shall be written in Python.

**Rationale**: Python has an excellent package ecosystem. It is a widely used language. It is
most often the next language for C/C++ programming community when it comes to
the tools development and scripting tasks.

#### Cross-platform availability

**Type**: SECTION \
**MID**: 131af6457a9f43299306e6dc9fce65a7 \
**UID**: SECTION-SRS-Cross-platform-availability

##### Linux

**MID**: ceee07bdc9bd42fc9a4d0e9b4bfc312f \
**UID**: SDOC-SRS-9 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-67`

**Statement**: StrictDoc shall support the Linux operating systems.

##### macOS

**MID**: f8c7586e1b324480ac0bd153e068350d \
**UID**: SDOC-SRS-10 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-67`

**Statement**: StrictDoc shall support the macOS operating system.

##### Windows

**MID**: 6af3dbb1e05244579622d3d2a26b5413 \
**UID**: SDOC-SRS-11 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-67`

**Statement**: StrictDoc shall support the Windows operating system.

### Implementation constraints

**Type**: SECTION \
**MID**: 852396c217184ba98a0d26b92f36fd04 \
**UID**: SECTION-SRS-Implementation-constraints

#### Use of open source components

**MID**: 83d5c896004948b48c3597d58267dafa \
**UID**: SDOC-SRS-89 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `DO178-7`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-39`
- **Type**: `File` \
  **Path**: `pyproject.toml`

**Statement**: StrictDoc shall be built using only open source software components.

**Rationale**: No commercial/proprietary dependency chain ensures that StrictDoc remain free
and open for everyone.

#### No heavy UI frameworks

**MID**: b22bf982e73246a79a5ba4ae653d21e5 \
**UID**: SDOC-SRS-14 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-90`

**Statement**:

StrictDoc shall avoid using large and demanding UI frameworks.

NOTE: An example of frameworks that require a very specific architecture: React
JS, AngularJS.

#### No use of NPM

**MID**: 309e4108c1fa47e99d4331af642f3b81 \
**UID**: SDOC-SRS-15 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-90`

**Statement**: StrictDoc shall avoid extending its infrastructure with anything based on
NPM-ecosystem.

**Rationale**: StrictDoc already deals with the Python/Pip/Pypi ecosystem. The amount of
necessary maintenance is already quite high. NPM is known for splitting its
projects into very small parts, which increases the complexity of maintaining
all dependencies.

#### No use of JavaScript replacement languages (e.g., Typescript)

**MID**: b9cacb97a045418385c7f870b23ac063 \
**UID**: SDOC-SRS-16 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-90`

**Statement**: StrictDoc shall avoid using JavaScript-based programming languages.

**Rationale**: The development team does not have specific experience with any of the JS
alternatives. Staying with a general subset of JavaScript is a safer choice.

#### Monolithic application with no microservices

**MID**: 70f05a744a0546909dc5b69de88ad41f \
**UID**: SDOC-SRS-87 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-82`

**Statement**: StrictDoc shall avoid using microservices and microservice-based architectures.

**Rationale**: The project is too small to scale to a multi-service architecture.

**Comment**: This requirement could be re-considered only if a significant technical pressure
would require the use of microservices.

#### No reliance on containerization

**MID**: 7d68821750a54cb5833b608cfc278f47 \
**UID**: SDOC-SRS-88 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-82`

**Statement**: StrictDoc shall avoid using containers and containerization technologies.

**Rationale**: Containers are significant extra layer of complexity. They are hard to debug.

**Comment**: This constraint does not block a StrictDoc user from wrapping StrictDoc into
their containers.

### Coding constraints

**Type**: SECTION \
**MID**: e4e5b9934e074cdb9567fa197db20a4a \
**UID**: SECTION-SRS-Coding-constraints

#### Use of asserts

**MID**: 61d96cd1d03e40c48187ee67ac0b65f6 \
**UID**: SDOC-SRS-40 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`

**Statement**:

StrictDoc's development shall ensure a use of assertions throughout the project
codebase.

NOTE: At a minimum, the function input parameters must be checked for validity.

#### Use of type annotations in Python code

**MID**: 72b5b0c925cf4ef49749b7e466675df1 \
**UID**: SDOC-SRS-41 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`

**Statement**: StrictDoc's development shall ensure a use of type annotations throughout the
project's Python codebase.

### Linting

**Type**: SECTION \
**MID**: 61e87567580045378d970b327d218cac \
**UID**: SECTION-SRS-Linting

#### Compliance with Python community practices (PEP8 etc)

**MID**: 6c0163c56ade49faa353ec06cbd676cd \
**UID**: SDOC-SRS-42 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-90`

**Statement**: StrictDoc's development shall ensure that the project's codebase is compliant
with the Python community's modern practices.

### Static analysis

**Type**: SECTION \
**MID**: 3029f97a1276499dbbd5d7c71691908e \
**UID**: SECTION-SRS-Static-analysis

#### Static type checking

**MID**: 2cc9b494ca6248058b6bf63b6e2c1cfa \
**UID**: SDOC-SRS-43 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`
- **Type**: `File` \
  **Path**: `tasks.py`

**Statement**: StrictDoc's development shall include a continuous type checking of StrictDoc's
codebase.

### Testing

**Type**: SECTION \
**MID**: 3aba8ca86d404ba9a063ce125489f35b \
**UID**: SECTION-SRS-Testing

#### Unit testing

**MID**: 2731c64ab32146eeb4b8167df4a34540 \
**UID**: SDOC-SRS-44 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-77`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`

**Statement**: StrictDoc's development shall provide unit testing of its codebase.

#### CLI interface black-box integration testing

**MID**: 70ef3986cfc4437bbb10288d3b55958c \
**UID**: SDOC-SRS-45 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-77`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`

**Statement**: StrictDoc's development shall provide complete black-box integration testing of
its command-line interface.

#### Web end-to-end testing

**MID**: a42c65f1a53b4c9bb50bc2a1ecb855cb \
**UID**: SDOC-SRS-46 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-77`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`

**Statement**: StrictDoc's development shall provide complete end-to-end testing of the web
interface.

#### At least one integration or end-to-end test

**MID**: c90f35ab9a7f4c29a418557151878b9f \
**UID**: SDOC-SRS-47 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-77`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-78`

**Statement**:

Every update to the StrictDoc codebase shall be complemented with a
corresponding provision of at least one test as follows:

- For web interface: at least one end-to-end test.
- For command-line interface: at least one black-box integration test.
- For internal Python functions: at least one unit test.

NOTE: This requirement implies that no modifications to StrictDoc's
functionality can be merged unless accompanied by at least one test.

**Rationale**: This requirement ensures that every new feature or a chance in the codebase is
covered/stressed by at least one test, according to the change type.

## Code hosting and distribution

**Type**: SECTION \
**MID**: 83bdb9731e78431cb48d584d279443b4

### Code hosting

**Type**: SECTION \
**MID**: dbd186fae9624fd6af8aeb55edfaa43b \
**UID**: SECTION-SRS-Code-hosting

#### GitHub

**MID**: b112c60bc2f34114ab1f3361a1a10a00 \
**UID**: SDOC-SRS-12 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-38`
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-82`

**Statement**: StrictDoc's source code shall be hosted on GitHub.

### StrictDoc license

**MID**: bd949cbbe07c4cb29492ea0c8e5c1eec \
**UID**: SDOC-SRS-118 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `SDOC-SSS-40`
- **Type**: `File` \
  **Path**: `LICENSE`
- **Type**: `File` \
  **Path**: `NOTICE`

**Statement**: All StrictDoc software shall be licensed under the Apache 2 license.
