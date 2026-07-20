#!/usr/bin/env node
// Fetch any URL and extract its readable content as markdown.
// No API key required. Used by pi when the model needs to read a specific page.

import { Readability } from "@mozilla/readability";
import { JSDOM } from "jsdom";
import TurndownService from "turndown";
import { gfm } from "turndown-plugin-gfm";

const url = process.argv[2];

if (!url) {
	console.log("Usage: content.js <url>");
	console.log("\nExtracts readable content from a webpage as markdown.");
	console.log("\nExamples:");
	console.log("  content.js https://nodejs.org/api/fs.html");
	console.log("  content.js https://doc.rust-lang.org/book/ch04-01-what-is-ownership.html");
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
		if (article.title) console.log(`# ${article.title}\n`);
		console.log(htmlToMarkdown(article.content));
		process.exit(0);
	}

	// Fallback: strip page chrome and extract main content
	const doc2 = new JSDOM(html, { url }).window.document;
	doc2.querySelectorAll("script, style, noscript, nav, header, footer, aside")
		.forEach(el => el.remove());

	const title = doc2.querySelector("title")?.textContent?.trim();
	const main  = doc2.querySelector("main, article, [role='main'], .content, #content")
		?? doc2.body;

	if (title) console.log(`# ${title}\n`);

	const inner = main?.innerHTML ?? "";
	if (inner.trim().length > 100) {
		console.log(htmlToMarkdown(inner));
	} else {
		console.error("Could not extract readable content from this page.");
		process.exit(1);
	}
} catch (e) {
	console.error(`Error: ${e.message}`);
	process.exit(1);
}
