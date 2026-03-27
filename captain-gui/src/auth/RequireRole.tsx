import type { ReactNode } from "react";
import { useAuth, type UserRole } from "./AuthContext";

interface Props {
  allowed: UserRole[];
  children: ReactNode;
  fallback?: ReactNode;
}

export function RequireRole({ allowed, children, fallback }: Props) {
  const { user } = useAuth();
  if (!allowed.includes(user.role)) {
    return <>{fallback ?? null}</>;
  }
  return <>{children}</>;
}
