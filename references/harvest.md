# Harvesting Voice Samples — internals

Harvest bootstraps teach samples from local chat transcripts and folders the user
declares as their own writing. The routed flow (harvest → classify → approve →
copy) is step 1 of `references/commands/teach.md`; this file holds the adapter
internals, the contamination tripwire, and the privacy rules that flow links to.

The transcript adapters only accept entries with explicit user authorship. Assistant
turns are dropped before candidate filtering, and unknown JSONL schemas are skipped with
a warning rather than guessed. This authorship separation is the product requirement:
assistant-authored transcript text must never enter candidates.

The `codex-jsonl` adapter reads Codex CLI/Desktop sessions, stored under
`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` and auto-detected by shape alongside
`claude-jsonl`. It harvests `event_msg` user_message text and user-role
`response_item` message content, and drops assistant/developer-role turns, tool
and reasoning plumbing, and `session_meta.base_instructions` outright. Codex also
injects non-user content into user-role turns: a repo's AGENTS.md dumped verbatim,
an `<environment_context>` banner, and similar wrapper tags. The adapter filters
those by structural marker, never by guessing at content, and counts them under
the `instruction-injection` drop reason instead of silently discarding them.

The contamination tripwire runs each kept candidate through `banned_phrase_scan` and
`structure_scan`. A hard violation, or two or more distinct scanner categories, marks
the sample as `suspect_ai: true`. Suspect samples are kept for human review, ranked last,
and must never be auto-approved.
A clean-styled, unmarked assistant paste inside a user turn is undetectable by parsing
and only weakly covered by the tripwire; mandatory human approval is the real defense.

The folder adapter treats `.md` and `.txt` files in a designated folder as user-authored
by declaration, but still runs the same tripwire. Dictated text with heavy `um`/`uh`
fillers is marked `dictated: true` and kept because spoken phrasing can still be useful
voice evidence.

Privacy: harvesting is local. Candidate files, classifier task files, and approved
`.unslop/voice/<name>/` samples should stay out of git unless the user explicitly chooses
otherwise.

Tiering: parsing and filtering are Tier 0 deterministic work. Situation/register
classification can be fanned out to the cheapest capable model through the emitted task
files. Final approval stays human.
