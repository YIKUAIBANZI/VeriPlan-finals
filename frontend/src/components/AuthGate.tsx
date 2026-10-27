import { useEffect, useState } from "react";
import { AuthError, UNAUTHORIZED_EVENT, authApi as defaultAuthApi, type AuthApi } from "../api";
import type { User } from "../types";
import { App } from "../App";
import { AuthPage } from "./AuthPage";

type State =
  | { kind: "loading" }
  | { kind: "offline"; message: string }
  | { kind: "anonymous"; requiresInvite: boolean }
  | { kind: "signed-in"; user: User };

export function AuthGate({ authApi = defaultAuthApi }: { authApi?: AuthApi }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    const requiresInvite = () =>
      authApi.health().then(h => Boolean(h.registration_requires_invite), () => false);
    authApi.me()
      .then(user => { if (alive) setState({ kind: "signed-in", user }); })
      .catch(async err => {
        if (!alive) return;
        if (err instanceof AuthError && err.status === 401) {
          const invite = await requiresInvite();
          if (alive) setState({ kind: "anonymous", requiresInvite: invite });
        } else {
          setState({ kind: "offline", message: (err as Error).message });
        }
      });
    return () => { alive = false; };
  }, [authApi, attempt]);

  // Any protected call that comes back 401 (session expired, logged out elsewhere).
  useEffect(() => {
    const expire = () => { setState({ kind: "loading" }); setAttempt(a => a + 1); };
    window.addEventListener(UNAUTHORIZED_EVENT, expire);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, expire);
  }, []);

  if (state.kind === "loading") return <div className="auth-loading" role="status">正在确认登录状态…</div>;
  if (state.kind === "offline")
    return (
      <div className="auth-loading" role="alert">
        <p>{state.message}</p>
        <button onClick={() => { setState({ kind: "loading" }); setAttempt(a => a + 1); }}>重试</button>
      </div>
    );
  if (state.kind === "anonymous")
    return <AuthPage api={authApi} requiresInvite={state.requiresInvite} onAuthed={user => setState({ kind: "signed-in", user })} />;
  return (
    <App
      key={state.user.id}
      user={state.user}
      onLogout={async () => {
        await authApi.logout().catch(() => undefined);
        setState({ kind: "loading" });
        setAttempt(a => a + 1);
      }}
    />
  );
}
