import { useState } from "react";
import type { AuthApi } from "../api";
import type { User } from "../types";

const discipline = [
  ["对齐条件", "先确认预算、期限和目标，再动手"],
  ["联网取证", "多个维度检索，每条结论标出来源"],
  ["事前验尸", "假设已经失败，倒推最可能的原因"],
  ["反方自审", "专门挑刺的委员审一遍全部论证"],
  ["代码算数", "数字由程序计算，不让模型心算"],
  ["你来签字", "采纳、修改还是暂缓，由你决定"],
  ["事后校准", "回填真实结果，看清自己的偏差"],
] as const;

const USERNAME = /^[0-9A-Za-z_.\-一-鿿]{3,32}$/;

export function AuthPage({
  api,
  requiresInvite,
  onAuthed,
}: {
  api: AuthApi;
  requiresInvite: boolean;
  onAuthed: (user: User) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [invite, setInvite] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const registering = mode === "register";

  function switchTo(next: typeof mode) {
    setMode(next);
    setError("");
    setConfirm("");
  }

  function localError() {
    if (!registering) return "";
    if (!USERNAME.test(username.trim())) return "用户名需 3–32 位，可用中英文、数字、下划线、点和短横线。";
    if (password.length < 8) return "密码至少 8 位。";
    if (password !== confirm) return "两次输入的密码不一致。";
    if (requiresInvite && !invite.trim()) return "请填写邀请码。";
    return "";
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    const problem = localError();
    if (problem) { setError(problem); return; }
    setBusy(true);
    setError("");
    try {
      const user = registering
        ? await api.register(username.trim(), password, requiresInvite ? invite.trim() : undefined)
        : await api.login(username.trim(), password);
      onAuthed(user);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-intro">
        <div className="brand"><div><strong>证策</strong><span>VeriPlan</span></div></div>
        <h1 className="display">一人公司的<br />决策委员会</h1>
        <p className="lede">它不替你拍板。它让每个决定都走完同一套纪律，并把过程记下来。</p>
        <ol className="discipline">
          {discipline.map(([title, body], index) => (
            <li key={title}>
              <span className="discipline-no">{String(index + 1).padStart(2, "0")}</span>
              <div><strong>{title}</strong><small>{body}</small></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="brand auth-card-brand"><div><strong>证策</strong><span>VeriPlan</span></div></div>
          <div className="auth-tabs" role="tablist" aria-label="登录或注册">
            <button role="tab" type="button" aria-selected={!registering} onClick={() => switchTo("login")}>登录</button>
            <button role="tab" type="button" aria-selected={registering} onClick={() => switchTo("register")}>注册</button>
          </div>
          <h2>{registering ? "创建账号" : "欢迎回来"}</h2>
          <p className="auth-sub">{registering ? "你的决策账本只有你自己能看到。" : "登录后继续你的决策账本。"}</p>
          <form onSubmit={submit} noValidate>
            <label>
              <span>用户名</span>
              <input
                aria-label="用户名"
                autoComplete="username"
                autoFocus
                required
                maxLength={32}
                value={username}
                onChange={e => setUsername(e.target.value)}
              />
            </label>
            <label>
              <span>密码</span>
              <input
                aria-label="密码"
                type="password"
                autoComplete={registering ? "new-password" : "current-password"}
                required
                maxLength={128}
                placeholder={registering ? "至少 8 位" : undefined}
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
            </label>
            {registering && (
              <label>
                <span>确认密码</span>
                <input
                  aria-label="确认密码"
                  type="password"
                  autoComplete="new-password"
                  required
                  maxLength={128}
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                />
              </label>
            )}
            {registering && requiresInvite && (
              <label>
                <span>邀请码</span>
                <input
                  aria-label="邀请码"
                  autoComplete="off"
                  required
                  value={invite}
                  onChange={e => setInvite(e.target.value)}
                />
              </label>
            )}
            {error && <p className="auth-error" role="alert">{error}</p>}
            <button className="primary" type="submit" disabled={busy || !username.trim() || !password}>
              {busy ? "请稍候…" : registering ? "注册并进入" : "登录"}
            </button>
          </form>
          <p className="auth-switch">
            {registering ? "已有账号？" : "还没有账号？"}
            <button type="button" className="link-button" onClick={() => switchTo(registering ? "login" : "register")}>
              {registering ? "去登录" : "注册一个"}
            </button>
          </p>
        </div>
      </section>
    </div>
  );
}
