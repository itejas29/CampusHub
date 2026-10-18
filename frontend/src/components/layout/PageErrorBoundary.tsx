import { AlertTriangle, Home, RotateCw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { isStaleBuildError, reloadForNewBuild } from "@/lib/staleBuild";

// A screen that throws while rendering takes only itself down: the sidebar and
// top bar stay, and the person gets a way out instead of a blank white page.
// AppShell keys this on the path, so moving to another screen clears it.
export class PageErrorBoundary extends Component<
  { children: ReactNode; fullPage?: boolean },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (isStaleBuildError(error) && reloadForNewBuild()) return;
    console.error("Screen failed to render", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const stale = isStaleBuildError(error);
    return (
      <div className={this.props.fullPage ? "grid min-h-screen place-items-center bg-canvas p-4" : "py-16"}>
        <div role="alert" className="mx-auto max-w-md rounded-lg border border-line bg-surface p-6 text-center shadow-sm">
          <AlertTriangle className="mx-auto h-8 w-8 text-warning" aria-hidden />
          <h1 className="mt-3 text-md font-semibold text-ink">This page couldn't load</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {stale
              ? "CampusHub was updated while this tab was open. Reload to get the new version."
              : "Something went wrong showing this page. Reloading usually fixes it; if it keeps happening, tell the portal team what you clicked."}
          </p>
          <div className="mt-5 flex justify-center gap-2">
            <Button size="sm" icon={<RotateCw className="h-3.5 w-3.5" aria-hidden />}
                    onClick={() => window.location.reload()}>
              Reload
            </Button>
            <Button size="sm" variant="secondary" icon={<Home className="h-3.5 w-3.5" aria-hidden />}
                    onClick={() => window.location.assign("/")}>
              Dashboard
            </Button>
          </div>
        </div>
      </div>
    );
  }
}
