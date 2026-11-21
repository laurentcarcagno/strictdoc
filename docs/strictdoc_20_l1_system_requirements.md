# Requirements Tool Specification (L1)

**Grammar**: strictdoc_20_l1_system_requirements.gra.md \
**Version**: Git commit: @GIT_VERSION, Git branch: @GIT_BRANCH \
**Date**: @GIT_COMMIT_DATETIME \
**Prefix**: SDOC-SSS- \
**Root**: True \
**Enable MID**: True

**Type**: TEXT \
**MID**: c455f0297eb648c6aa9c6d239f043e0d

The StrictDoc project is structured around two distinct requirement documents
that guide its development:

1. The "Requirements Tool Specification" (this document), which is a
   higher-level document.
2. The "StrictDoc Requirements Specification," a more detailed and lower-level
   document, separate from this one.

This document, the Requirements Tool Specification, delineates the general
requirements for an open-source Requirements Tool, with a focus that remains
agnostic of the specific implementation details of StrictDoc. Its primary goal
is to provide a comprehensive, implementation-neutral overview of what
capabilities a Requirements Tool should possess, emphasizing the 'WHAT' aspect.

In contrast, the StrictDoc Requirements Specification, the second document,
delves deeply into the 'HOW' aspect of StrictDoc’s implementation. It builds
upon the high-level requirements set out in this document, treating them as
parent requirements to guide its detailed development approach.

## Summary of user needs

**Type**: SECTION \
**MID**: 668d18a7489043b38dd435933319e8e7

**Type**: TEXT \
**MID**: 7a94c3f55e32498187603400923bfae4

This section offers an overview of the necessary capabilities of a requirements
and documentation management tool.

### Free and open source tool

**Type**: SECTION \
**MID**: 1cbe275272994922a942fd088fa969d8

**Type**: TEXT \
**MID**: 3ca29d12a7804f089f5b2aa955e4da59

The primary user need and entry point for this Requirements Tool specification
is the availability of free, lightweight, yet capable software for creating
requirements specifications and other technical documentation. The tool should
facilitate the creation of requirements specifications and technical documents,
effectively lowering the entry barrier for requirements engineering and
technical documentation writing.

It is assumed throughout this document that the requirements tool will be
developed as open-source software available at no cost. However, with minor
adjustments, these requirements could also apply to commercial requirements
tools. See [LINK: SECTION-SSSS-Licensing-and-distribution].

### Document types

**Type**: SECTION \
**MID**: 18136bcb9a5b4226a7a95d27dae49805

**Type**: TEXT \
**MID**: 14383453f84747d3abdce6b5dce50c7f

A requirements tool is very often also a documentation writing and management
tool, so, besides the requirements editing functionality, the tool shall be able
to accommodate for the variety of documents and templates used in different
industries.

The variety comes from:

- Supporting arbitrary documentation structures, e.g., non-nested vs. deeply
  nested documents.
- Supporting a rich set of visualization mechanisms. Supporting images,
  diagrams, tables, text markup, etc.
- Supporting custom fields/attributes used by different industries (the
  criticality levels in various industries, RAIT verification activities in
  aerospace, status/workflow fields, etc.).

Examples of typical document types include:

- Requirements specification
- Design document / architecture description document
- Interface control document / API reference
- User manual
- Development plan
- Systems engineering plan, management plan
- Standard (e.g., ECSS or ISO 26262).

The documentation/requirements management requirements for a Requirements Tool
are specified in the sections [LINK: SECTION-RTS-Documentation-management] and
[LINK: SECTION-RTS-Requirements-management].

#### Document structure differences

**Type**: SECTION \
**MID**: 973b586b8a89411ab4f083fd4c262cf5 \
**UID**: SECTION-RTC-Appendix-A-Document-archetypes

**Type**: TEXT \
**MID**: 4a847b9a58444e4a9be056db1f23272c

The table below summarizes various differences observed across industry
documents.

**Table: Requirements and specification document**

<table>
<thead>
<tr><th>Criteria</th><th>Comments</th></tr>
</thead>
<tbody>
<tr><td>Structure</td><td>Non-nested, nested, deeply nested. A structure of a deeply nested specification document can reach 8-10 levels (e.g., Section 1.2.3.4.5.6.7.8 "ABC").</td></tr>
<tr><td>Requirements visual presentation</td><td>Requirements are often presented as table cells. The cells can be standalone or a whole section or a document can be a structured as a long table with cells. Alternatively, requirements are rather presented as a section header + text.</td></tr>
<tr><td>Unique requirement identifiers (UID)</td><td>Some documents provide UIDs for all requirements, some do not. Where the UIDs are missing, the section header numbers are used instead for unique identification. Often, a combination "Number + Title" becomes a reference-able identifier.</td></tr>
<tr><td>Requirement titles</td><td>Not all documents provide requirement titles. When the requirement titles are missing, the grouping is may be provided by sections/chapters. When the titles are present, the requirement titles can also be section titles.</td></tr>
</tbody>
</table>

### Workflows

**Type**: SECTION \
**MID**: 52b6175f03d7495a9fa8dbffa36aeff4 \
**UID**: SECTION-LRTS-Workflows

**Type**: TEXT \
**MID**: c537b8fa5b54417eb9dff6478553f6d7

Besides supporting a variety of document types, a Requirements Tool shall also
support and integrate well with multiple documentation and requirements
management workflows.

At least the following workflows have been identified to be relevant:

<table>
<thead>
<tr><th><strong>Workflow</strong></th><th><strong>Description</strong></th></tr>
</thead>
<tbody>
<tr><td>Requirements analysis and prototyping</td><td>Early phases of the project. Requirements are drafted out quickly. The higher-level picture and coverage of all topics may be more important than specific details.</td></tr>
<tr><td>Requirements compliance, traceability and justification</td><td>Demonstrating the correctness of specification, also for contractual purposes. Every aspect shall be traceable.</td></tr>
<tr><td>Requirements implementation</td><td>Assisting software engineers in implementing requirements in source code. Making links between requirements and source code implementation units, e.g., files, functions, code fragments. Linking source code implementation units to requirements using special markers left in source code.</td></tr>
<tr><td>Requirements validation/verification workflow (RAIT)</td><td>Verifying the correctness of requirements themselves and the validity of the information they communicate.</td></tr>
<tr><td>Configuration management, change management</td><td>Time machine and Diff functions. Maintaining requirements baselines (v1, v1.1, v2, etc.).</td></tr>
<tr><td>Reporting</td><td>Progress reports, statistics, metrication.</td></tr>
<tr><td>Collaboration on requirements</td><td>Supporting multiple users to collaborate on a documentation tree.</td></tr>
<tr><td>Requirements exchange</td><td>Integration between distinct projects requirements trees. Example: An embedded software project has its own requirements. The developers want to integrate a requirements subtree of another product that is integrated to the parent project as an off-the-shelf solution.</td></tr>
<tr><td>Formal reviews</td><td>Formal review of documentation. Walkthroughs, inspections. Version control of delivered documentation packages. Assessment of progress reports achieved.</td></tr>
<tr><td>Interoperability with industry standards.</td><td>Supporting seamless integration between a project documentation tree and applicable standards.</td></tr>
</tbody>
</table>

The section [LINK: SECTION-SSSS-Existing-workflows] contains the
workflow-related requirements for a Requirements Tool.

### Target audience

**Type**: SECTION \
**MID**: 08d547a3b04d485ca1f5a3a94a664ee1

**Type**: TEXT \
**MID**: 847eaab505124e7797bd25c865f9d868

A Requirements Tool may have different users, each with a different role,
experience and background which necessitates the requirements towards usability,
installation, and user experience.

The following user groups are preliminarily identified as especially relevant:

**Engineering professionals**

This group includes:

- Systems engineers
- Requirements engineers
- Assurance experts in quality, safety/security, verification/validation

For these professionals, the Requirements Tool should offer robust functionality
that is adequate for complex system design and detailed requirements tracking,
ensuring that all aspects of system integrity and compliance are met
efficiently.

**Management**

The focus of this group is more on the progress and compliance aspects. They
require high-level overviews and reporting capabilities in the tool, to track
project milestones, manage risks, and ensure that the development is adhering to
the predefined requirements and industry standards.

**Software engineers**

For software engineers, the Requirements Tool shall be closely integrated with
their software engineering workflow, e.g., it has interfaces with software
version control systems, software IDEs, and source code repositories. This
integration ensures a seamless transition between requirement specification and
software development tasks.

**IT/DevOps**

This group of users may not work with a Requirements Tool directly but is still
an important stakeholder. The Tool shall be easy to install and deploy. It shall
be easy to maintain and upgrade the tool, with support for automated updates and
compatibility with various IT infrastructures.

**General audience**

Not all users of a requirements tool must have an engineering background. In
fact, there are many projects where non-technical people have to maintain
requirements. The Requirements Tool shall be usable without any technical
training required, featuring an intuitive user interface and simplified
processes for entering and managing requirements.

The requirement sets in the sections
[LINK: SECTION-RTC-Usability-installation-and-usage] and
[LINK: SECTION-SSSS-Implementation-suggestions] aim to equip the Requirements
Tool with sufficient capabilities to support all of the user groups described
above.

## Documentation management

**Type**: SECTION \
**MID**: f1ffdc7f78134d4b98f3c90e9be40cc7 \
**UID**: SECTION-RTS-Documentation-management

**Type**: TEXT \
**MID**: 0cacb010f5164118adce5dd8512c3e27

This section outlines the requirements towards a Requirements Tool as a
documentation tool.

The requirements of this group are dedicated to the core tasks of documentation
management:

- Writing, structuring and managing documents
- Complementing documents with meta information
- Versioning documents.

### Documents (CRUD)

**MID**: 72d0dd23dedd4907b4a8924debe7343b \
**UID**: SDOC-SSS-3 \
**Status**: Active

**Statement**:

The Requirements Tool shall provide the CRUD operations for document management:

- Create document
- Read document
- Update document
- Delete document.

**Rationale**: The CRUD operations are essential operations of document management. They are at
the core of a documentation management tool.

### Browsing documentation tree

**MID**: 9841bc9a56d740dd9e7988e52339618c \
**UID**: SDOC-SSS-91 \
**Status**: Active

**Statement**: The Requirements Tool shall provide browsing of the documentation tree.

### Documents with nested sections/chapters structure

**MID**: c4de5f1f46f343b6b4e8dc2a6121b0a2 \
**UID**: SDOC-SSS-51 \
**Status**: Active

**Statement**: The Requirements Tool shall allow management of documents with nested
sections/chapters structure.

### Assembling documents from fragments

**MID**: 5236f36f278140539e347bacea921118 \
**UID**: SDOC-SSS-52 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-1`

**Statement**:

The Requirements Tool shall allow composing documents from other documents or
fragments.

NOTE: If a Requirements Tool implements stores documents in a file system, the
composition can be arranged at a file level when a parent document file includes
the child fragment files and produces a composite document.

**Rationale**: Composable documents allow assembling documents from multiple smaller documents
which can be standalone documents or document fragments. This feature is
particularly useful for managing extensive documents that can be more
effectively organized and handled when divided into smaller document sections.

### Document meta information (UID, version, authors, signatures, etc)

**MID**: 8aeecdfa139341588d6ab8c0c3606a9b \
**UID**: SDOC-SSS-53 \
**Status**: Active

**Statement**: The Requirements Tool shall support management of document meta information.

### Document versioning

**MID**: d1883b65e17442c0a22987d4ad415cb6 \
**UID**: SDOC-SSS-75 \
**Status**: Active

**Statement**: The Requirements Tool shall provide capabilities for document versioning.

### Text formatting capabilities

**MID**: b8d7b22fd8a6478a9a21ecaa60cf0028 \
**UID**: SDOC-SSS-63 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-9`

**Statement**:

The Requirements Tool shall provide "rich text" formatting capabilities which
includes but not limited to:

- Headings
- Lists
- Tables
- UML diagrams
- etc.

### Content search

**MID**: 3bb5252d75bc486b98e7606fb642bac0 \
**UID**: SDOC-SSS-95 \
**Status**: Active

**Statement**: The Requirements Tool shall provide functionality to search content in the
documentation tree.

**Rationale**: Efficient navigation of large documentation trees requires search capabilities
so that users can quickly locate relevant information without manually browsing
through all content.

## Requirements management

**Type**: SECTION \
**MID**: fd227b9cfdc54d7db3134cdb925bde87 \
**UID**: SECTION-RTS-Requirements-management

**Type**: TEXT \
**MID**: c1e2431cdf2141ca86931f29b9912ff7

This section outlines the requirements towards a Requirements Tool as a
requirements management tool.

The following core aspects of the requirements management are covered:

- Writing and structuring requirements
- Linking requirements with other requirements
- Managing requirement unique identifiers (UID)
- Requirement verification.

### Requirements CRUD

**MID**: 6e6f1464c47f4ced8e14c4153f40618b \
**UID**: SDOC-SSS-4 \
**Status**: Active

**Statement**:

The Requirements Tool shall enable the main requirements management operations:

- Create a requirement
- Read / view / browse a requirement
- Update / edit a requirement
- Delete a requirement.

**Rationale**: The CRUD operations are at the core of the requirements management.

### Minimal requirement field set

**MID**: db42ad4b504e48e0bf51b4d82529a888 \
**UID**: SDOC-SSS-61 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-10`
- **Type**: `Parent` \
  **ID**: `ZEP-14`

**Statement**:

The Requirements Tool shall support at least the following requirement field
set:

- UID
- STATUS
- TITLE
- STATEMENT
- RATIONALE
- COMMENT
- RELATIONS (connections with other requirements).

**Rationale**: The selection of the minimal set is based on what is common in the industries
(e.g., automotive, space, etc).

**Comment**: The other fields common to each industry can be customized with custom fields
handled by other requirements.

### Custom fields

**MID**: a69bae43b3224dfc8439a88451a98395 \
**UID**: SDOC-SSS-62 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-3`

**Statement**:

The requirements tool shall support configuring a requirement item with an
arbitrary set of fields.

NOTE: Examples of typical fields include: UID, Title, Statement, Rationale,
Comment. Other fields that are used very often are: Status, Tags, Criticality
level, Priority, etc.

**Rationale**: The tool shall not constrain a user in which fields they are able to use for
their projects.

### Structuring requirements in documents

**MID**: 5f89bdaa6cb74e2a8b9b030b6237b7ef \
**UID**: SDOC-SSS-64 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-13`

**Statement**: The Requirements Tool shall support structuring requirements in documents.

**Rationale**: The industry works with requirements documents. The documents have
sections/chapters and requirements.

### Move requirement nodes within document

**MID**: 65575cc8a87e4d4480ccdf89d1fb6d67 \
**UID**: SDOC-SSS-5 \
**Status**: Active

**Statement**: The Requirements Tool shall allow moving nodes (sections, requirements) within
the containing document.

### Move nodes between documents

**MID**: 06ab121d3c0f4d8c94652323b8f735c6 \
**UID**: SDOC-SSS-70 \
**Status**: Active

**Statement**: The Requirements Tool shall allow moving nodes (sections, requirements) between
documents.

### Auto-provision of Requirement UIDs

**MID**: 637c129a91804d8cbe2280c1af14836d \
**UID**: SDOC-SSS-6 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-8`

**Statement**: The Requirements Tool shall provide controls for automatic generation of
requirements UIDs.

**Rationale**: When a document is large, it becomes harder to manage the assignment of the new
requirements identifiers by manually exploring which requirement UID has not
been assigned yet. The provision of automatically generated UIDs is a
convenience feature that improves the user experience significantly.

### Link requirements together

**MID**: 1ce495a5194044d4a7a3dd030f766c9f \
**UID**: SDOC-SSS-7 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-4`

**Statement**: The Requirements Tool shall allow bi-directional linking of requirements nodes
together using Parent or Child relations.

**Rationale**: The requirement ensures a classic capability of a requirement tool: linking
requirements together enables bi-directional traceability which helps in
understanding how the requirements are related to each other.

### Multiple link roles

**MID**: 44b9d75e50c84d6c8424cfb8a42a0771 \
**UID**: SDOC-SSS-8 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-5`

**Statement**:

The Requirements Tool shall support the link roles.

Example of roles for a child-to-parent link: "verifies", "implements",
"satisfies", etc.

**Rationale**: Different industries maintain custom conventions for naming the relations
between requirements and other nodes such as tests or other artefacts.

### Reverse parent links

**MID**: 387bd5ff0e4a4a97962661e9d7451f19 \
**UID**: SDOC-SSS-71 \
**Status**: Active

**Statement**: The Requirements Tool shall support the Reverse Parent relationship.

### Unique identification of requirements

**MID**: 3348caaed8d44be0928cc6f3c7414094 \
**UID**: SDOC-SSS-89 \
**Status**: Active

**Statement**: The Requirements Tool shall provide means for unique identification of every
requirement.

**Rationale**:

The requirement ensures a classic capability of a requirement tool:

1) The unique identifiers help the users in identifying the requirements, both
   when reading a requirements document and when discussing requirements.
2) The unique identifiers are used for linking requirements together. The
   requirements tool stores the identifiers in a global database and can resolve
   the links, following the unique identifiers they point to.

### Requirements database consistency checks

**MID**: 3850f0b8c8294455bf7be9e2acddbd40 \
**UID**: SDOC-SSS-47 \
**Status**: Active

**Statement**:

The Requirements Tool shall provide a validation mechanism that ensures the
integrity of requirements and connections between them.

NOTE: Examples of integrity checks:

- Requirements have correct fields.
- Requirements do not form cycles.
- Requirements only link to other requirements as specified in a project
  configuration.

### Requirement syntax validation (e.g. EARS)

**MID**: 1216cb617c0f495a9c96471ef72bf80f \
**UID**: SDOC-SSS-57 \
**Status**: Active

**Statement**: The Requirements Tool shall provide capabilities for validating requirements
according to the EARS syntax.

## Existing workflows

**Type**: SECTION \
**MID**: ec52fa5cc1714b07863eb7da9432be1d \
**UID**: SECTION-SSSS-Existing-workflows

**Type**: TEXT \
**MID**: 33769a5f0ca94b99a4802adc81841037

This section captures the requirements towards specific workflows that a
Requirements Tool should support as outlined in [LINK: SECTION-LRTS-Workflows].

### Excel-like viewing and editing of requirements

**MID**: 831debedfa0e4e4c8434021569f96bad \
**UID**: SDOC-SSS-73 \
**Status**: Active

**Statement**:

The Requirements Tool shall provide an Excel-like user interface for viewing and
editing requirements.

NOTE: This interface does not have to be the only or a default interface.

**Rationale**: As recognized by the parent requirement, some requirements-based workflows are
naturally easier when the requirements content is presented in a form of a
table, as opposed to a document with a nested chapter structure.

### 1000-feet view

**MID**: 5d412989005e4bc3b5dcfd94675615dc \
**UID**: SDOC-SSS-56 \
**Status**: Active

**Statement**: The Requirements Tool shall provide a "1000-feet view" kind of requirements
visualization.

**Rationale**: Compared to the other visualizations, such a visualization helps to "see the
forest for the trees". Seeing requirements and their sections all at once helps
to visualize groups of requirements and better understand the relationships
between them.

### Traceability matrices

**MID**: 5eb553abd3944bffbd003e37b3d1c5a5 \
**UID**: SDOC-SSS-28 \
**Status**: Active

**Statement**: The Requirements Tool shall support generation of traceability matrices.

### Compliance matrices

**MID**: 06f0bb40f76142f4ba59d037aaedc9de \
**UID**: SDOC-SSS-48 \
**Status**: Active

**Statement**: The Requirements Tool shall allow generating a Compliance Matrix document.

### Requirements coverage

**MID**: 74ffae6279bc4e4095c03d6a247c3599 \
**UID**: SDOC-SSS-29 \
**Status**: Active

**Statement**:

The Requirements Tool shall provide means for getting information about the
requirements coverage of a given project.

NOTE: The requirements coverage can be presented in a tabular form or visualized
with a set of graphs.

**Rationale**: The requirements coverage information helps to assess whether all requirements
are linked to each other, whether all requirements are connected to
implementation, test or other artifacts. Additionally, the requirements coverage
information can provide metrics for measuring a project's progress, e.g., "50%
of requirements have been traced to the source code". The requirement ensures
that the requirements tool provides this feature.

### Progress report

**MID**: e0e6d1f883764719919238e4974dccef \
**UID**: SDOC-SSS-49 \
**Status**: Active

**Statement**:

The Requirements Tool shall allow generating a Progress Report document.

NOTE: A progress report document shall include at least the following Key
Performance Indicators.

Project-level KPIs:

- Total number of requirements
- Total number of requirements without parent (excluding top-level and derived)
- Total number of TBD/TBC
- Total number of requirements without rationale
- Tags breakdown

Document-level KPIs: the same but per document.

### Change management

**MID**: ed4bd232bed84eda977263fa03e75b80 \
**UID**: SDOC-SSS-74 \
**Status**: Active

**Statement**:

The Requirements Tool shall provide capabilities for change management:

- Visualizing changes between project tree versions.
- Visualizing changes between document versions.
- Visualizing the impact that a changed requirement has on a project tree.

## Requirements and source code

**Type**: SECTION \
**MID**: 8b1da9907bc847c989dc807b7dff2a05 \
**UID**: SECTION-RTS-Requirements-and-source-code

### Traceability between requirements and source code

**MID**: 4692362c77974fb8bcbeefdc248d0e89 \
**UID**: SDOC-SSS-72 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-11`
- **Type**: `Parent` \
  **ID**: `ZEP-12`

**Statement**:

The Requirements Tool shall support bi-directional tracing between requirements
content and implementation source code with only minimal changes needed in the
source code.

NOTE: The Requirements Tool does not necessarily have to implement the complete
tracing process. It may delegate parts of the traceability task to other tools,
e.g., Doxygen, Lobster, etc.

**Rationale**: This requirement connects the worlds of requirements and source code which
ensures that the traceability between requirements-implementation and
requirements-tests can be achieved in an explicit way. Without a direct support
of tracing requirements to source code by a requirements tool, the users have to
find workarounds that are less efficient.

## Requirements exchange formats (export/import)

**Type**: SECTION \
**MID**: cd9e353e07ae4d50b1aa08999854aa02 \
**UID**: SECTION-RTS-Requirements-exchange-formats-export-import

**Type**: TEXT \
**MID**: ecc76e0991e44d6282776365496193e6

This section captures the requirements related to "Requirements exchange" as
outlined in the section [LINK: SECTION-LRTS-Workflows].

The Requirements Tool should fundamentally support the exchange of documentation
and requirements with other tools. Importing data into this tool and exporting
data from it to other tools should be straightforward. The key focus of this
section's requirements is on enabling seamless access to requirements and
documentation data.

### PDF export

**MID**: 086eb992322d4c43ad91a40f6c9f9952 \
**UID**: SDOC-SSS-96 \
**Status**: Active

**Statement**: The Requirements Tool shall support exporting documentation content to PDF, both
individual documents and complete documentation trees.

**Rationale**: PDF is one of the most common formats for reviewing documentation.

### ReqIF export/import

**MID**: 73e70548c2cf415f94adbf1066d5fe4b \
**UID**: SDOC-SSS-58 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-6`

**Statement**: The Requirements Tool shall support exporting/importing requirements content
from/to ReqIF format.

**Rationale**: ReqIF is a standard for exchanging requirements. There is currently no other
standard of a higher maturity.

### CSV export/import

**MID**: c94de32c2c2e454d81c77724a4f29283 \
**UID**: SDOC-SSS-59 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-7`

**Statement**: The Requirements Tool shall support exporting/importing requirements content
from/to CSV.

### Excel export/import

**MID**: f7a600a238e34075ac6b65852492cc2f \
**UID**: SDOC-SSS-60 \
**Status**: Active

**Statement**: The Requirements Tool shall support exporting/importing requirements content
from/to Excel.

## Tool configurability

**Type**: SECTION \
**MID**: 7c112f3a5885477084396fd26387a864

### Project-level configuration

**MID**: 4550038552894ef69b85b281cff60c60 \
**UID**: SDOC-SSS-92 \
**Status**: Active

**Statement**:

The Requirements Tool shall provide a solution for configuring the project-level
options.

NOTE: Examples of project-level options:

- Project title.
- Global settings for the Requirements Tool itself.

**Rationale**: The requirement ensures the configurability of the tool for a specific project.

### Document-level configuration

**MID**: 4550b38552894ef69b85b281cff60360 \
**UID**: SDOC-SSS-93 \
**Status**: Active

**Statement**:

The Requirements Tool shall provide a solution for configuring the
document-level options.

NOTE: Examples of document-level options:

- Document title
- Requirement prefix.
- Other options local to the content and the presentation of a given document.

**Rationale**: Sometimes, the project-level configuration can be not fine-grained enough. The
requirement ensures that the requirements tool allows a configuration on a
document level.

## Performance

**Type**: SECTION \
**MID**: 56dabce670be4691b35434bda6d6bb36 \
**UID**: SECTION-SSSS-Performance

**Type**: TEXT \
**MID**: 68e4b4b1ba78485f8620575ef9e1eaa2

This section captures the performance requirements towards a Requirements Tool.

### Support large requirements sets

**MID**: a0a95079e3c0438bb3ea9e5af7ddddc9 \
**UID**: SDOC-SSS-13 \
**Status**: Active

**Statement**: The Requirements Tool shall support requirement trees with at least 10000
requirements.

### Support large project trees

**MID**: 64b982c9299a4c8eb7031495e940a3f8 \
**UID**: SDOC-SSS-14 \
**Status**: Active

**Statement**: The Requirements Tool shall be able to handle documentation packages of at least
100 documents without significant performance degradation.

## Data integrity

**Type**: SECTION \
**MID**: d1a483f3e321414b83bb4a39b1283293

### Data integrity of documentation/requirements

**MID**: d1323d222a0040b2b6122c59b3c00f06 \
**UID**: SDOC-SSS-94 \
**Status**: Active

**Statement**: The Requirements Tool shall ensure the integrity of stored documentation and
requirements data throughout its lifecycle.

**Rationale**: The requirement ensures that the tool and the tool's development includes
measures for reducing the risk of any data corruption.

**Comment**: This includes safeguarding against data corruption, loss, and ensuring the
reliability of links within the documentation.

## Usability, installation and usage

**Type**: SECTION \
**MID**: 85d2f75b2f074f98ace5ceb5288c09b9 \
**UID**: SECTION-RTC-Usability-installation-and-usage

### General usability

**MID**: 7e33387f373d427d9e1af522f1e5bbc5 \
**UID**: SDOC-SSS-79 \
**Status**: Active

**Statement**:

The Requirements Tool shall be accessible to a broad spectrum of users.

NOTE: Factors to consider:

- The cost of a tool.
- The easy of installation.
- The availability of a graphical user interface.
- The availability of a programmatic access to the functions of a tool.
- The interoperability of the tool with other tools.

**Rationale**: A tool that can be used by a large number of people simplifies its adoption and
allows more users to work with documentation and requirements.

### Tool identification

**MID**: 5461fce7174a4bc79048b3528b699beb \
**UID**: SDOC-SSS-97 \
**Status**: Active

**Statement**: The Requirements Tool shall provide identifying information, including title,
release version, and project website links.

### Easy user experience

**MID**: 57b01915e4624634909dbb40f5d56697 \
**UID**: SDOC-SSS-80 \
**Status**: Active

**Statement**:

The Requirements Tool shall provide a smooth user experience.

NOTE: Documentation and requirements management are composite activities that
consist of several types of repetitive tasks. A requirements tool user
experience should assist in automating these tasks as far as possible and make
the overall workflow efficient and precise.

### Support projects with a large number of users

**MID**: d3e66072363d4e7ea2e2f9691c094bb2 \
**UID**: SDOC-SSS-81 \
**Status**: Active

**Statement**: The Requirements Tool shall be capable of supporting a large number of users.

**Rationale**: Many documentation and requirements projects involve large groups of people. The
requirements tool should not become a bottleneck when a number of users grows.

### Individual use (home PC)

**MID**: db495bc2f11f4f96ace60cdb0bef4d66 \
**UID**: SDOC-SSS-82 \
**Status**: Active

**Statement**: The Requirements Tool shall be usable on the normal personal computers, e.g., do
not require a special cloud deployment.

### Server-based deployments (IT-friendly setup)

**MID**: 90562d92b9a7468ba42567bc72cb6ebf \
**UID**: SDOC-SSS-83 \
**Status**: Active

**Statement**: The Requirements Tool shall be deployable to the network of computers, e.g.,
provide a server instance.

**Comment**: Scaling from smaller setups (e.g., Raspberry PI in an office network) to
larger in-house and cloud-base installations.

### Requirements database

**MID**: 4312ed066d19487eba18ec677430e60f \
**UID**: SDOC-SSS-84 \
**Status**: Active

**Statement**: The Requirements Tool shall store documentation and requirements data in a
database.

**Rationale**:

A database allows:

- Persistent storage of documentation/requirements data
- Versioning
- Backups
- Exchange of information and access of the same database by multiple users.

### Programming access via API (Web)

**MID**: 81858dda65844dcd9640fdd74badecee \
**UID**: SDOC-SSS-85 \
**Status**: Active

**Statement**: The Requirements Tool shall provide a Web API interface.

**Rationale**: Besides a direct access to the tool's source code, accessing an API deployed to
a server provides additional capabilities for getting and manipulating
requirements/documentation content.

### Programming access via API (SDK)

**MID**: ee96cc5f18e14f6894e2775c546240d8 \
**UID**: SDOC-SSS-86 \
**Status**: Active

**Statement**:

The Requirements Tool shall provide a Software Development Kit (SDK) that allows
customization of the Requirements Tool functions.

NOTE: An SDK provides access to the API of the Requirements Tool. Examples of
functions that may be used by the users of the tool:

- Custom import/export functions to/from various requirements/documentation
  formats.
- Implement custom visualization functions.
- Implement integration with other tools.

**Rationale**: A SDK allows a software engineer to extend the Requirements Tool capabilities.

### Programmatic access to requirements data

**MID**: f4b122c5081f4b218aa93a119e372a34 \
**UID**: SDOC-SSS-87 \
**Status**: Active

**Statement**: The Requirements Tool shall provide programmatic access to requirements data.

**Rationale**: When the requirements data is accessible by a user directly, it is possible to
exchange the data or implement additional scripting procedures.

## Implementation suggestions

**Type**: SECTION \
**MID**: 29fa83c59e714d0da8b36a9dc65b0c72 \
**UID**: SECTION-SSSS-Implementation-suggestions

### Static HTML export

**MID**: 3db06eb066b4441290e06b08405da0a9 \
**UID**: SDOC-SSS-30 \
**Status**: Active

**Statement**: The Requirements Tool shall support generation of documentation to static HTML.

**Rationale**:

A static HTML export capability enables:

- Viewing requirements in browsers without any additional software.
- Exchanging HTML content as zip between users.
- Publishing HTML content via static website hosting providers (GitHub and
  GitLab Pages, Read the Docs, Heroku, etc.).

### Graphical user interface (GUI)

**MID**: e718af582b0345c2b0ddb6e405cb6d9a \
**UID**: SDOC-SSS-31 \
**Status**: Active

**Statement**: The Requirements Tool shall provide a graphical user interface.

### Command-line interface

**MID**: cd20e9613a65441a8862143ba6407f61 \
**UID**: SDOC-SSS-32 \
**Status**: Active

**Statement**: The Requirements Tool shall provide a command line interface (CLI).

### Web API interface

**MID**: 4475857729e5476cbbb409cc844048fd \
**UID**: SDOC-SSS-68 \
**Status**: Active

**Statement**: The Requirements Tool shall provide an API interface.

### Version control (Git)

**MID**: 5ac2f3010db84466bff854fc323e944c \
**UID**: SDOC-SSS-33 \
**Status**: Active

**Statement**: The Requirements Tool shall support the software version control systems (e.g.,
Git).

**Rationale**:

- Git allows precise tracking of the changes to the documentation.
- Requirements/documentation content can be release-tagged.
- The "Time machine" function: ability to review the older state of the
  documentation/requirements tree.

### Support major operating systems

**MID**: b76fb774542849a182e2cdd89fdaab3c \
**UID**: SDOC-SSS-67 \
**Status**: Active

**Statement**:

The Requirements Tool shall support at least the following operating systems:

- Linux
- Windows
- macOS.

### Conservative languages for implementation

**MID**: 871a7a66eb50436997fde692e90e93eb \
**UID**: SDOC-SSS-69 \
**Status**: Active

**Statement**:

The Requirements Tool shall be implemented using the popular programming
languages.

NOTE: Examples of the most popular programming languages:

- Java
- C++
- Python
- JavaScript

**Rationale**: Choosing a less popular programming language can limit the long-term
maintainability of the tool.

**Comment**: Examples of less popular programming languages, with all due respect to their
powerful features: Haskell, F#, Ada, etc.

### Long-term maintainability of a tool

**MID**: 0556a0b2773d4ee0b44b22773455a600 \
**UID**: SDOC-SSS-90 \
**Status**: Active

**Statement**:

The Requirements Tool shall be designed for long-term maintenance.

NOTE: Long-term maintenance aspects to consider:

- Careful selection of the technologies used, e.g., avoid building on too many
  unrelated technologies at the same time.
- Take into account the existing experience of the development team. Consider
  the availability of qualified developers in the future.
- Take into account maintainability by the development team as well as the
  users, e.g., IT/DevOps department.

## Text-based requirements language (optional)

**Type**: SECTION \
**MID**: 7bdea1a7cb9e4f6fbcf8497670f87278 \
**UID**: SECTION-RTS-Text-based-requirements-language

**Type**: TEXT \
**MID**: dfe5a61ed10149bebcf69d9c5c3b1316

Note: Not all requirements tools must be text-based. But when they are, the
following requirements apply.

### Text files for storing documentation and requirements

**MID**: f472e85f3398413795234a9298d4af3c \
**UID**: SDOC-SSS-88 \
**Status**: Active

**Statement**: The Requirements Tool shall allow storage of documentation and requirements
content using text files.

### Strict text language syntax

**MID**: b13bc3dfa7324f238bc06a88baf5edb6 \
**UID**: SDOC-SSS-55 \
**Status**: Active

**Statement**: The Requirements Tool shall provide a strict syntax for its text language.

### Machine-readable format

**MID**: 0b47da74f9ec45e6a77573185b95f327 \
**UID**: SDOC-SSS-54 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-2`

**Statement**: The Requirement Tool's text language shall be machine-readable.

### Requirements data from multiple repositories

**MID**: 13f3e7765b494237893c1585a7c9dfd0 \
**UID**: SDOC-SSS-34 \
**Status**: Active

**Statement**:

The Requirement Tool shall allow reading requirements files from multiple
folders or repositories.

NOTE: The folders/repositories can be arbitrarily nested.

## Collaboration on requirements

**Type**: SECTION \
**MID**: efaa3e91045c4d49a70232f09a85ad35 \
**UID**: SECTION-RTS-Requirements-collaboration

### Support user accounts

**MID**: f9d65df46ff24b0da6cb2bf011f0fc70 \
**UID**: SDOC-SSS-65 \
**Status**: Draft

### Send notifications about updated requirements

**MID**: 29d0374556494f38977ec3c928aa894d \
**UID**: SDOC-SSS-66 \
**Status**: Draft

## Development process

**Type**: SECTION \
**MID**: f80a4b7ff03042849c3814c6cd5e5ca4 \
**UID**: SECTION-SSSS-Development-process

### Requirements engineering

**MID**: f16ea50f686e412f9c21d8096055bb47 \
**UID**: SDOC-SSS-76 \
**Status**: Active

**Statement**: The Requirements Tool's development process shall include the Requirements
Tool's own requirements engineering.

**Rationale**: A requirements tool is not a trivial project. A clear set of requirements for
the developed tool helps to structure the development and communicate the
functions of the tool to the developers and the users of the tool.

### Self-hosted requirements

**MID**: 0bebdf77108a499c87e5c0838204c39c \
**UID**: SDOC-SSS-50 \
**Status**: Active
**Relations**:
- **Type**: `Parent` \
  **ID**: `ZEP-15`

**Statement**: The Requirements Tool's requirements shall be developed and stored using the
Requirements Tool itself.

**Rationale**: While not strictly necessary, developing the requirements for the tool using the
tool itself aids developers in test-driving its functionality during the
requirement development phase. Moreover, having the tool host its own
requirements provides a tangible and dynamic illustration of how the tool can be
employed for crafting requirements documentation.

### Test coverage

**MID**: 1a39a758930040029db320d8466806c1 \
**UID**: SDOC-SSS-77 \
**Status**: Active

**Statement**:

The Requirements Tool's development process shall ensure:

- A testability of the tool.
- The highest possible coverage of the tool's code by test.
- Usage of modern testing methods to ensure adequate coverage of the tool's
  functions (e.g., command-line interface, web interface, smallest units of
  code, etc.).

**Rationale**: The presence of tests, the adequate selection of test methods and a high test
coverage are preconditions for a high quality of the requirements tool.

### Tool qualification

**MID**: 8cb5ac6812924f4c8f4afd156b2f021c \
**UID**: SDOC-SSS-78 \
**Status**: Active

**Statement**: The Requirements Tool's development process shall ensure that the tool can be
qualified for the use in critical product developments as required by the
rigorous technical standards (e.g., EN IEC 61508).

**Rationale**: Many project developments require a qualification of the tools used during the
development. A requirements tool is one of the critical tools that affect the
project development. If a requirement tool is developed to the higher standards
of quality, it simplifies the argument of bringing the tool forward and using it
in a particular project.

## Licensing and distribution

**Type**: SECTION \
**MID**: e4cd429e9ec04deabfd1fb1381c39e38 \
**UID**: SECTION-SSSS-Licensing-and-distribution

**Type**: TEXT \
**MID**: 92bf658bcddb4d2899b78c526fbddf38

This section outlines the requirements for the "free and open source" aspect of
the Requirements Tool.

### Open source

**MID**: 2f30b94fdc074c8fa5858dfccc6202e8 \
**UID**: SDOC-SSS-38 \
**Status**: Active

**Statement**: The Requirements Tool's source code shall be publicly available, e.g., hosted on
a code hosting platform such as GitHub or GitLab.

### Only open source dependencies

**MID**: 27b640de8cae44a680b23429c981bee9 \
**UID**: SDOC-SSS-39 \
**Status**: Active

**Statement**: The Requirement Tool's source code shall be based on open source software
components.

### Free

**MID**: 1338faad11204073a97212fa0fd11317 \
**UID**: SDOC-SSS-40 \
**Status**: Active

**Statement**:

The Requirements Tool shall be licensed under a permissive license, ensuring
no/minimal constraints on the utilization and dissemination of the project.

NOTE: Example of a permissive license: MIT, Apache 2.

**Rationale**: This requirement captures the essence of an open and free requirements
management tool.
