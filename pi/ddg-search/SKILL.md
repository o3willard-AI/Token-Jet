---
name: ddg-search
description: Keyless web search via DuckDuckGo. Use for searching documentation, API references, error messages, or any web content. No API key required.
---

# DuckDuckGo Search

Web search and content extraction using DuckDuckGo's HTML interface. No API key or account required.

## Search

```bash
{baseDir}/search.js "query"                         # Basic search (5 results)
{baseDir}/search.js "query" -n 10                   # More results (max 25)
{baseDir}/search.js "query" --content               # Include page content as markdown
{baseDir}/search.js "query" --freshness pw          # Results from last week
{baseDir}/search.js "query" -n 3 --content          # Combined options
```

### Options

- `-n <num>` — Number of results (default: 5, max: 25)
- `--content` — Fetch and include readable page content as markdown
- `--freshness <period>` — Filter by time:
  - `pd` — Past day
  - `pw` — Past week
  - `pm` — Past month
  - `py` — Past year

## Extract Page Content

```bash
{baseDir}/content.js https://example.com/article
```

Fetches any URL and extracts the readable content as markdown. Useful when you have a specific URL from search results or documentation.

## Output Format

```
--- Result 1 ---
Title: Page Title
Link: https://example.com/page
Snippet: Description from search results
Content: (if --content flag used)
  Markdown content extracted from the page...

--- Result 2 ---
...
```

## When to Use

- Searching for documentation, API references, or examples
- Looking up error messages or stack traces
- Finding library changelogs or release notes
- Any task requiring web information without interactive browsing
- Fetching content from a specific URL you already know

## Tips

- For coding questions, include the language and version: `"python 3.12 walrus operator"`
- For error messages, quote the exact error text
- Use `--content` when snippets alone aren't enough — fetches the full page
- Combine `-n 3 --content` to get fewer but richer results
