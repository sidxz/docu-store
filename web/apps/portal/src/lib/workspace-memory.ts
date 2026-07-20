// Remembered workspace so interactive logins skip the picker.
// Survives logout on purpose (the SDK's sentinel_workspace_id does not) —
// "Switch workspace" in the topbar user menu clears it to bring the picker back.
const KEY = "ds-last-workspace-id";

export function rememberedWorkspace(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function rememberWorkspace(id: string): void {
  try {
    localStorage.setItem(KEY, id);
  } catch {
    // storage unavailable (private mode) — picker just shows every time
  }
}

export function forgetWorkspace(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
