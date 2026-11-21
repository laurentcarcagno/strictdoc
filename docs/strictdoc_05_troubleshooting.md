# Troubleshooting

**Grammar**: strictdoc_05_troubleshooting.gra.md \
**UID**: SDOC_TROUBLESHOOTING \
**Version**: Git commit: @GIT_VERSION, Git branch: @GIT_BRANCH \
**Date**: @GIT_COMMIT_DATETIME \
**Enable MID**: True \
**View style**: Narrative

**Type**: TEXT \
**MID**: 7e3481d51ad14767b5c97132cad2e0a6

This document summarizes solutions to the most common issues reported by
StrictDoc users.

## Caching issues

**Type**: SECTION \
**MID**: 17152ac7de9f4c138b85e2956091206f

**Type**: TEXT \
**MID**: 9a32ac13510d401cbc1a608259652c78

<div class="sdoc-admonition sdoc-note" role="note">
<p class="sdoc-admonition-title">Note</p>

**TL;DR:** If you encounter errors related to reading data, make sure to delete the StrictDoc cache folder located at `output/_cache` or in the custom directory if specified by the `cache_dir` option in the `strictdoc_config.py` configuration file. See [LINK: SECTION-UG-Path-to-cache-dir].

</div>

StrictDoc caches many artifacts on disk. Some artifacts are cached using
Python’s [pickle](https://docs.python.org/3/library/pickle.html) module, while
others are written directly to disk.

The pickle module serializes Python objects to disk. The issue with this
approach is that when StrictDoc changes the schema of its objects (e.g., when
SDocNode or SDocDocument objects gain a new property or a property type
changes), an outdated object may be read from the cache after upgrading to a new
StrictDoc version. While a more systematic solution might be implemented in the
future, the current workaround is to manually delete the StrictDoc cache folder.
