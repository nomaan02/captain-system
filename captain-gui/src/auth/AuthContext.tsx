import { createContext, useContext, useState, type ReactNode } from "react";

export type UserRole = "ADMIN" | "RISK" | "TRADER" | "VIEWER";

export interface User {
  user_id: string;
  display_name: string;
  role: UserRole;
}

interface AuthContextValue {
  user: User;
  setUser: (u: User) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const DEFAULT_USER: User = {
  user_id: "primary_user",
  display_name: "Nomaan",
  role: "ADMIN",
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User>(DEFAULT_USER);
  return (
    <AuthContext.Provider value={{ user, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
