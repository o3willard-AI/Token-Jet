#!/usr/bin/env node
// DuckDuckGo web search — no API key required.
//
// Uses a two-step session flow that mirrors what a real browser does:
//   1. GET duckduckgo.com to obtain a short-lived vqd session token
//   2. GET html.duckduckgo.com/html/ with that token to retrieve results
//
// The vqd token is DDG's bot-detection gate. Extracting and replaying it
// (along with the session cookies) is the only reliable way to get real
// search results without an API key.

import { Readability } from "@mozilla/readability";
import { JSDOM } from "jsdom";
import TurndownService from "turndown";
import { gfm } from "turndown-plugin-gfm";

// ── CLI argument parsing ──────────────────────────────────────────────────────

const args = process.argv.slice(2);

const contentIndex = args.indexOf("--content");
const fetchContent = contentIndex !== -1;
if (fetchContent) args.splice(contentIndex, 1);

let numResults = 5;
const nIndex = args.indexOf("-n");
if (nIndex !== -1 && args[nIndex + 1]) {
	numResults = Math.min(parseInt(args[nIndex + 1], 10) || 5, 25);
	args.splice(nIndex, 2);
}

let freshness = null;
const freshnessIndex = args.indexOf("--freshness");
if (freshnessIndex !== -1 && args[freshnessIndex + 1]) {
	freshness = args[freshnessIndex + 1];
	args.splice(freshnessIndex, 2);
}

const query = args.join(" ").trim();

if (!query) {
	console.log("Usage: search.js <query> [-n <num>] [--content] [--freshness <period>]");
	console.log("\nOptions:");
	console.log("  -n <num>              Number of results (default: 5, max: 25)");
	console.log("  --content             Fetch readable content from each result page");
	console.log("  --freshness <period>  pd=past day, pw=past week, pm=past month, py=past year");
	console.log("\nExamples:");
	console.log('  search.js "python pathlib read file"');
	console.log('  search.js "rust async await" -n 10');
	console.log('  search.js "nodejs fs module" --content');
	process.exit(1);
}

// ── Browser-like request headers ──────────────────────────────────────────────
// DDG's bot detection looks at UA, Accept-Language, and Referer.
// These values match a real aarch64 Linux Chrome browser.

const BROWSER_UA =
	"Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 " +
	"(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const BASE_HEADERS = {
	"User-Agent":      BROWSER_UA,
	"Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
	"Accept-Language": "en-US,en;q=0.9",
	"Accept-Encoding": "identity",
};

// ── Minimal cookie jar ────────────────────────────────────────────────────────
// We carry the session cookie DDG sets on step 1 into step 2.

let cookieJar = "";

function absorbCookies(setCookieHeader) {
	if (!setCookieHeader) return;
	const headers = Array.isArray(setCookieHeader) ? setCookieHeader : [setCookieHeader];
	for (const hdr of headers) {
		const pair = hdr.split(";")[0].trim();
		if (!pair) continue;
		const name = pair.split("=")[0];
		const existing = cookieJar ? cookieJar.split("; ").filter(c => !c.startsWith(name + "=")) : [];
		existing.push(pair);
		cookieJar = existing.join("; ");
	}
}

// ── Fetch with retry + cookie forwarding ──────────────────────────────────────

async function fetchRetry(url, opts = {}, retries = 3) {
	let lastErr;
	for (let attempt = 1; attempt <= retries; attempt++) {
		try {
			const headers = { ...BASE_HEADERS, ...opts.headers };
			if (cookieJar) headers["Cookie"] = cookieJar;

			const resp = await fetch(url, {
				...opts,
				headers,
				signal: AbortSignal.timeout(15000),
			});

			// Absorb any new cookies
			const sc = resp.headers.get("set-cookie");
			if (sc) absorbCookies(sc);

			return resp;
		} catch (err) {
			lastErr = err;
			if (attempt < retries) {
				await new Promise(r => setTimeout(r, 1200 * attempt));
			}
		}
	}
	throw lastErr;
}

// ── Step 1: Obtain the vqd session token ─────────────────────────────────────
// DDG embeds a short-lived vqd token in the search page HTML.
// Replaying it in step 2 is what makes us look like a real session.

async function getVqd(query) {
	const url = `https://duckduckgo.com/?q=${encodeURIComponent(query)}&ia=web`;
	const resp = await fetchRetry(url);
	const html = await resp.text();

	// vqd appears as vqd="4-xxx" or vqd=4-xxx
	const m = html.match(/vqd[=\s:"']+([0-9][0-9\-]+)/);
	if (!m) {
		if (html.includes("anomaly-modal") || html.includes("CAPTCHA")) {
			throw new Error(
				"DuckDuckGo returned a CAPTCHA. " +
				"Wait 60 seconds and try again, or reduce search frequency."
			);
		}
		throw new Error("Could not find vqd token in DuckDuckGo response.");
	}
	return m[1];
}

// ── Step 2: Fetch and parse HTML results ──────────────────────────────────────

const FRESHNESS_MAP = { pd: "d", pw: "w", pm: "m", py: "y" };

async function searchDDG(query, numResults, freshness) {
	const vqd = await getVqd(query);

	const params = new URLSearchParams({ q: query, vqd });
	if (freshness && FRESHNESS_MAP[freshness]) {
		params.set("df", FRESHNESS_MAP[freshness]);
	}

	const url = `https://html.duckduckgo.com/html/?${params}`;
	const resp = await fetchRetry(url, {
		headers: { "Referer": "https://duckduckgo.com/" },
	});

	if (!resp.ok) {
		throw new Error(`DuckDuckGo returned HTTP ${resp.status}.`);
	}

	const html = await resp.text();

	if (html.includes("anomaly-modal")) {
		throw new Error(
			"DuckDuckGo rate-limited this request. Wait 60 seconds and try again."
		);
	}

	const dom = new JSDOM(html);
	const doc = dom.window.document;

	// Results live in <div class="result results_links results_links_deep web-result">
	const resultEls = doc.querySelectorAll(".result.results_links_deep");
	const results = [];

	for (const el of resultEls) {
		if (results.length >= numResults) break;

		const titleEl   = el.querySelector(".result__a");
		const snippetEl = el.querySelector(".result__snippet");
		if (!titleEl) continue;

		const title   = titleEl.textContent?.trim() ?? "";
		const snippet = snippetEl?.textContent?.trim() ?? "";

		// href is a DDG redirect: //duckduckgo.com/l/?uddg=<encoded-url>&rut=...
		// Decode the uddg parameter to get the actual destination URL.
		let link = titleEl.getAttribute("href") ?? "";
		try {
			const full = link.startsWith("//") ? "https:" + link : link;
			const uddg = new URL(full).searchParams.get("uddg");
			if (uddg) link = decodeURIComponent(uddg);
		} catch {
			// leave link as-is if URL parsing fails
		}

		if (!title || !link) continue;
		results.push({ title, link, snippet });
	}

	return results;
}

// ── HTML → Markdown ───────────────────────────────────────────────────────────

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

// ── Page content fetcher ──────────────────────────────────────────────────────

async function fetchPageContent(url) {
	try {
		const resp = await fetch(url, {
			headers: {
				"User-Agent": BROWSER_UA,
				"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
			},
			signal: AbortSignal.timeout(12000),
		});
		if (!resp.ok) return `(HTTP ${resp.status})`;

		const html = await resp.text();
		const dom  = new JSDOM(html, { url });

		// Try Readability first (best quality)
		const article = new Readability(dom.window.document).parse();
		if (article?.content) {
			return htmlToMarkdown(article.content).substring(0, 2000);
		}

		// Fallback: strip chrome, extract main element
		const doc2 = new JSDOM(html, { url }).window.document;
		doc2.querySelectorAll("script, style, noscript, nav, header, footer, aside")
			.forEach(el => el.remove());
		const main = doc2.querySelector("main, article, [role='main'], .content, #content")
			?? doc2.body;
		const text = main?.textContent ?? "";
		if (text.trim().length > 100) return text.trim().substring(0, 2000);

		return "(Could not extract readable content from this page)";
	} catch (e) {
		return `(Error fetching page: ${e.message})`;
	}
}

// ── Main ──────────────────────────────────────────────────────────────────────
// Hard cap on total stdout to prevent context window overflow regardless of
// how this script is invoked (bash tool or web_search tool wrapper).
const MAX_TOTAL_CHARS = 5000;

try {
	const results = await searchDDG(query, numResults, freshness);

	if (results.length === 0) {
		console.error("No results found. Try rephrasing your query.");
		process.exit(0);
	}

	if (fetchContent) {
		for (const r of results) {
			r.content = await fetchPageContent(r.link);
		}
	}

	const lines = [];
	for (let i = 0; i < results.length; i++) {
		const r = results[i];
		lines.push(`--- Result ${i + 1} ---`);
		lines.push(`Title: ${r.title}`);
		lines.push(`Link: ${r.link}`);
		lines.push(`Snippet: ${r.snippet}`);
		if (r.content) {
			lines.push(`Content:\n${r.content}`);
		}
		lines.push("");
	}

	let output = lines.join("\n");
	if (output.length > MAX_TOTAL_CHARS) {
		output = output.slice(0, MAX_TOTAL_CHARS) +
			`\n\n[Output truncated at ${MAX_TOTAL_CHARS} chars. Use fetch_url for full page content.]`;
	}
	console.log(output);
} catch (e) {
	console.error(`Error: ${e.message}`);
	process.exit(1);
}
