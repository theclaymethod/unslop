# /unslop rewrite

Read [the core contract](../core-contract.md). Read the source before looking at scanner output. From the skill root, with `INPUT` set to the source text:

```bash
python3 scripts/extract_constraints.py <<< "$INPUT"
python3 scripts/banned_phrase_scan.py <<< "$INPUT"
python3 scripts/structure_scan.py <<< "$INPUT"
python3 scripts/silhouette_scan.py <<< "$INPUT"
```

For documentation or social prose, pass `--genre docs` or `--genre social` to the structure scanner. Use the phrase scanner's `--include-quoted` only for an explicit request to audit quoted examples.

Confirm or protect findings in context. With no confirmed defect, return the source verbatim and stop. Otherwise, repair confirmed spans, run the [validation checks](../core-contract.md#validation), and follow the entrypoint's output format. For multi-agent execution see [the pipeline](../pipeline.md); detector packs live in [packs](../packs/).
