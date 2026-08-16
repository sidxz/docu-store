import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface AppConfig {
  duar_url: string;
  api_url: string;
  google_client_id: string;
  google_client_secret: string;
}

const DEFAULTS: AppConfig = {
  duar_url: "http://localhost:9003",
  api_url: "http://localhost:8000",
  google_client_id: "",
  google_client_secret: "",
};

function configDir(): string {
  const xdg = process.env.XDG_CONFIG_HOME;
  return join(xdg || join(homedir(), ".config"), "docu-store");
}

function configPath(): string {
  return join(configDir(), "config.json");
}

export function loadConfig(): AppConfig {
  const path = configPath();
  let file: Partial<AppConfig> = {};
  if (existsSync(path)) {
    try {
      file = JSON.parse(readFileSync(path, "utf-8"));
    } catch {
      // ignore corrupt config
    }
  }

  return {
    duar_url:
      process.env.DOCU_DUAR_URL ||
      file.duar_url ||
      // ponytail: legacy key from configs written before the Sentinel → Duar rename
      (file as { sentinel_url?: string }).sentinel_url ||
      DEFAULTS.duar_url,
    api_url:
      process.env.DOCU_API_URL || file.api_url || DEFAULTS.api_url,
    google_client_id:
      process.env.DOCU_GOOGLE_CLIENT_ID || file.google_client_id || DEFAULTS.google_client_id,
    google_client_secret:
      process.env.DOCU_GOOGLE_CLIENT_SECRET || file.google_client_secret || DEFAULTS.google_client_secret,
  };
}

export function saveConfig(partial: Partial<AppConfig>): void {
  const dir = configDir();
  mkdirSync(dir, { recursive: true });
  const path = configPath();

  let existing: Partial<AppConfig> = {};
  if (existsSync(path)) {
    try {
      existing = JSON.parse(readFileSync(path, "utf-8"));
    } catch {
      // overwrite corrupt file
    }
  }

  const merged = { ...existing, ...partial };
  writeFileSync(path, JSON.stringify(merged, null, 2) + "\n", "utf-8");
}

export function showConfig(): Record<string, string> {
  const config = loadConfig();
  return {
    duar_url: config.duar_url,
    api_url: config.api_url,
    google_client_id: config.google_client_id || "(not set)",
    google_client_secret: config.google_client_secret ? "(set)" : "(not set)",
    config_file: configPath(),
  };
}
