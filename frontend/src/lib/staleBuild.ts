// A tab opened before a deploy still asks for the previous build's page files,
// and those are gone once the new build is live. Each screen loads on first
// visit (see App.tsx), so the next screen opened in that tab fails to load —
// which, unhandled, left a blank white page. Reloading once fetches the new
// build; the guard stops a genuinely broken build from reloading forever.

const KEY = "campushub:reloaded-for-new-build";

export function isStaleBuildError(error: unknown): boolean {
  const message = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /dynamically imported module|Importing a module script failed|ChunkLoadError|Unable to preload CSS/i
    .test(message);
}

/** Reload to pick up the new build, unless this tab already did in the last minute. */
export function reloadForNewBuild(): boolean {
  try {
    const last = Number(sessionStorage.getItem(KEY) ?? 0);
    if (Date.now() - last < 60_000) return false;
    sessionStorage.setItem(KEY, String(Date.now()));
  } catch {
    // Storage blocked: reload anyway — the browser's own cache stops a loop
    // from being more than one extra load.
  }
  window.location.reload();
  return true;
}
