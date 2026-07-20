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
        reasoning: false,
        contextWindow: DEFAULT_CTX,
        maxTokens: 8192,
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
        // /props returns the server's actual runtime configuration,
        // including the n_ctx that llama-server was started with.
        const propsResp = await fetch(`${SERVER_BASE}/props`, {
          signal: context.signal,
        });
        if (!propsResp.ok) return [];
        const props = await propsResp.json();
        const n_ctx: number =
          props?.default_generation_settings?.n_ctx ?? DEFAULT_CTX;

        // /v1/models gives us the loaded model's ID (typically the filename).
        const modelsResp = await fetch(`${SERVER_BASE}/v1/models`, {
          signal: context.signal,
        });
        let modelId = "local";
        let modelName = "Jetson Local Model";
        if (modelsResp.ok) {
          const modelsData = await modelsResp.json();
          const first = (modelsData.data ?? [])[0];
          if (first?.id) {
            modelId = first.id;
            // Strip path and .gguf for a readable display name.
            modelName =
              modelId.split("/").pop()?.replace(/\.gguf$/i, "") ?? modelId;
          }
        }

        return [
          {
            id: modelId,
            name: modelName,
            api: "openai-completions",
            reasoning: false,
            contextWindow: n_ctx,
            maxTokens: Math.min(n_ctx, 8192),
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
