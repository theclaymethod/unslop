# Pack: Phrases Core

Use this pack only for scanner-backed phrase, jargon, and scaffold tells. Do not judge facts, register-preservation, macro structure, or the rewriter's house style here.

## Look For

- Throat-clearing and reader steering: "here's the thing", "let's dive in", "to answer your question".
- Emphasis crutches and inflated significance: "let that sink in", "underscores the importance", "a testament to".
- Business, academic, and promotional vocabulary used as generic polish: "leverage", "seamless", "vibrant", "rich cultural heritage".
- Vague attribution or false agency: unnamed "experts", numbers that "speak for themselves", data that "tells a story".
- Formulaic scaffolds: ordinal sequencing, generic conclusions, rhetorical setup questions, novelty claims, numbered-list hype.

Use `references/taboo-phrases.md` as the authoritative phrase catalog. Report only spans this pack owns.

## Emit

Return JSON findings only:

```json
{"span":"...","rule":"throat_clearing","pack":"pack-phrases-core","severity":"hard","note":"Cut the opener and start with the claim."}
```

Use `hard` for always-bad boilerplate and `soft` for context-dependent wording. Leave legitimate literal, legal, medical, code, or domain-specific uses unreported.

## Examples

- "Here's the thing: the data speaks for itself." -> report "Here's the thing" and "speaks for itself".
- "The loan used 3:1 leverage." -> no finding; finance sense is literal.
- "This update unlocks seamless cross-functional synergy." -> report "seamless" and "synergy".
- "Some critics argue the policy failed." -> report vague attribution unless the critics are named nearby.
