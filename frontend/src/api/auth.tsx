/** 全局认证上下文 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { flushSync } from "react-dom";
import { authApi, type User } from "../api/client";

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (student_id: string, password: string, role: string) => Promise<User>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

function readStoredUser(): User | null {
  const stored = localStorage.getItem("user");
  if (!stored) return null;
  try {
    return JSON.parse(stored) as User;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => readStoredUser());
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);
  const tokenRef = useRef(token);

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  useEffect(() => {
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    let cancelled = false;

    /** blockUI：仅首次校验 token 时阻塞界面；后台同步（如窗口重新聚焦）不打断当前页面 */
    const syncUser = (blockUI: boolean) => {
      if (blockUI) setLoading(true);
      authApi
        .me()
        .then((r) => {
          if (cancelled || tokenRef.current !== localStorage.getItem("token")) return;
          setUser(r.data);
          localStorage.setItem("user", JSON.stringify(r.data));
        })
        .catch(() => {
          if (cancelled || tokenRef.current !== localStorage.getItem("token")) return;
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          setUser(null);
          setToken(null);
        })
        .finally(() => {
          if (!cancelled && blockUI) setLoading(false);
        });
    };

    syncUser(true);

    const onStorage = (event: StorageEvent) => {
      if (event.key !== "token" && event.key !== "user") return;
      const nextToken = localStorage.getItem("token");
      setToken(nextToken);
      tokenRef.current = nextToken;
      if (!nextToken) {
        setUser(null);
        setLoading(false);
        return;
      }
      syncUser(false);
    };

    const onFocus = () => {
      const storedToken = localStorage.getItem("token");
      if (storedToken !== tokenRef.current) {
        setToken(storedToken);
        tokenRef.current = storedToken;
      }
      if (storedToken) syncUser(false);
    };

    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", onFocus);
    };
  }, [token]);

  const login = useCallback(async (student_id: string, password: string, role: string) => {
    const r = await authApi.login({ student_id, password, role });
    localStorage.setItem("token", r.data.access_token);
    localStorage.setItem("user", JSON.stringify(r.data.user));
    flushSync(() => {
      setToken(r.data.access_token);
      setUser(r.data.user);
    });
    return r.data.user;
  }, []);

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
