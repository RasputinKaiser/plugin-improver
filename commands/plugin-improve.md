---
description: Run one bounded, non-regressing improvement pass on a plugin
argument-hint: "[plugin-dir]"
---
Use the **plugin-improve** skill to run a single bounded improvement pass on the plugin at $ARGUMENTS (default: current directory): baseline, at most three highest-leverage fixes, the regression checklist, re-score, version bump, and ledger. If nothing clears the bar, report the plugin as stable rather than churning.
