# Pinned EvoTool source snapshot

- Upstream: https://github.com/SYang2000/ACL_2026_EvoTool
- Commit: \`6a82719ea6e22cf23f963078e2527094e50b47f6\`
- License: MIT; see \`LICENSE\`.
- \`SOURCE_LOCK.json\` pins the exact Git Blob SHA of each retained source file.

The snapshot is intentionally limited to the published tau-bench Retail adapter, tool implementations, success evaluator, progress metric, episode runner, split loader, tool-card registry, and base config. It is used only for deterministic source and environment conformance tests. It is not a complete clone of the EvoTool repository.

Do not edit these pinned files in place. Any corrected adapter or experimental treatment must live in a separate project path and retain the original implementation as an immutable comparator.

The conformance audit imports these files without running an LLM. It patches only the DB directory to the byte-identical official legacy Retail DB already vendored under \`vendor/tau_bench/\`.
