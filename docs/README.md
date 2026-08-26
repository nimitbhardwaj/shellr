# docs/

This directory contains additional documentation that lives with the code
rather than the source modules.

## Files

| File | What it is |
|---|---|
| [`SKILL.md`](SKILL.md) | Hermes skill — instructions for LLMs that drive the phone via the shellr daemon. Mirrors `~/.hermes/skills/shellr-phone-control/SKILL.md`. |
| [`llm-session-install.md`](llm-session-install.md) | Step-by-step install playbook for **LLM agents**. Describes what to drive via tools and what minimal physical steps the user has to do on the phone. **Read this if you're an LLM about to install shellr.** |

## Why both?

The master skill lives in Hermes's skill store (`~/.hermes/skills/`) and
should stay there — it's loaded automatically when the trigger conditions
match. This `docs/` copy is for distribution: anyone installing shellr
from GitHub gets the skill alongside the code, can update both from one
`git pull`, and can edit here in their fork.

## Updating

When you change the daemon's behaviour or add RPC methods:

1. Update `docs/SKILL.md` to match.
2. Mirror the change to `~/.hermes/skills/shellr-phone-control/SKILL.md`
   (master copy stays authoritative for runtime triggers).
3. Commit both in the same PR.
