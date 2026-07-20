import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const SERVER_BASE = "http://127.0.0.1:1234";
const DEFAULT_CTX = 16384;

// Returned when the server is unreachable or when pi requests a sync-only
// refresh (allowNetwork: false). Must NOT be an empty array — pi evaluates
// the return value with `arr ? use_it : keep_static`, and [] is truthy, so
// returning [] wipes the static models list from the registration config.
const FALLBACK_MODEL = {
  id: "local",
  name: "Jetson Local Model",
  api: "openai" as const,
  reasoning: false,
  contextWindow: DEFAULT_CTX,
  maxTokens: DEFAULT_CTX,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
};

export default function (pi: ExtensionAPI) {
  pi.registerProvider("jetson-local", {
    name: "Jetson (llama.cpp)",
    baseUrl: `${SERVER_BASE}/v1`,
    api: "openai",
    // Auth credential is also written to ~/.pi/agent/auth.json by the
    // install script. apiKey here is a belt-and-suspenders backup.
    apiKey: "none",

    // Static list — used on first load and when refreshModels is not yet called.
    models: [FALLBACK_MODEL],

    // Called each time pi starts. Must always return a non-empty array:
    // returning [] (truthy) overwrites the static models list above.
    refreshModels: async (context) => {
      if (!context.allowNetwork) {
        // Sync-only pass — no network calls allowed. Return the fallback so
        // the static list is not wiped before the real refresh runs.
        return [FALLBACK_MODEL];
      }
      try {
        // /v1/models: primary source for model ID and context window.
        // Newer llama-server versions expose meta.n_ctx here directly.
        const modelsResp = await fetch(`${SERVER_BASE}/v1/models`, {
          signal: context.signal,
        });
        if (!modelsResp.ok) return [FALLBACK_MODEL];
        const modelsData = await modelsResp.json();
        const first = (modelsData.data ?? [])[0];
        if (!first) return [FALLBACK_MODEL];

        const modelId: string = first.id ?? "local";
        const modelName: string =
          modelId.split("/").pop()?.replace(/\.gguf$/i, "") ?? modelId;

        // Prefer meta.n_ctx from /v1/models (official pi-llama-cpp approach).
        // Fall back to /props for older llama-server builds.
        let n_ctx: number = first?.meta?.n_ctx ?? 0;
        if (!n_ctx) {
          const propsResp = await fetch(`${SERVER_BASE}/props`, {
            signal: context.signal,
          });
          if (propsResp.ok) {
            const props = await propsResp.json();
            n_ctx = props?.default_generation_settings?.n_ctx ?? DEFAULT_CTX;
          } else {
            n_ctx = DEFAULT_CTX;
          }
        }

        return [
          {
            id: modelId,
            name: modelName,
            api: "openai",
            reasoning: false,
            contextWindow: n_ctx,
            maxTokens: n_ctx,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          },
        ];
      } catch {
        // Server not running — keep a usable model entry so pi doesn't
        // show "No models available". Requests will fail at send time.
        return [FALLBACK_MODEL];
      }
    },
  });
}
