import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { AUTH_LOST } from "../api/client";
import { auth } from "../api/learner";
import type { Lang, Me } from "../api/types";
import i18n, { remember } from "../i18n";

interface AuthValue {
  me: Me | null;
  ready: boolean;
  signedIn: (me: Me) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  setLanguage: (lang: Lang) => void;
}

const Ctx = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const adopt = useCallback((user: Me | null) => {
    setMe(user);
    if (user && user.preferred_language !== i18n.language) {
      void i18n.changeLanguage(user.preferred_language);
      remember(user.preferred_language);
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      adopt(await auth.me());
    } catch {
      setMe(null);
    } finally {
      setReady(true);
    }
  }, [adopt]);

  useEffect(() => {
    void refresh();
    const lost = () => setMe(null); // session expired: the guards send the user to login
    window.addEventListener(AUTH_LOST, lost);
    return () => window.removeEventListener(AUTH_LOST, lost);
  }, [refresh]);

  const value = useMemo<AuthValue>(
    () => ({
      me,
      ready,
      refresh,
      signedIn: adopt,
      logout: async () => {
        await auth.logout().catch(() => undefined);
        setMe(null);
      },
      setLanguage: (lang) => {
        void i18n.changeLanguage(lang);
        remember(lang);
        if (me) {
          setMe({ ...me, preferred_language: lang });
          void auth.setLanguage(lang).catch(() => undefined);
        }
      },
    }),
    [me, ready, refresh, adopt],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(Ctx);
  if (!value) throw new Error("useAuth outside AuthProvider");
  return value;
}
