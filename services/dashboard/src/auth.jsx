// Auth context: JWT in localStorage, role-aware. Token claims decode the email/role.
import React, { createContext, useContext, useState, useCallback } from "react";
import { api, getToken, setToken } from "./api.js";

const AuthCtx = createContext(null);

function parseJwt(token) {
  try {
    return JSON.parse(atob(token.split(".")[1]));
  } catch {
    return null;
  }
}

function fromToken(token) {
  const claims = token ? parseJwt(token) : null;
  if (!claims) return null;
  // expiry check
  if (claims.exp && claims.exp * 1000 < Date.now()) return null;
  return { token, email: claims.email, role: claims.role };
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => fromToken(getToken()));

  const apply = (r) => {
    setToken(r.token);
    setAuth({ token: r.token, email: r.email, role: r.role });
    return r;
  };
  const login = useCallback((email, password) => api.login(email, password).then(apply), []);
  const register = useCallback((email, password, role) => api.register(email, password, role).then(apply), []);
  const logout = useCallback(() => { setToken(null); setAuth(null); }, []);

  return <AuthCtx.Provider value={{ auth, login, register, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
