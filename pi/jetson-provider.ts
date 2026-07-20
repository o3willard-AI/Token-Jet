import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const SERVER_BASE = "http://127.0.0.1:1234";
const DEFAULT_CTX = 16384;

export default function (pi: ExtensionAPI) {
  pi.registerProvider("jetson-local", {
    name: "Jetson (llama.cpp)",
    baseUrl: `${SERVER_BASE}/v1`,
    api: "openai-completions",

    // Static fallback used when the inference server isn't running yet.
    // refreshModels() below replaces this at runtime with live values.
    models: [
      {
        id: "local",
        name: "Jetson Local Model",
        api: "openai-completions",
        reasoning: true,
        contextWindow: DEFAULT_CTX,
        maxTokens: DEFAULT_CTX,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      },
    ],

    // Called each time pi starts (when allowNetwork is true).
    // Queries the running llama-server for the actual loaded model name
    // and the context window that jetson-infer calculated at startup
    // (which varies by model and available RAM).
    refreshModels: async (context) => {
      if (!context.allowNetwork) return [];
      try {
        // /v1/models: primary source for model ID and context window.
        // Newer llama-server versions expose meta.n_ctx here directly.
        const modelsResp = await fetch(`${SERVER_BASE}/v1/models`, {
          signal: context.signal,
        });
        if (!modelsResp.ok) return [];
        const modelsData = await modelsResp.json();
        const first = (modelsData.data ?? [])[0];
        if (!first) return [];

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
            api: "openai-completions",
            reasoning: true,
            contextWindow: n_ctx,
            maxTokens: n_ctx,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          },
        ];
      } catch {
        // Server not running — pi falls back to the static models array above.
        return [];
      }
    },
  });
}
