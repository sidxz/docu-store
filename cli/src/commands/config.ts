import { saveConfig, showConfig, type AppConfig } from "../utils/config.js";
import * as log from "../utils/logger.js";

const VALID_KEYS: (keyof AppConfig)[] = ["duar_url", "api_url", "google_client_id", "google_client_secret"];

export function configSetCommand(key: string, value: string): void {
  // Accept both dash and underscore forms
  const normalizedKey = key.replace(/-/g, "_") as keyof AppConfig;

  if (!VALID_KEYS.includes(normalizedKey)) {
    log.error(`Unknown config key: "${key}". Valid keys: ${VALID_KEYS.join(", ")}`);
    process.exit(1);
  }

  saveConfig({ [normalizedKey]: value });
  log.success(`${normalizedKey} = ${value}`);
}

export function configShowCommand(): void {
  const config = showConfig();
  for (const [key, value] of Object.entries(config)) {
    console.log(`  ${key}: ${value}`);
  }
}
