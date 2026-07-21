---
name: ddg-search
description: "Search the web with DuckDuckGo. Run ddg-search \"query\" in bash. No API key needed."
---

# Web Search

To search the web, run this bash command:

```bash
ddg-search "your search query"
```

To fetch the full content of a specific URL:

```bash
fetch-url https://example.com/page
```

## Options for ddg-search

- `-n 10` — return more results (default 5, max 25)
- `--content` — include full page text for each result
- `--freshness pd` — past day; `pw` = past week; `pm` = past month

## Examples

```bash
ddg-search "python asyncio tutorial"
ddg-search "nodejs fs readFile example" -n 10
ddg-search "rust borrow checker error E0502" --content
ddg-search "llama.cpp CUDA build" --freshness pw
fetch-url https://docs.python.org/3/library/asyncio.html
```

## Output

Each result looks like:
```
--- Result 1 ---
Title: ...
Link: https://...
Snippet: ...
```

With `--content`, a `Content:` block with the full page markdown is added.
