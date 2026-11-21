# Technical Note: Zephyr requirements tool requirements

**Grammar**: strictdoc_41_Zephyr_requirements.gra.md \
**Version**: Git commit: @GIT_VERSION, Git branch: @GIT_BRANCH \
**Date**: @GIT_COMMIT_DATETIME \
**Prefix**: ZEP- \
**Root**: True \
**Enable MID**: True

## Multiple files / include mechanism

**MID**: 68e87901205c4b0dbb6a0071479330b5 \
**UID**: ZEP-1 \
**Status**: Active

**Statement**: Requirements or groups of requirements shall be distributable over several files
and still form a full specification (document) via some kind of include
mechanism.

**Rationale**: In a future constellation the requirements shall be written resp. update with
the code in the same PR. Smallish requirements files per topic / component next
to the code in the same repo allow a better workflow than one huge requirements
file somewhere.

## Clear separation of requirements (machine-readable)

**MID**: 36415af620f645388af4dc51c2a19b97 \
**UID**: ZEP-2 \
**Status**: Active

**Statement**: Requirements objects shall be clearly separated from each other, also when
organized in the same file.

**Rationale**: For exporting or machine processing, a clear separation of requirements objects
is a prerequisite.

## Custom fields

**MID**: 7a9e26240f5c4fe29143cf3348ac3d3b \
**UID**: ZEP-3 \
**Status**: Active

**Statement**: Requiremements objects shall be configurable to create several types with a
number of custom fields.

**Rationale**: Requirements on software level may need to hold different information than on
the architecture/interface and on the component level. By having typed
requirements objects, linkages between requirements objects can be verified and
filtered (start_object_type – link_role_type --> end_object_type)".

## Links

**MID**: a5928d6204a84d02a3c367d6dbc54092 \
**UID**: ZEP-4 \
**Status**: Active

**Statement**: Linking shall in general be supported between any requirement object of any
object type in a 1:n manner.

**Rationale**: A SAIS requirement will link to a SRS requirement via «refines» link. A SITS
test case will link to the same SAIS requirement.

## Multiple link roles

**MID**: 55bbe693d12d4e00956d41a837ef15ef \
**UID**: ZEP-5 \
**Status**: Active

**Statement**: Links shall be configurable to create multiple link roles.

**Rationale**: Link roles and requirements object types allow to verify, that the traceability
is consistent.

## ReqIF export

**MID**: b58c387f3a2d4cf6a540e279dbe49e47 \
**UID**: ZEP-6 \
**Status**: Active

**Statement**: Requirements specification shall be exportable to ReqIF.

**Rationale**: Will/may be used to as exchange format to generate a requirements and
traceability documentation.

## CSV

**MID**: 17a141add32f4d7696b5a74b6507b9aa \
**UID**: ZEP-7 \
**Status**: Active

**Statement**: Requirements specification shall be exportable to CSV.

**Rationale**: Will/may be used to as exchange format to generate a requirements and
traceability documentation.

## Unique ID management

**MID**: d0d258d8640443578c7ec508c014b50d \
**UID**: ZEP-8 \
**Status**: Active

**Statement**:

Requirements objects shall allow unique ID management when adding new
requirements on different branches.

Options could be:

- UUID: no checking required, but not handy
- Manually assigned: collision checking required
- Centralized: when not affected by branching".

**Rationale**: Centralized object ID management might collide with a branching, PR, merging
process approach commonly used in the rest of the project.

## Text formatting capabilities

**MID**: 611546bf2409417e8844f93854d54268 \
**UID**: ZEP-9 \
**Status**: Active

**Statement**:

The description field shall allow for formatting such as:

- lists
- tables
- headings
- UML diagrams
- etc.

**Rationale**: In some cases a plain text requirement is not sufficiently clear and requires
formatting or even UML diagrams.

## Minimal requirement field set

**MID**: f1f6da87da5c49d1b8c3441b14863975 \
**UID**: ZEP-10 \
**Status**: Active

**Statement**:

A requirements object shall at least comprise the following fields (or similar):

- title
- ID
- Description
- Status
- Outbound links
- Inbound links (optional?)

**Rationale**: TBD

## Requirements to source code traceability

**MID**: 55cbd9b658164414adb0c13b0446e3f7 \
**UID**: ZEP-11 \
**Status**: Active

**Statement**: Linking from requirements objects to code or from code to requirements objects
via ID shall be supported.

**Rationale**: For safety development and certification linking to code is required.

## Non-intrusive links in source code

**MID**: a2930225168147808e6554a4da49aeb4 \
**UID**: ZEP-12 \
**Status**: Active

**Statement**: Linking from code to requirements objects via ID shall be least code intrusive.

**Rationale**: Code with lots of meta information in it via comment tags, makes the code less
readable. Links should best be hidden in existing comment structures e.g.
function headers and not be extra tags.

## Structuring requirements in documents

**MID**: 2614d6673a594da995df672e8943839e \
**UID**: ZEP-13 \
**Status**: Active

**Statement**: Requirements objects shall be structurable in a document like manner (with
requirements ordering, and organized in chapters).

**Rationale**: A collection of unorganized requirements as a specifications are hard to read
and understand. They should be organizable in topic chapters or similar.

## Status field

**MID**: a92a28ce3bcb4b3590f36e778a604ccb \
**UID**: ZEP-14 \
**Status**: Active

**Statement**: Each requirements object type shall have a configurable status workflow.

**Rationale**: Requirements may be in different statuses such as Draft, InReview, Approved.
Dependent on the used process is rather reflected in the development work
(branch=draft, PR under Review=InReview, PR merged to main=Approved.

## Tool Qualifiability

**MID**: b74919612283422a9e139418a20926c6 \
**UID**: ZEP-15 \
**Status**: Active

**Statement**: The Requirement Tool shall be qualifiable for use in safety-related and/or
security-related development. At the very least, the Requirement Tool shall come
with its own set of requirements, which shall be amenable to validation in
compliance with the relevant standards.

**Rationale**: Certification of Zephyr-based products.
