import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthError, UNAUTHORIZED_EVENT, api, authApi, type AuthApi } from "../api";
import { AuthPage } from "./AuthPage";
import { AuthGate } from "./AuthGate";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const user = { id: 1, username: "banz", created_at: "2026-10-27T00:00:00Z" };
function fakeAuth(overrides: Partial<AuthApi> = {}): AuthApi {
  return {
    me: vi.fn().mockRejectedValue(new AuthError(401, "未登录")),
    login: vi.fn().mockResolvedValue(user),
    register: vi.fn().mockResolvedValue(user),
    logout: vi.fn().mockResolvedValue(undefined),
    health: vi.fn().mockResolvedValue({ mode: "demo", database: "ok", live_available: false }),
    ...overrides,
  };
}
const fill = (label: string, value: string) =>
  fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } });

describe("AuthPage", () => {
  it("logs in with trimmed username", async () => {
    const auth = fakeAuth();
    const onAuthed = vi.fn();
    render(<AuthPage api={auth} requiresInvite={false} onAuthed={onAuthed} />);
    fill("用户名", "  banz ");
    fill("密码", "secret-pass");
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(() => expect(onAuthed).toHaveBeenCalledWith(user));
    expect(auth.login).toHaveBeenCalledWith("banz", "secret-pass");
  });

  it("shows the server message when login fails", async () => {
    const auth = fakeAuth({ login: vi.fn().mockRejectedValue(new AuthError(401, "用户名或密码不正确。")) });
    render(<AuthPage api={auth} requiresInvite={false} onAuthed={vi.fn()} />);
    fill("用户名", "banz");
    fill("密码", "wrong-pass");
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("用户名或密码不正确。");
  });

  it("checks register fields locally before calling the server", () => {
    const auth = fakeAuth();
    render(<AuthPage api={auth} requiresInvite={false} onAuthed={vi.fn()} />);
    fireEvent.click(screen.getByRole("tab", { name: "注册" }));
    fill("用户名", "banz");
    fill("密码", "12345678");
    fill("确认密码", "12345679");
    fireEvent.click(screen.getByRole("button", { name: "注册并进入" }));
    expect(screen.getByRole("alert")).toHaveTextContent("两次输入的密码不一致");
    fill("密码", "short");
    fill("确认密码", "short");
    fireEvent.click(screen.getByRole("button", { name: "注册并进入" }));
    expect(screen.getByRole("alert")).toHaveTextContent("密码至少 8 位");
    expect(auth.register).not.toHaveBeenCalled();
  });

  it("asks for and sends the invite code only when required", async () => {
    const auth = fakeAuth();
    const { unmount } = render(<AuthPage api={auth} requiresInvite={false} onAuthed={vi.fn()} />);
    fireEvent.click(screen.getByRole("tab", { name: "注册" }));
    expect(screen.queryByLabelText("邀请码")).not.toBeInTheDocument();
    unmount();

    const onAuthed = vi.fn();
    render(<AuthPage api={auth} requiresInvite onAuthed={onAuthed} />);
    fireEvent.click(screen.getByRole("tab", { name: "注册" }));
    fill("用户名", "新用户_01");
    fill("密码", "12345678");
    fill("确认密码", "12345678");
    fireEvent.click(screen.getByRole("button", { name: "注册并进入" }));
    expect(screen.getByRole("alert")).toHaveTextContent("请填写邀请码");
    fill("邀请码", " haic ");
    fireEvent.click(screen.getByRole("button", { name: "注册并进入" }));
    await waitFor(() => expect(onAuthed).toHaveBeenCalled());
    expect(auth.register).toHaveBeenCalledWith("新用户_01", "12345678", "haic");
  });
});

describe("AuthGate", () => {
  it("shows the sign-in page when there is no session, with invite field from health", async () => {
    render(<AuthGate authApi={fakeAuth({
      health: vi.fn().mockResolvedValue({ mode: "live", database: "ok", live_available: true, registration_requires_invite: true }),
    })} />);
    expect(await screen.findByRole("heading", { name: "欢迎回来" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "注册" }));
    expect(screen.getByLabelText("邀请码")).toBeInTheDocument();
  });

  it("offers a retry when the server is unreachable", async () => {
    const me = vi.fn().mockRejectedValueOnce(new Error("无法连接服务，请稍后重试。")).mockResolvedValue(user);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    render(<AuthGate authApi={fakeAuth({ me })} />);
    fireEvent.click(await screen.findByRole("button", { name: "重试" }));
    expect(await screen.findByText("banz")).toBeInTheDocument();
  });

  it("enters the app for a signed-in user, and logs out back to the sign-in page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    const me = vi.fn().mockResolvedValueOnce(user).mockRejectedValue(new AuthError(401, "未登录"));
    const auth = fakeAuth({ me });
    render(<AuthGate authApi={auth} />);
    expect(await screen.findByText("banz")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    expect(await screen.findByRole("heading", { name: "欢迎回来" })).toBeInTheDocument();
    expect(auth.logout).toHaveBeenCalled();
  });

  it("returns to the sign-in page when a protected call reports an expired session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    const me = vi.fn().mockResolvedValueOnce(user).mockRejectedValue(new AuthError(401, "未登录"));
    render(<AuthGate authApi={fakeAuth({ me })} />);
    expect(await screen.findByText("banz")).toBeInTheDocument();
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    expect(await screen.findByRole("heading", { name: "欢迎回来" })).toBeInTheDocument();
  });
});

describe("api 401 handling", () => {
  it("announces an expired session on protected calls", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));
    const heard = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, heard);
    await expect(api.listDecisions()).rejects.toThrow("登录已过期");
    window.removeEventListener(UNAUTHORIZED_EVENT, heard);
    expect(heard).toHaveBeenCalledTimes(1);
  });

  it("does not announce on a failed login, and surfaces the server detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "用户名或密码不正确。" }), { status: 401 })));
    const heard = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, heard);
    await expect(authApi.login("a", "b")).rejects.toMatchObject({ status: 401, message: "用户名或密码不正确。" });
    window.removeEventListener(UNAUTHORIZED_EVENT, heard);
    expect(heard).not.toHaveBeenCalled();
  });
});
