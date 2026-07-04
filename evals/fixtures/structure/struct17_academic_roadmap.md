We study how retrieval quality degrades when embedding models are quantized below eight bits. Prior work measured recall on synthetic benchmarks only, so the field's working assumptions about safe compression ratios rest on data that never saw a real query distribution. We use production query logs from three deployments, spanning eleven languages. The picture changes sharply.

Section 2 reviews related work on embedding compression. Section 3 describes our query-log corpus and evaluation protocol. Section 4 presents the quantization experiments. Section 5 discusses deployment implications.

The headline result is blunt. Below five bits, tail-language recall collapses even when English recall looks fine, and the collapse is invisible to any aggregate metric a practitioner would normally monitor in production. We release our per-language evaluation splits.
