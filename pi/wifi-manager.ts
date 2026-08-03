import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawnSync } from "child_process";
import { homedir } from "os";

const WIFI_SCRIPT = `${homedir()}/Token-Jet/pi/wifi-manager/wifi.py`;

function runWifi(args: string[]): any {
  const r = spawnSync("python3", [WIFI_SCRIPT, ...args], {
    timeout: 35000,
    encoding: "utf8",
  });
  const raw = r.stdout?.trim();
  if (raw) {
    try { return JSON.parse(raw); } catch {}
  }
  const errMsg = r.stderr?.trim() || `Exit ${r.status ?? "timeout"}`;
  return { error: errMsg };
}

function formatStatus(data: any): string {
  if (data.error) return `Error: ${data.error}`;
  if (!data.enabled) return `Wi-Fi: DISABLED  (device: ${data.device})`;
  const conn = data.connected_to ? `connected to "${data.connected_to}"` : data.state;
  const ip = data.ip ? `  IP: ${data.ip}` : "";
  return `Wi-Fi: ON  |  ${conn}${ip}  (device: ${data.device})`;
}

function formatNetworks(networks: any[]): string {
  if (!networks?.length) return "No networks found.";
  const lines = networks.map((n: any) => {
    const tags = [];
    if (n.connected) tags.push("connected");
    else if (n.saved) tags.push("saved");
    const security = n.security || "open";
    const tag = tags.length ? `  [${tags.join(", ")}]` : "";
    return `${n.bars}  ${n.ssid}  ${security}${tag}`;
  });
  return lines.join("\n");
}

export default function (pi: ExtensionAPI) {
  // ── wifi_status ────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "wifi_status",
    label: "Wi-Fi Status",
    description:
      "Show current Wi-Fi state: radio enabled/disabled, connected network, IP address, and device name.",
    promptSnippet: "wifi_status() — show Wi-Fi radio state and current connection",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _onUpdate, _ctx) {
      const data = runWifi(["status"]);
      return { content: [{ type: "text" as const, text: formatStatus(data) }], details: {} };
    },
  });

  // ── wifi_scan ──────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "wifi_scan",
    label: "Wi-Fi Scan",
    description:
      "Scan for nearby Wi-Fi networks. Returns each network's SSID, signal strength, security type, " +
      "and whether it is currently connected or has a saved password profile.",
    promptSnippet: "wifi_scan() — list nearby Wi-Fi networks with signal, security, and saved status",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _onUpdate, _ctx) {
      const data = runWifi(["scan"]);
      if (data.error) {
        return { content: [{ type: "text" as const, text: `Error: ${data.error}` }], details: {} };
      }
      const text = formatNetworks(data.networks);
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // ── wifi_on ────────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "wifi_on",
    label: "Enable Wi-Fi",
    description: "Turn on the Wi-Fi radio. Use this to re-enable Wi-Fi after it has been disabled.",
    promptSnippet: "wifi_on() — enable the Wi-Fi radio",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _onUpdate, _ctx) {
      const data = runWifi(["on"]);
      const text = data.error ? `Failed to enable Wi-Fi: ${data.error}` : "Wi-Fi enabled.";
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // ── wifi_off ───────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "wifi_off",
    label: "Disable Wi-Fi",
    description:
      "Turn off the Wi-Fi radio entirely. Use for air-gapped / USB-only operation. " +
      "The Jetson remains reachable via USB (192.168.55.1).",
    promptSnippet: "wifi_off() — disable Wi-Fi radio for air-gapped USB-only mode",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _onUpdate, _ctx) {
      const data = runWifi(["off"]);
      const text = data.error ? `Failed to disable Wi-Fi: ${data.error}` : "Wi-Fi disabled.";
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // ── wifi_connect ───────────────────────────────────────────────────────────
  pi.registerTool({
    name: "wifi_connect",
    label: "Wi-Fi Connect",
    description:
      "Connect to a Wi-Fi network by SSID. If the network has a saved password profile, " +
      "no passphrase is needed. For a new password-protected network, provide the passphrase. " +
      "Supports WPA, WPA2, WPA3, and open networks.",
    promptSnippet:
      'wifi_connect(ssid="MyNetwork") or wifi_connect(ssid="MyNetwork", password="passphrase")',
    parameters: Type.Object({
      ssid: Type.String({ description: "Network name (SSID) to connect to" }),
      password: Type.Optional(
        Type.String({ description: "WPA/WPA2/WPA3 passphrase (omit if saved or open network)" })
      ),
    }),
    async execute(_id, params, _signal, _onUpdate, _ctx) {
      const args = ["connect", params.ssid];
      if (params.password) args.push("--password", params.password);
      const data = runWifi(args);
      const text = data.error
        ? `Connection failed: ${data.error}`
        : data.success
          ? `Connected to "${params.ssid}".`
          : `Unexpected response: ${JSON.stringify(data)}`;
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // ── wifi_disconnect ────────────────────────────────────────────────────────
  pi.registerTool({
    name: "wifi_disconnect",
    label: "Wi-Fi Disconnect",
    description: "Disconnect from the current Wi-Fi network without disabling the radio.",
    promptSnippet: "wifi_disconnect() — disconnect from the current Wi-Fi network",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _onUpdate, _ctx) {
      const data = runWifi(["disconnect"]);
      const text = data.error
        ? `Disconnect failed: ${data.error}`
        : data.success
          ? "Disconnected from Wi-Fi."
          : `Unexpected response: ${JSON.stringify(data)}`;
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // ── wifi_forget ────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "wifi_forget",
    label: "Forget Wi-Fi Network",
    description:
      "Delete the saved password profile for a Wi-Fi network so it is no longer auto-reconnected.",
    promptSnippet: 'wifi_forget(ssid="MyNetwork") — delete saved credentials for a network',
    parameters: Type.Object({
      ssid: Type.String({ description: "Network name (SSID) whose profile to delete" }),
    }),
    async execute(_id, params, _signal, _onUpdate, _ctx) {
      const data = runWifi(["forget", params.ssid]);
      const text = data.error
        ? `Failed to forget "${params.ssid}": ${data.error}`
        : data.success
          ? `Saved profile for "${params.ssid}" deleted.`
          : `Unexpected response: ${JSON.stringify(data)}`;
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // ── /secure-jet slash command ──────────────────────────────────────────────
  // Air-gaps the Jetson: turns off the WiFi radio AND deletes all saved WiFi
  // profiles so it cannot auto-reconnect on reboot. The only remaining path
  // in is USB-C Ethernet (192.168.55.1). Restoring WiFi requires connecting
  // via USB and running /wifi or asking the model to reconnect.
  pi.registerCommand("secure-jet", {
    description: "Air-gap Token-Jet: disable WiFi radio and wipe all saved WiFi profiles",
    handler: async (_args, ctx) => {
      const status = runWifi(["status"]);
      const ipLine = status.ip
        ? `  Current WiFi IP: ${status.ip}`
        : "  (WiFi not currently connected)";

      ctx.ui.notify(
        [
          "⚠  SECURE-JET — what will happen:",
          "",
          "  1. WiFi radio will be turned OFF",
          "  2. All saved WiFi profiles will be DELETED",
          "",
          ipLine,
          "",
          "  After this, the only access to Token-Jet is via USB-C:",
          "    ssh jetuser@192.168.55.1",
          "",
          "  To restore WiFi later: connect via USB, then run /wifi",
          "  or ask the model to reconnect to a network.",
        ].join("\n"),
        "warning"
      );

      const choice = await ctx.ui.select(
        "Confirm: air-gap Token-Jet?",
        ["Yes — disable WiFi permanently", "No — cancel"]
      );
      if (!choice || choice.startsWith("No")) {
        ctx.ui.notify("Cancelled — WiFi unchanged.", "info");
        return;
      }

      ctx.ui.setStatus("secure-jet", "Disabling WiFi radio…");
      const off = runWifi(["off"]);
      if (off.error) {
        ctx.ui.setStatus("secure-jet", undefined);
        ctx.ui.notify(`Failed to disable WiFi radio: ${off.error}`, "error");
        return;
      }

      ctx.ui.setStatus("secure-jet", "Deleting saved WiFi profiles…");
      const forget = runWifi(["forget-all"]);
      ctx.ui.setStatus("secure-jet", undefined);

      if (forget.error) {
        ctx.ui.notify(
          `WiFi radio is OFF, but profile deletion failed: ${forget.error}\n` +
          `Profiles may still cause auto-reconnect on reboot. Run /wifi to delete manually.`,
          "warning"
        );
        return;
      }

      const count: number = forget.count ?? 0;
      ctx.ui.notify(
        [
          "✓  Token-Jet is now air-gapped.",
          "",
          `  WiFi radio: OFF`,
          `  Profiles deleted: ${count}`,
          "",
          "  Connect via USB-C:",
          "    ssh jetuser@192.168.55.1",
          "",
          "  To re-enable WiFi: connect via USB → /wifi",
        ].join("\n"),
        "info"
      );
    },
  });

  // ── /wifi slash command ────────────────────────────────────────────────────
  pi.registerCommand("wifi", {
    description: "Manage Wi-Fi: scan networks, connect, disconnect, or toggle the radio",
    handler: async (_args, ctx) => {
      // Check radio state first
      const status = runWifi(["status"]);
      if (status.error) {
        ctx.ui.notify(`Wi-Fi error: ${status.error}`, "error");
        return;
      }

      if (!status.enabled) {
        const action = await ctx.ui.select("Wi-Fi is OFF", ["Turn Wi-Fi ON", "Cancel"]);
        if (action === "Turn Wi-Fi ON") {
          const r = runWifi(["on"]);
          ctx.ui.notify(r.error ? `Failed: ${r.error}` : "Wi-Fi enabled.", r.error ? "error" : "info");
        }
        return;
      }

      // Wi-Fi is on — scan
      ctx.ui.setStatus("wifi-scan", "Scanning for networks…");
      const scanData = runWifi(["scan"]);
      ctx.ui.setStatus("wifi-scan", undefined);

      if (scanData.error) {
        ctx.ui.notify(`Scan failed: ${scanData.error}`, "error");
        return;
      }

      const networks: any[] = scanData.networks ?? [];
      if (!networks.length) {
        ctx.ui.notify("No networks found.", "warning");
        return;
      }

      const connected = networks.find((n: any) => n.connected);

      // Build picker options
      const netOptions = networks.map((n: any) => {
        const tags = [];
        if (n.connected) tags.push("connected");
        else if (n.saved) tags.push("saved");
        const security = n.security || "open";
        const tag = tags.length ? `  [${tags.join(", ")}]` : "";
        return `${n.bars}  ${n.ssid}  ${security}${tag}`;
      });

      const menuOptions = [
        ...(connected ? ["Disconnect from current network"] : []),
        "Disable Wi-Fi radio",
        ...netOptions,
      ];

      const picked = await ctx.ui.select("Wi-Fi Manager", menuOptions);
      if (!picked) return;

      if (picked === "Disable Wi-Fi radio") {
        const r = runWifi(["off"]);
        ctx.ui.notify(r.error ? `Failed: ${r.error}` : "Wi-Fi disabled.", r.error ? "error" : "info");
        return;
      }

      if (picked === "Disconnect from current network") {
        const r = runWifi(["disconnect"]);
        ctx.ui.notify(
          r.error ? `Disconnect failed: ${r.error}` : "Disconnected.",
          r.error ? "error" : "info"
        );
        return;
      }

      // Find the network that was selected
      const netIdx = netOptions.indexOf(picked);
      const network = networks[netIdx];
      if (!network) return;

      if (network.connected) {
        ctx.ui.notify(`Already connected to "${network.ssid}".`, "info");
        return;
      }

      if (!network.security || network.saved) {
        // Open or saved — connect directly
        ctx.ui.setStatus("wifi-connect", `Connecting to ${network.ssid}…`);
        const r = runWifi(["connect", network.ssid]);
        ctx.ui.setStatus("wifi-connect", undefined);
        ctx.ui.notify(
          r.error ? `Connection failed: ${r.error}` : `Connected to "${network.ssid}".`,
          r.error ? "error" : "info"
        );
        return;
      }

      // Password required — instruct user to use the model
      ctx.ui.notify(
        `"${network.ssid}" requires a ${network.security} password.\n` +
        `Tell the model: connect to ${network.ssid} with password <your-passphrase>`,
        "info"
      );
    },
  });
}
