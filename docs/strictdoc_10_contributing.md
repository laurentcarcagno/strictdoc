# Contributing to StrictDoc

**Grammar**: strictdoc_10_contributing.gra.md \
**Version**: Git commit: @GIT_VERSION, Git branch: @GIT_BRANCH \
**Date**: @GIT_COMMIT_DATETIME \
**Enable MID**: True

**Type**: TEXT \
**MID**: 13fe652f160d4af69e869c28a155437d

Contributions to StrictDoc are welcome and appreciated.
Presented below is a condensed checklist that summarises the information
of the development guide, see [LINK: DEVGUIDE_GETTING_STARTED].

## Contributor checklist

**Type**: SECTION \
**MID**: ec078ab0d7564738acd2961f72abb2c9

**Type**: TEXT \
**MID**: ae0fc6d87b114137ab6da7c9b5647b62

Before opening your Pull Request, the contributor is encouraged to do the
following steps:

1. Run `invoke check` tasks locally. This task calls several lint and test
   scripts and it is the very task that is run by the GitHub CI process.
2. A contribution that contains changes to the StrictDoc's codebase shall also
   include tests that exercise the changed behavior. A contribution without any
   tests is unlikely to be accepted (with the exception of "code climate"
   changes, see [LINK: DEVGUIDE_PYTHON_CODE]).
3. Follow the conventions of the section [LINK: DEVGUIDE_GIT_WORKFLOW].
   A clean Git history and conventional commit names are expected for every
   single contribution.
4. If the contribution is not trivial, read through the complete development
   guide.
5. If the contribution is not trivial, please update the Release Notes with a high-level summary of your contribution. Refer to the release notes from previous releases for guidance on what information is desirable.

## How can I help?

**Type**: SECTION \
**MID**: 8b40cc35f3524bc7b4e444321c080837

### Spread the word

**Type**: SECTION \
**MID**: 8e346888911649f2a3aaf49763aaef24

**Type**: TEXT \
**MID**: 07462b02027a423a85ab68525b78ac67

If you like the StrictDoc project and use it in your daily work, there are
several things you could do besides contributing Pull Requests:

- Star the StrictDoc repository to show your appreciation of the project.
- Write a blog post or a tutorial about using StrictDoc to achieve some goal.
- Write an email to <strictdoc.project@gmail.com> and tell us how
  you are using StrictDoc and which features you are missing. We somewhat lack
  enough feedback from our users.

### ReqIF users

**Type**: SECTION \
**MID**: 2696c7fda6d440f3a290f202bee08fe6

**Type**: TEXT \
**MID**: 9cfbb025525f41c5a195be0e637dffee

The existing capability of StrictDoc to export/import SDoc to ReqIF is very
basic. If you have to deal with ReqIF and you experience errors/crashes when
using StrictDoc against ReqIF files, feel free to contribute the anonymized
ReqIF files via StrictDoc Issues on GitHub, and we will take care of your
specific case.

It is straightforward to create an anonymized version of a ReqIF file. Just
reduce your file to the section that causes troubles in import or export and
replace all your business-specific titles/texts to some `Lorem ipsum...`
boilerplate, see <https://www.loremipsum.de/>.
