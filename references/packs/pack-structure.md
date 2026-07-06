# Pack: Structure

Use this pack for document-level AI structure. Do not report isolated phrases unless they create a macro pattern.

## Look For

- `structure_scan.py` flags: `sentence_burstiness`, `conclusion_coda`, `bold_colon_listicle`, `one_line_staccato`, `connective_paragraph_openers`, `signpost_density`, `opener_repetition`, `participial_closer_share`.
- Concrete thresholds to self-check: average sentence length under 8 or over 34 words is suspicious; sentence-length variance under 18 on 5+ sentences suggests uniform rhythm; 3+ one-line paragraphs under 8 words suggests staccato; 3+ consecutive paragraphs opened by connectives/signposts suggests scaffolding; 4+ repeated paragraph openers is blocking; 35%+ participial sentence endings suggests templated cadence.
- Judge-only macro tells from `taboo-phrases.md`: both-sidesism, templated redemption arc, preview/recap symmetry, over-determination, uniform emotional register.
- `silhouette_scan.py` flags idea arrangement above the surface: `scaffold_opener_share`, `callback_content` (recap loop), `role_entropy_bits`, `preview_fulfillment`, `heading_preview`, composited into `silhouette_penalty` (flags at `>= 1.0`).
- A high `silhouette_penalty` means the document follows a template outline (preview-then-fulfill, rotating scaffold openers, closing recap); cite the specific flagged metric, not just the composite.
- Cue-deletion evades silhouette but not surface repetition: pair `silhouette_scan` with `structure_scan` (`opener_repetition`, `one_line_staccato`) so a stripped-connective attack still fails one of the two fences.

Genre matters. `--genre docs` can allow reference-doc structure; `--genre social` can allow deliberate social cadence. Output still fails if the genre excuse is false.

## Emit

Return JSON findings only:

```json
{"span":"paragraphs 2-5","rule":"connective_paragraph_openers","pack":"pack-structure","severity":"hard","note":"Paragraphs advance by scaffold words instead of content."}
```

Quote the smallest span that shows the macro pattern. For whole-document patterns, use paragraph ranges.

## Examples

- "However... In addition... Consequently... In the end..." -> report connective scaffold and coda.
- A technical comparison with "In Rails / In Django / In raw SQL" once -> no finding.
- A story that always moves problem -> lesson -> uplift -> moral -> report `macro_redemption_arc`.
- A report whose conclusion only recaps the intro -> report `macro_preview_recap`.
