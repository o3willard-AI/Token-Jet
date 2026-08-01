import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execFile, spawnSync } from "child_process";
import { readdirSync, statSync } from "fs";
import { homedir } from "os";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

const SERVER_BASE = "http://127.0.0.1:1234";
const DEFAULT_CTX = 20480; // Must match MAX_CTX_HARD_CAP in jetson-infer
const SKILL_DIR = `${homedir()}/Token-Jet/pi/ddg-search`;
const SHARED_DIR = `${homedir()}/shared`;

// Returned when the server is unreachable or when pi requests a sync-only
// refresh (allowNetwork: false). Must NOT be an empty array — pi evaluates
// the return value with `arr ? use_it : keep_static`, and [] is truthy, so
// returning [] wipes the static models list from the registration config.
const FALLBACK_MODEL = {
  id: "local",
  name: "Jetson Local Model",
  api: "openai-completions" as const,
  input: ["text"] as string[],
  reasoning: false,
  contextWindow: DEFAULT_CTX,
  maxTokens: DEFAULT_CTX,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
};

export default function (pi: ExtensionAPI) {
  pi.registerProvider("jetson-local", {
    name: "Jetson (llama.cpp)",
    baseUrl: `${SERVER_BASE}/v1`,
    api: "openai-completions",
    // Auth credential is also written to ~/.pi/agent/auth.json by the
    // install script. apiKey here is a belt-and-suspenders backup.
    apiKey: "none",

    // Static list — used on first load and when refreshModels is not yet called.
    models: [FALLBACK_MODEL],

    // Called each time pi starts. Must always return a non-empty array:
    // returning [] (truthy) overwrites the static models list above.
    refreshModels: async (context) => {
      if (!context.allowNetwork) {
        return [FALLBACK_MODEL];
      }

      // Enumerate all downloaded .gguf files so pi-web shows every model,
      // not just the one currently loaded in the server.
      const modelDir = `${homedir()}/models`;
      let ggufFiles: string[] = [];
      try {
        ggufFiles = readdirSync(modelDir)
          .filter((f: string) => f.endsWith(".gguf"))
          .sort();
      } catch {}

      if (!ggufFiles.length) return [FALLBACK_MODEL];

      // Get the active model filename and its real context window from the server.
      let activeFile = "";
      let activeCtx = DEFAULT_CTX;
      try {
        const modelsResp = await fetch(`${SERVER_BASE}/v1/models`, {
          signal: context.signal,
        });
        if (modelsResp.ok) {
          const data = await modelsResp.json();
          const first = (data.data ?? [])[0];
          if (first) {
            activeFile = (first.id ?? "").split("/").pop() ?? "";
            activeCtx = first?.meta?.n_ctx ?? DEFAULT_CTX;
            if (!activeCtx) {
              const propsResp = await fetch(`${SERVER_BASE}/props`, {
                signal: context.signal,
              });
              if (propsResp.ok) {
                const props = await propsResp.json();
                activeCtx =
                  props?.default_generation_settings?.n_ctx ?? DEFAULT_CTX;
              }
            }
          }
        }
      } catch {}

      return ggufFiles.map((f: string) => {
        const isActive = f === activeFile;
        const baseName = f.replace(/\.gguf$/i, "");
        // Mark the active model so it's identifiable in the pi-web dropdown.
        // Non-active models can be selected but require running switch_model in
        // the chat and then starting a new session to take effect.
        const name = isActive ? `▶ ${baseName}` : baseName;
        const ctx = isActive ? activeCtx : DEFAULT_CTX;
        return {
          id: `${modelDir}/${f}`,
          name,
          api: "openai-completions" as const,
          input: ["text"] as string[],
          reasoning: false,
          contextWindow: ctx,
          maxTokens: ctx,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        };
      });
    },
  });

  // ── web_search tool ────────────────────────────────────────────────────────
  // Registered as a native tool so small models call it directly instead of
  // needing to translate "run this bash command" into a bash tool invocation.
  // Total output is capped at MAX_SEARCH_CHARS to prevent context overflow.
  const MAX_SEARCH_CHARS = 6000;
  pi.registerTool({
    name: "web_search",
    label: "Web Search",
    description:
      "Search the web using DuckDuckGo. Returns titles, links, and snippets for each result. " +
      "Use for any question requiring current information, facts, documentation, or news. " +
      "Output is capped at 6000 chars; use fetch_url with page= to read full pages.",
    promptSnippet: 'web_search(query="...") — search the web with DuckDuckGo, no API key needed',
    parameters: Type.Object({
      query: Type.String({ description: "Search query" }),
      num_results: Type.Optional(
        Type.Number({ description: "Number of results to return (default 5, max 25)", default: 5 })
      ),
      include_content: Type.Optional(
        Type.Boolean({ description: "Fetch first 2000 chars of page content for each result (use fetch_url for full pages)", default: false })
      ),
      freshness: Type.Optional(
        Type.String({ description: "Time filter: pd=past day, pw=past week, pm=past month, py=past year" })
      ),
    }),
    async execute(_id, params, _signal, _onUpdate, _ctx) {
      const args: string[] = [params.query];
      if (params.num_results) args.push("-n", String(params.num_results));
      if (params.include_content) args.push("--content");
      if (params.freshness) args.push("--freshness", params.freshness);

      const result = spawnSync("node", [`${SKILL_DIR}/search.js`, ...args], {
        timeout: 30000,
        encoding: "utf8",
      });

      let text =
        result.stdout?.trim() ||
        result.stderr?.trim() ||
        "No results returned.";

      if (text.length > MAX_SEARCH_CHARS) {
        text = text.slice(0, MAX_SEARCH_CHARS) +
          `\n\n[Truncated — ${text.length} chars total. Use fetch_url with page= to read specific results in full.]`;
      }

      return {
        content: [{ type: "text" as const, text }],
        details: {},
      };
    },
  });

  // ── list_models tool ───────────────────────────────────────────────────────
  pi.registerTool({
    name: "list_models",
    label: "List Models",
    description:
      "List all GGUF models downloaded on the Jetson and show which one is currently active. " +
      "Call this before switch_model to get the exact filename to pass.",
    promptSnippet: "list_models() — show active model and all downloaded models available to switch to",
    parameters: Type.Object({}),
    async execute(_id, _params, signal, _onUpdate, _ctx) {
      let activeId = "";
      try {
        const resp = await fetch(`${SERVER_BASE}/v1/models`, { signal });
        if (resp.ok) {
          const data = await resp.json();
          activeId = (data.data?.[0]?.id ?? "").split("/").pop() ?? "";
        }
      } catch {}

      const modelDir = `${homedir()}/models`;
      let files: string[] = [];
      try {
        files = readdirSync(modelDir)
          .filter((f: string) => f.endsWith(".gguf"))
          .sort();
      } catch {}

      if (!files.length) {
        return {
          content: [{ type: "text" as const, text: "No models found in ~/models/" }],
          details: {},
        };
      }

      const lines = files.map((f: string) => {
        const active = f === activeId;
        let sizeGb = "?.? ";
        try {
          sizeGb = (statSync(`${modelDir}/${f}`).size / 1024 ** 3).toFixed(1);
        } catch {}
        return `${active ? "▶ " : "  "}${f}  (${sizeGb} GB)${active ? "  ← active" : ""}`;
      });

      const text = `Downloaded models  (▶ = currently active)\n\n${lines.join("\n")}`;
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // ── switch_model tool ──────────────────────────────────────────────────────
  pi.registerTool({
    name: "switch_model",
    label: "Switch Model",
    description:
      "Stop the current inference server and restart it with a different downloaded model. " +
      "Use list_models first to get the exact filename. " +
      "After a successful switch, tell the user to restart pi to reconnect: " +
      "type /exit then reopen pi from the terminal — their session will be restored.",
    promptSnippet:
      'switch_model(model="filename.gguf") — switch active model; always remind user to restart pi afterward',
    parameters: Type.Object({
      model: Type.String({
        description: "Exact filename from list_models output (e.g. qwen3.5-4B-super-coder.Q4_0.gguf)",
      }),
    }),
    async execute(_id, params, _signal, _onUpdate, _ctx) {
      const bin = `${homedir()}/bin/jetson-infer`;
      const result = spawnSync(bin, ["switch", params.model], {
        timeout: 120000,
        encoding: "utf8",
      });

      const raw = result.stdout?.trim() || result.stderr?.trim() || "No output.";
      const output = raw.replace(/\x1b\[[0-9;]*m/g, ""); // strip ANSI colour codes
      const success = result.status === 0;

      const text = success
        ? `${output}\n\n---\nModel switched. To reconnect pi to the new model:\n  1. Type /quit to end this session\n  2. Reopen pi from your terminal — your session will be restored.`
        : `Switch failed (exit ${result.status ?? "timeout"}):\n${output}`;

      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // ── fetch_url tool ─────────────────────────────────────────────────────────
  pi.registerTool({
    name: "fetch_url",
    label: "Fetch URL",
    description:
      "Fetch the readable text content of any URL as markdown. " +
      "Pages are split into 3000-char chunks. Call with page=1 first; " +
      "if the response shows 'Page 1/N', call again with page=2, 3, etc. to read the rest.",
    promptSnippet: "fetch_url(url=\"https://...\") — read a webpage as markdown; use page=2,3... for long pages",
    parameters: Type.Object({
      url: Type.String({ description: "The URL to fetch" }),
      page: Type.Optional(
        Type.Number({ description: "Which 3000-char page to return (default 1). Check Page N/M header for total.", default: 1 })
      ),
      page_size: Type.Optional(
        Type.Number({ description: "Chars per page (default 3000, min 500). Reduce if responses are too large.", default: 3000 })
      ),
    }),
    async execute(_id, params, _signal, _onUpdate, _ctx) {
      const args: string[] = [params.url];
      if (params.page && params.page > 1) args.push("--page", String(Math.floor(params.page)));
      if (params.page_size) args.push("--page-size", String(Math.floor(params.page_size)));

      const result = spawnSync("node", [`${SKILL_DIR}/content.js`, ...args], {
        timeout: 30000,
        encoding: "utf8",
      });

      const text =
        result.stdout?.trim() ||
        result.stderr?.trim() ||
        "Could not fetch URL.";

      return {
        content: [{ type: "text" as const, text }],
        details: {},
      };
    },
  });

  // ── list_shared_files tool ────────────────────────────────────────────────
  // Surfaces the ~/shared/ directory so the model can see what files are
  // available to work on. Users drop files directly into ~/shared/ (no
  // uploads/ or exports/ subdirectories — they can create their own if needed).
  pi.registerTool({
    name: "list_shared_files",
    label: "List Shared Files",
    description:
      `List files in the Token-Jet shared directory (${SHARED_DIR}). ` +
      "Users place files here from their Mac or Windows machine via the browser at http://<jetson-ip>:30140 or a native WebDAV mount. " +
      "Use this to discover what files are available to work on.",
    promptSnippet:
      "list_shared_files() — see what files are in ~/shared/",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _onUpdate, _ctx) {
      let entries: string[] = [];
      try { entries = readdirSync(SHARED_DIR); } catch {}
      const lines = entries.length
        ? entries.map((f: string) => {
            try {
              const st = statSync(`${SHARED_DIR}/${f}`);
              if (st.isDirectory()) return `  ${f}/`;
              const size = st.size < 1024 * 1024
                ? `${(st.size / 1024).toFixed(1)} KB`
                : `${(st.size / 1024 / 1024).toFixed(1)} MB`;
              return `  ${f}  (${size})`;
            } catch { return `  ${f}`; }
          })
        : ["  (empty)"];
      const text = [
        `Shared directory: ${SHARED_DIR}`,
        `Browser access:   http://<jetson-ip>:30140`,
        ``,
        ...lines,
      ].join("\n");

      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // ── Shared helper ──────────────────────────────────────────────────────────
  function listGgufs(): { name: string; sizeGb: string }[] {
    const modelDir = `${homedir()}/models`;
    try {
      return readdirSync(modelDir)
        .filter((f: string) => f.endsWith(".gguf"))
        .sort()
        .map((f: string) => {
          let sizeGb = "?.?";
          try { sizeGb = (statSync(`${modelDir}/${f}`).size / 1024 ** 3).toFixed(1); } catch {}
          return { name: f, sizeGb };
        });
    } catch {
      return [];
    }
  }

  // ── /models slash command ──────────────────────────────────────────────────
  pi.registerCommand("models", {
    description: "List downloaded models and show which one is active",
    handler: async (_args, ctx) => {
      let activeId = "";
      try {
        const resp = await fetch(`${SERVER_BASE}/v1/models`);
        if (resp.ok) {
          const data = await resp.json();
          activeId = (data.data?.[0]?.id ?? "").split("/").pop() ?? "";
        }
      } catch {}

      const models = listGgufs();
      if (!models.length) {
        ctx.ui.notify("No models found in ~/models/", "warning");
        return;
      }

      const lines = models.map(({ name, sizeGb }) => {
        const active = name === activeId;
        return `${active ? "▶ " : "  "}${name}  (${sizeGb} GB)`;
      });
      ctx.ui.notify(lines.join("\n"), "info");
    },
  });

  // ── /files slash command ──────────────────────────────────────────────────
  pi.registerCommand("files", {
    description: "Show files in ~/shared/",
    handler: async (_args, ctx) => {
      let entries: string[] = [];
      try { entries = readdirSync(SHARED_DIR); } catch {}
      const fileLines = entries.length
        ? entries.map((f: string) => {
            try {
              const st = statSync(`${SHARED_DIR}/${f}`);
              if (st.isDirectory()) return `  ${f}/`;
              const size = st.size < 1024 * 1024
                ? `${(st.size / 1024).toFixed(1)} KB`
                : `${(st.size / 1024 / 1024).toFixed(1)} MB`;
              return `  ${f}  (${size})`;
            } catch { return `  ${f}`; }
          })
        : ["  (empty)"];
      const lines = [
        `~/shared/  —  Browser: http://<jetson-ip>:30140`,
        ...fileLines,
      ];
      ctx.ui.notify(lines.join("\n"), "info");
    },
  });

  // ── /switch slash command ──────────────────────────────────────────────────
  pi.registerCommand("switch", {
    description: "Switch the active inference model (interactive picker or /switch <filename>)",
    getArgumentCompletions: (_prefix: string) =>
      listGgufs().map(({ name, sizeGb }) => ({
        value: name,
        label: name,
        description: `${sizeGb} GB`,
      })),
    handler: async (args, ctx) => {
      const models = listGgufs();
      if (!models.length) {
        ctx.ui.notify("No models found in ~/models/", "warning");
        return;
      }

      let chosen = args.trim();
      if (!chosen) {
        const picked = await ctx.ui.select(
          "Switch Model",
          models.map(({ name, sizeGb }) => `${name}  (${sizeGb} GB)`)
        );
        if (!picked) return;
        // Strip the size suffix to get the bare filename
        chosen = picked.replace(/\s+\([\d.]+ GB\)$/, "");
      }

      const bin = `${homedir()}/bin/jetson-infer`;
      ctx.ui.setStatus("model-switch", `Switching to ${chosen}…`);
      try {
        await execFileAsync(bin, ["switch", chosen], { timeout: 120000 });
        ctx.ui.setStatus("model-switch", undefined);
        ctx.ui.notify(
          `Switched to ${chosen}.\nType /quit then reopen pi — your session will be restored.`,
          "info"
        );
      } catch (err: any) {
        ctx.ui.setStatus("model-switch", undefined);
        ctx.ui.notify(`Switch failed: ${err.message ?? String(err)}`, "error");
      }
    },
  });
}
