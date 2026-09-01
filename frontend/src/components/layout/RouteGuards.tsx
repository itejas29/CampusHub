import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState, LoadingState } from "@/components/ui/States";
import { useAuth } from "@/lib/auth";
import type { CoordinationDomain, Role } from "@/types";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <div className="w-full max-w-sm">
          <LoadingState label="Restoring your session…" rows={2} />
        </div>
      </div>
    );
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

/**
 * Client-side gate. The backend enforces the same rules independently — this
 * only avoids showing a page that would fail anyway.
 */
export function RequireAccess({
  children, roles, permission, coordinates,
}: {
  children: ReactNode; roles?: Role[]; permission?: string;
  /** Alternative to `permission`: any of these scoped coordinations admits. */
  coordinates?: CoordinationDomain[];
}) {
  const { can, hasRole, coordinates: holdsCoordination } = useAuth();

  const byPermission = permission ? can(permission) : null;
  const byCoordination = coordinates
    ? coordinates.some(holdsCoordination)
    : null;
  const capabilityOk =
    byPermission === null && byCoordination === null
      ? true
      : Boolean(byPermission) || Boolean(byCoordination);

  const allowed = capabilityOk && (!roles || hasRole(...roles));

  if (!allowed) {
    return (
      <Card>
        <EmptyState
          title="You don't have access to this page"
          description="Your role does not include the permission this section requires. If you believe this is a mistake, contact the department administrator."
          action={
            <Button variant="secondary" size="sm" onClick={() => window.history.back()}>
              Go back
            </Button>
          }
        />
      </Card>
    );
  }
  return <>{children}</>;
}

export function NotFoundPage() {
  return (
    <Card>
      <EmptyState
        title="Page not found"
        description="The page you were looking for doesn't exist or has moved."
        action={
          <Button variant="secondary" size="sm" onClick={() => window.history.back()}>
            Go back
          </Button>
        }
      />
    </Card>
  );
}
