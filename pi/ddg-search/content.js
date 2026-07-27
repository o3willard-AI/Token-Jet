#!/usr/bin/env node
// Fetch any URL and extract its readable content as markdown.
// Supports pagination via --page N and --page-size N so large pages
// can be read in controllable chunks without overflowing the context window.

import { Readability } from "@mozilla/readability";
import { JSDOM } from "jsdom";
import TurndownService from "turndown";
import { gfm } from "turndown-plugin-gfm";

const args = process.argv.slice(2);

// Parse --page and --page-size flags
let page = 1;
let pageSize = 3000;

const pageIdx = args.indexOf("--page");
if (pageIdx !== -1 && args[pageIdx + 1]) {
	page = Math.max(1, parseInt(args[pageIdx + 1], 10) || 1);
	args.splice(pageIdx, 2);
}

const psIdx = args.indexOf("--page-size");
if (psIdx !== -1 && args[psIdx + 1]) {
	pageSize = Math.max(500, parseInt(args[psIdx + 1], 10) || 3000);
	args.splice(psIdx, 2);
}

const url = args[0];

if (!url) {
	console.log("Usage: content.js <url> [--page N] [--page-size N]");
	console.log("\nExtracts readable content from a webpage as markdown.");
	console.log("Large pages are split into page-size chunks (default 3000 chars).");
	console.log("\nOptions:");
	console.log("  --page N        Which page to return (default: 1)");
	console.log("  --page-size N   Chars per page (default: 3000, min: 500)");
	console.log("\nExamples:");
	console.log("  content.js https://nodejs.org/api/fs.html");
	console.log("  content.js https://nodejs.org/api/fs.html --page 2");
	console.log("  content.js https://doc.rust-lang.org/book/ch04.html --page-size 2000");
	process.exit(1);
}

const BROWSER_UA =
	"Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 " +
	"(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

function htmlToMarkdown(html) {
	const td = new TurndownService({ headingStyle: "atx", codeBlockStyle: "fenced" });
	td.use(gfm);
	td.addRule("removeEmptyLinks", {
		filter: node => node.nodeName === "A" && !node.textContent?.trim(),
		replacement: () => "",
	});
	return td
		.turndown(html)
		.replace(/\[\\?\[\s*\\?\]\]\([^)]*\)/g, "")
		.replace(/ +/g, " ")
		.replace(/\s+,/g, ",")
		.replace(/\s+\./g, ".")
		.replace(/\n{3,}/g, "\n\n")
		.trim();
}

function paginate(fullText, page, pageSize) {
	const totalPages = Math.max(1, Math.ceil(fullText.length / pageSize));
	const clampedPage = Math.min(page, totalPages);
	const start = (clampedPage - 1) * pageSize;
	const end = Math.min(start + pageSize, fullText.length);
	const chunk = fullText.slice(start, end);
	const header = `[Page ${clampedPage}/${totalPages} — chars ${start + 1}–${end} of ${fullText.length}]`;
	const footer = clampedPage < totalPages
		? `\n\n[More content available — call fetch_url with page=${clampedPage + 1}]`
		: "";
	return `${header}\n\n${chunk}${footer}`;
}

try {
	const resp = await fetch(url, {
		headers: {
			"User-Agent":      BROWSER_UA,
			"Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
			"Accept-Language": "en-US,en;q=0.9",
		},
		signal: AbortSignal.timeout(15000),
	});

	if (!resp.ok) {
		console.error(`HTTP ${resp.status}: ${resp.statusText}`);
		process.exit(1);
	}

	const html = await resp.text();
	const dom  = new JSDOM(html, { url });

	// Try Readability first — best quality for articles and docs
	const article = new Readability(dom.window.document).parse();
	if (article?.content) {
		const md = htmlToMarkdown(article.content);
		const titleLine = article.title ? `# ${article.title}\n\n` : "";
		// Only prepend title on page 1
		const body = page === 1 ? titleLine + md : md;
		console.log(paginate(body, page, pageSize));
		process.exit(0);
	}

	// Fallback: strip page chrome and extract main content
	const doc2 = new JSDOM(html, { url }).window.document;
	doc2.querySelectorAll("script, style, noscript, nav, header, footer, aside")
		.forEach(el => el.remove());

	const title = doc2.querySelector("title")?.textContent?.trim();
	const main  = doc2.querySelector("main, article, [role='main'], .content, #content")
		?? doc2.body;

	const inner = main?.innerHTML ?? "";
	if (inner.trim().length > 100) {
		const md = htmlToMarkdown(inner);
		const titleLine = (page === 1 && title) ? `# ${title}\n\n` : "";
		console.log(paginate(titleLine + md, page, pageSize));
	} else {
		console.error("Could not extract readable content from this page.");
		process.exit(1);
	}
} catch (e) {
	console.error(`Error: ${e.message}`);
	process.exit(1);
}
