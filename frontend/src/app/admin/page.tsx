"use client";

import { useEffect, useState, type CSSProperties } from "react";

import {
  API_BASE_URL,
  type AdminUserSummary,
  type AuthenticatedUser,
  getCurrentUser,
  resetUserPassword,
} from "@/lib/api";

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "—";
  return timestamp.toLocaleString("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function generateTemporaryPassword(): string {
  const sample = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const randomPart = Array.from({ length: 10 }, () => sample[Math.floor(Math.random() * sample.length)]).join("");
  return `NexuX-${randomPart}`;
}

export default function AdminPage() {
  const [currentUser, setCurrentUser] = useState<AuthenticatedUser | null>(null);
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [actioningUserId, setActioningUserId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [noticeMessage, setNoticeMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadAdminConsole() {
      try {
        const me = await getCurrentUser();
        if (cancelled) return;
        if (me.role !== "admin") {
          window.location.assign("/");
          return;
        }
        setCurrentUser(me);

        const response = await fetch(`${API_BASE_URL}/api/admin/users`, {
          cache: "no-store",
          credentials: "include",
        });
        if (!response.ok) {
          throw new Error("無法載入帳號列表");
        }
        const data = (await response.json()) as AdminUserSummary[];
        if (!cancelled) {
          setUsers(data);
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(
            error instanceof Error ? error.message : "載入管理控制台失敗。",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadAdminConsole();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleResetPassword = async (userId: string, userName: string) => {
    const newPassword = generateTemporaryPassword();
    setActioningUserId(userId);
    setErrorMessage(null);
    setNoticeMessage(null);

    try {
      await resetUserPassword(userId, newPassword);
      setUsers((current) =>
        current.map((user) =>
          user.id === userId
            ? {
                ...user,
                updated_at: new Date().toISOString(),
              }
            : user,
        ),
      );
      setNoticeMessage(
        `已為 ${userName} 重設密碼。新密碼：${newPassword}（請立即通知使用者變更）`,
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "重設密碼失敗。",
      );
    } finally {
      setActioningUserId(null);
    }
  };

  if (loading) {
    return (
      <main style={styles.pageShell}>
        <div style={styles.loadingCard}>載入管理控制台中…</div>
      </main>
    );
  }

  if (!currentUser || currentUser.role !== "admin") {
    return (
      <main style={styles.pageShell}>
        <div style={styles.loadingCard}>權限不足，請先以 Admin 身分登入。</div>
      </main>
    );
  }

  return (
    <main style={styles.pageShell}>
      <div style={styles.wrapper}>
        <header style={styles.header}>
          <div>
            <div style={styles.label}>Admin 控制台</div>
            <h1 style={styles.title}>帳號與存取管理</h1>
          </div>
          <button
            onClick={() => window.location.assign("/")}
            style={styles.backButton}
            type="button"
          >
            返回首頁
          </button>
        </header>

        {noticeMessage && <div style={styles.notice}>{noticeMessage}</div>}
        {errorMessage && <div style={styles.error}>{errorMessage}</div>}

        <section style={styles.summaryCard}>
          <div>
            <div style={styles.summaryLabel}>登入管理員</div>
            <div style={styles.summaryValue}>{currentUser.display_name}</div>
          </div>
          <div>
            <div style={styles.summaryLabel}>角色</div>
            <div style={styles.summaryValue}>Admin</div>
          </div>
          <div>
            <div style={styles.summaryLabel}>帳號總數</div>
            <div style={styles.summaryValue}>{users.length}</div>
          </div>
          <div>
            <div style={styles.summaryLabel}>在線人數</div>
            <div style={styles.summaryValue}>{users.filter((user) => user.is_online).length}</div>
          </div>
        </section>

        <section style={styles.tableCard}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>姓名</th>
                <th style={styles.th}>電子郵件</th>
                <th style={styles.th}>權限</th>
                <th style={styles.th}>狀態</th>
                <th style={styles.th}>最後在線</th>
                <th style={styles.th}>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td style={styles.td}>{user.display_name}</td>
                  <td style={styles.td}>{user.email ?? "—"}</td>
                  <td style={styles.td}>{user.role === "admin" ? "Admin" : "User"}</td>
                  <td style={styles.td}>
                    <span
                      style={
                        user.is_online
                          ? { ...styles.statusPill, ...styles.onlinePill }
                          : { ...styles.statusPill, ...styles.offlinePill }
                      }
                    >
                      {user.is_online ? "在線" : "離線"}
                    </span>
                  </td>
                  <td style={styles.td}>{formatTimestamp(user.last_seen_at)}</td>
                  <td style={styles.td}>
                    <button
                      disabled={actioningUserId === user.id}
                      onClick={() => void handleResetPassword(user.id, user.display_name)}
                      style={
                        actioningUserId === user.id
                          ? { ...styles.actionButton, ...styles.disabledButton }
                          : styles.actionButton
                      }
                      type="button"
                    >
                      {actioningUserId === user.id ? "處理中…" : "重設密碼"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  pageShell: {
    minHeight: "100vh",
    background: "linear-gradient(180deg, #08111d 0%, #101827 100%)",
    color: "#e5eefb",
    display: "flex",
    justifyContent: "center",
    padding: "32px 20px",
    fontFamily: "Inter, 'Noto Sans TC', sans-serif",
  },
  wrapper: {
    width: "100%",
    maxWidth: "1240px",
    display: "flex",
    flexDirection: "column",
    gap: "20px",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "16px",
    padding: "20px 24px",
    background: "rgba(15, 23, 42, 0.82)",
    border: "1px solid rgba(148, 163, 184, 0.2)",
    borderRadius: "20px",
    boxShadow: "0 20px 45px rgba(15, 23, 42, 0.35)",
  },
  label: {
    fontSize: "12px",
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "#93c5fd",
    marginBottom: "6px",
  },
  title: {
    margin: 0,
    fontSize: "clamp(24px, 4vw, 34px)",
  },
  backButton: {
    border: "1px solid rgba(59, 130, 246, 0.6)",
    background: "rgba(59, 130, 246, 0.12)",
    color: "#dbeafe",
    padding: "10px 16px",
    borderRadius: "12px",
    cursor: "pointer",
  },
  loadingCard: {
    background: "rgba(15, 23, 42, 0.9)",
    color: "#dbeafe",
    border: "1px solid rgba(148, 163, 184, 0.25)",
    borderRadius: "18px",
    padding: "30px 24px",
    width: "100%",
    maxWidth: "620px",
    textAlign: "center",
    margin: "auto",
  },
  summaryCard: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: "16px",
    background: "rgba(15, 23, 42, 0.82)",
    border: "1px solid rgba(148, 163, 184, 0.2)",
    borderRadius: "20px",
    padding: "20px 24px",
  },
  summaryLabel: {
    color: "#94a3b8",
    fontSize: "12px",
    marginBottom: "6px",
  },
  summaryValue: {
    fontSize: "28px",
    fontWeight: 700,
    color: "#f8fafc",
  },
  tableCard: {
    background: "rgba(15, 23, 42, 0.82)",
    border: "1px solid rgba(148, 163, 184, 0.2)",
    borderRadius: "20px",
    padding: "18px",
    overflowX: "auto",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    minWidth: "820px",
  },
  th: {
    textAlign: "left",
    color: "#cbd5e1",
    fontSize: "13px",
    padding: "12px 10px",
    borderBottom: "1px solid rgba(148, 163, 184, 0.18)",
  },
  td: {
    padding: "14px 10px",
    borderBottom: "1px solid rgba(148, 163, 184, 0.14)",
    verticalAlign: "middle",
    color: "#e2e8f0",
  },
  statusPill: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "999px",
    padding: "6px 10px",
    fontSize: "12px",
    fontWeight: 700,
  },
  onlinePill: {
    background: "rgba(34, 197, 94, 0.18)",
    color: "#bbf7d0",
  },
  offlinePill: {
    background: "rgba(148, 163, 184, 0.14)",
    color: "#cbd5e1",
  },
  actionButton: {
    border: "1px solid rgba(96, 165, 250, 0.7)",
    background: "rgba(59, 130, 246, 0.18)",
    color: "#dbeafe",
    borderRadius: "10px",
    padding: "8px 12px",
    cursor: "pointer",
    fontWeight: 600,
  },
  disabledButton: {
    opacity: 0.7,
    cursor: "wait",
  },
  notice: {
    background: "rgba(34, 197, 94, 0.14)",
    border: "1px solid rgba(34, 197, 94, 0.35)",
    color: "#bbf7d0",
    borderRadius: "12px",
    padding: "12px 14px",
  },
  error: {
    background: "rgba(239, 68, 68, 0.12)",
    border: "1px solid rgba(239, 68, 68, 0.4)",
    color: "#fecaca",
    borderRadius: "12px",
    padding: "12px 14px",
  },
};
