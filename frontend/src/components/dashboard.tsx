"use client";

import Image from "next/image";
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  FileText,
  FolderOpen,
  History,
  LayoutDashboard,
  LoaderCircle,
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  Paperclip,
  Plus,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Terminal,
  UploadCloud,
  X,
  Zap,
  LogOut,
} from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";

import MessageContent from "@/components/message-content";
import {
  API_BASE_URL,
  ApiError,
  AgentRunResult,
  AgentToolCall,
  AuthenticatedUser,
  ChatDoneEvent,
  ChatModelOption,
  ConversationDetail,
  ConversationMessage,
  ConversationSummary,
  DocumentSummary,
  createConversation,
  getChatModels,
  getConversation,
  getConversations,
  getCurrentUser,
  getDocuments,
  getSkills,
  runAgent,
  signIn,
  signUp,
  signOut,
  searchKnowledge,
  streamChat,
  uploadDocument,
} from "@/lib/api";
import { useDashboardStore } from "@/lib/dashboard-store";

type PendingAttachment = {
  key: string;
  file: File;
  documentId?: string;
  previewUrl?: string;
};

type ChatMode = "chat" | "agent";
const ACCEPTED_FILES =
  ".bmp,.csv,.docx,.gif,.htm,.html,.jpeg,.jpg,.md,.pdf,.png,.pptx,.tif,.tiff,.txt,.webp,.xls,.xlsx";

function errorText(error: unknown): string {
  if (!(error instanceof Error)) return "發生未預期的錯誤，請稍後再試。";

  const message = error.message;
  const translations: Record<string, string> = {
    "Authentication is required": "請先登入後再使用此功能。",
    "Invalid email or password": "電子郵件或密碼不正確。",
    "An account with this email already exists": "此電子郵件已註冊，請直接登入。",
    "The request origin is not allowed": "此請求來源未獲允許，請重新載入頁面後再試。",
    "Conversation not found": "找不到這段對話，或你沒有存取權限。",
    "One or more attached documents were not found":
      "找不到其中一份附件，或你沒有存取權限。",
    "No configured chat model is available.":
      "目前沒有可用的對話模型，請檢查模型設定。",
    "The chat response did not include an event stream":
      "聊天服務未提供串流回應，請稍後再試。",
    "The chat stream ended before its done event":
      "聊天串流意外中斷，請稍後再試。",
  };
  if (translations[message]) return translations[message];
  if (message.startsWith("Request failed with HTTP ")) {
    return `請求失敗（HTTP ${message.slice("Request failed with HTTP ".length)}）。`;
  }
  if (message.startsWith("Chat request failed with HTTP ")) {
    return `聊天請求失敗（HTTP ${message.slice("Chat request failed with HTTP ".length)}）。`;
  }
  return message;
}

function detailSummary(detail: ConversationDetail): ConversationSummary {
  return {
    id: detail.id,
    title: detail.title,
    created_at: detail.created_at,
    updated_at: detail.updated_at,
  };
}

function formatBytes(size: number): string {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function providerLabel(provider: ChatModelOption["provider"]): string {
  return provider === "ollama" ? "本機 Ollama" : "OpenAI 相容 API";
}

function conversationTitle(title: string): string {
  return title === "New conversation" ? "新對話" : title;
}

function documentColor(name: string): string {
  const extension = name.split(".").pop()?.toLowerCase();
  if (["png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "webp"].includes(extension ?? "")) {
    return "teal";
  }
  if (["pptx", "xlsx", "xls", "csv"].includes(extension ?? "")) return "blue";
  return "violet";
}

function BrandMark() {
  return (
    <div className="brand-mark" aria-hidden="true">
      <span />
      <span />
      <span />
      <span />
    </div>
  );
}

export default function Dashboard() {
  const {
    activePanel,
    isSidebarOpen,
    setActivePanel,
    setSidebarOpen,
    toggleSidebar,
  } = useDashboardStore();
  const [authLoading, setAuthLoading] = useState(true);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authDisplayName, setAuthDisplayName] = useState("");
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [isKnowledgeSearchOpen, setKnowledgeSearchOpen] = useState(false);
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [knowledgeResults, setKnowledgeResults] = useState<
    Awaited<ReturnType<typeof searchKnowledge>>["results"]
  >([]);
  const [hasSearchedKnowledge, setHasSearchedKnowledge] = useState(false);
  const [knowledgeSearchError, setKnowledgeSearchError] = useState<string | null>(null);
  const [isKnowledgeSearching, setIsKnowledgeSearching] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [skills, setSkills] = useState<{ name: string; description: string }[]>([]);
  const [models, setModels] = useState<ChatModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState<ChatModelOption | null>(null);
  const [chatMode, setChatMode] = useState<ChatMode>("chat");
  const [draft, setDraft] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{
    completed: number;
    total: number;
    currentFile: string;
  } | null>(null);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);
  const [isLoadingConversation, setIsLoadingConversation] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [agentCalls, setAgentCalls] = useState<AgentToolCall[]>([]);
  const chatFileInput = useRef<HTMLInputElement>(null);
  const libraryFileInput = useRef<HTMLInputElement>(null);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const knowledgeSearchInput = useRef<HTMLInputElement>(null);
  const composerAbort = useRef<AbortController | null>(null);
  const pendingAttachmentCleanup = useRef<PendingAttachment[]>([]);

  useEffect(() => {
    const compactViewport = window.matchMedia("(max-width: 980px)");
    const closeSidebarOnCompactViewport = () => {
      if (compactViewport.matches) setSidebarOpen(false);
    };

    closeSidebarOnCompactViewport();
    compactViewport.addEventListener("change", closeSidebarOnCompactViewport);
    return () =>
      compactViewport.removeEventListener("change", closeSidebarOnCompactViewport);
  }, [setSidebarOpen]);

  useEffect(() => {
    const handleSearchShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setKnowledgeSearchOpen(true);
      } else if (event.key === "Escape") {
        setKnowledgeSearchOpen(false);
      }
    };

    window.addEventListener("keydown", handleSearchShortcut);
    return () => window.removeEventListener("keydown", handleSearchShortcut);
  }, []);

  useEffect(() => {
    if (isKnowledgeSearchOpen) knowledgeSearchInput.current?.focus();
  }, [isKnowledgeSearchOpen]);

  useEffect(() => {
    let cancelled = false;
    const loadWorkspace = async () => {
      let signedInUser: AuthenticatedUser;
      try {
        signedInUser = await getCurrentUser();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          if (!cancelled) setAuthLoading(false);
          return;
        }
        if (!cancelled) {
          setErrorMessage(errorText(error));
          setAuthLoading(false);
        }
        return;
      }

      if (cancelled) return;
      setUser(signedInUser);
      setAuthLoading(false);
      try {
        const [catalog, sessions, library, registeredSkills] = await Promise.all([
          getChatModels(),
          getConversations(),
          getDocuments(),
          getSkills(),
        ]);
        if (cancelled) return;
        setModels(catalog.models);
        setSelectedModel(
          catalog.models.find(
            (option) =>
              option.provider === catalog.default_provider &&
              option.model === catalog.default_model,
          ) ?? catalog.models.find((option) => option.configured) ?? null,
        );
        setConversations(sessions);
        setDocuments(library);
        setSkills(registeredSkills);
        if (sessions.length > 0) {
          const detail = await getConversation(sessions[0].id);
          if (cancelled) return;
          setActiveSession(detail.id);
          setMessages(detail.messages);
          setAgentCalls(detail.messages.flatMap((message) => message.tool_calls));
        }
      } catch (error) {
        if (!cancelled) setErrorMessage(errorText(error));
      }
    };
    void loadWorkspace();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    pendingAttachmentCleanup.current = pendingAttachments;
  }, [pendingAttachments]);

  useEffect(() => {
    return () => {
      pendingAttachmentCleanup.current.forEach((attachment) => {
        if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
      });
      composerAbort.current?.abort();
    };
  }, []);

  const activeSessionTitle =
    conversationTitle(
      conversations.find((session) => session.id === activeSession)?.title ?? "",
    ) ||
    "新對話";

  const addDocuments = (added: DocumentSummary[]) => {
    setDocuments((current) => {
      const byId = new Map(current.map((document) => [document.document_id, document]));
      added.forEach((document) => byId.set(document.document_id, document));
      return [...byId.values()].sort(
        (left, right) =>
          new Date(right.uploaded_at).getTime() -
          new Date(left.uploaded_at).getTime(),
      );
    });
  };

  const selectConversation = async (conversationId: string) => {
    setIsLoadingConversation(true);
    setErrorMessage(null);
    try {
      const detail = await getConversation(conversationId);
      setActiveSession(detail.id);
      setMessages(detail.messages);
      setAgentCalls(detail.messages.flatMap((message) => message.tool_calls));
      setChatMode("chat");
    } catch (error) {
      setErrorMessage(errorText(error));
    } finally {
      setIsLoadingConversation(false);
    }
  };

  const startNewConversation = async () => {
    setErrorMessage(null);
    try {
      const conversation = await createConversation();
      setConversations((current) => [conversation, ...current]);
      setActiveSession(conversation.id);
      setMessages([]);
      setAgentCalls([]);
      setStreamingText("");
      setChatMode("chat");
    } catch (error) {
      setErrorMessage(errorText(error));
    }
  };

  const queueAttachments = (files: FileList | File[]) => {
    if (isSending) return;
    const incoming = Array.from(files);
    if (pendingAttachments.length + incoming.length > 10) {
      setErrorMessage("單則訊息最多可附加 10 個檔案。");
      return;
    }
    setErrorMessage(null);
    setPendingAttachments((current) => [
      ...current,
      ...incoming.map((file) => ({
        key: crypto.randomUUID(),
        file,
        previewUrl: file.type.startsWith("image/")
          ? URL.createObjectURL(file)
          : undefined,
      })),
    ]);
  };

  const removeAttachment = (key: string) => {
    const target = pendingAttachments.find((attachment) => attachment.key === key);
    if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
    setPendingAttachments((current) =>
      current.filter((attachment) => attachment.key !== key),
    );
  };

  const uploadToLibrary = async (files: FileList | File[]) => {
    const incoming = Array.from(files);
    if (incoming.length === 0) return;

    setIsUploading(true);
    setUploadProgress({
      completed: 0,
      total: incoming.length,
      currentFile: incoming[0].name,
    });
    setErrorMessage(null);
    try {
      for (const [index, file] of incoming.entries()) {
        setUploadProgress({
          completed: index,
          total: incoming.length,
          currentFile: file.name,
        });
        addDocuments([await uploadDocument(file)]);
        setUploadProgress({
          completed: index + 1,
          total: incoming.length,
          currentFile: incoming[index + 1]?.name ?? file.name,
        });
      }
    } catch (error) {
      setErrorMessage(errorText(error));
    } finally {
      setIsUploading(false);
      setUploadProgress(null);
    }
  };

  const refreshConversation = async (conversationId: string) => {
    const detail = await getConversation(conversationId);
    setMessages(detail.messages);
    setAgentCalls(detail.messages.flatMap((message) => message.tool_calls));
    setConversations((current) => [
      detailSummary(detail),
      ...current.filter((conversation) => conversation.id !== detail.id),
    ]);
    return detail;
  };

  const sendMessage = async () => {
    if (isSending || (!draft.trim() && pendingAttachments.length === 0)) return;
    if (!selectedModel) {
      setErrorMessage("目前沒有可用的對話模型，請檢查模型設定。");
      return;
    }
    const mode = chatMode;
    const prompt =
      draft.trim() ||
      "請摘要附件內容，並整理其中的重點。";
    setErrorMessage(null);
    setIsSending(true);
    let conversationId = activeSession;
    let attachmentIds: string[] = [];
    try {
      if (!conversationId) {
        const conversation = await createConversation();
        conversationId = conversation.id;
        setActiveSession(conversation.id);
        setConversations((current) => [conversation, ...current]);
      }
      const uploadedAttachments: PendingAttachment[] = [];
      for (const attachment of pendingAttachments) {
        if (attachment.documentId) {
          uploadedAttachments.push(attachment);
          continue;
        }
        const document = await uploadDocument(attachment.file);
        addDocuments([document]);
        uploadedAttachments.push({
          ...attachment,
          documentId: document.document_id,
        });
        setPendingAttachments((current) =>
          current.map((item) =>
            item.key === attachment.key
              ? { ...item, documentId: document.document_id }
              : item,
          ),
        );
      }
      attachmentIds = uploadedAttachments.flatMap((item) =>
        item.documentId ? [item.documentId] : [],
      );
      setMessages((current) => [
        ...current,
        {
          id: `pending-${crypto.randomUUID()}`,
          role: "user",
          content: prompt,
          usage: null,
          tool_calls: [],
          attachment_ids: attachmentIds,
          images: [],
          created_at: new Date().toISOString(),
        },
      ]);

      if (mode === "agent") {
        const result: AgentRunResult = await runAgent(
          prompt,
          conversationId,
          attachmentIds,
        );
        setAgentCalls(result.tool_calls);
        setActivePanel("agent");
        await refreshConversation(conversationId);
      } else {
        const controller = new AbortController();
        composerAbort.current = controller;
        setStreamingText("");
        const done: ChatDoneEvent = await streamChat(
          prompt,
          conversationId,
          attachmentIds,
          selectedModel,
          controller.signal,
          (token) => setStreamingText((current) => current + token),
        );
        if (done.conversation_id) {
          await refreshConversation(done.conversation_id);
        }
      }
      setDraft("");
      setPendingAttachments((current) => {
        current.forEach((attachment) => {
          if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
        });
        return [];
      });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setErrorMessage(errorText(error));
      }
      if (conversationId) {
        try {
          await refreshConversation(conversationId);
        } catch (refreshError) {
          setErrorMessage(
            `${errorText(error)} 更新對話紀錄失敗：${errorText(refreshError)}`,
          );
        }
      }
    } finally {
      composerAbort.current = null;
      setStreamingText("");
      setIsSending(false);
    }
  };

  const handleSignOut = async () => {
    try {
      await signOut();
      setUser(null);
      setConversations([]);
      setActiveSession(null);
      setMessages([]);
      setDocuments([]);
      setSkills([]);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(errorText(error));
    }
  };

  const handleKnowledgeSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const query = knowledgeQuery.trim();
    if (!query || isKnowledgeSearching) return;

    setIsKnowledgeSearching(true);
    setKnowledgeSearchError(null);
    setKnowledgeResults([]);
    setHasSearchedKnowledge(false);
    try {
      const response = await searchKnowledge(query);
      setKnowledgeResults(response.results);
      setHasSearchedKnowledge(true);
    } catch (error) {
      setKnowledgeSearchError(errorText(error));
    } finally {
      setIsKnowledgeSearching(false);
    }
  };

  const continueSearchInChat = (sourceName: string) => {
    setDraft(`請根據文件「${sourceName}」回答：${knowledgeQuery.trim()}`);
    setChatMode("chat");
    setKnowledgeSearchOpen(false);
    window.setTimeout(() => composerInput.current?.focus(), 0);
  };

  const handleAuthSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthSubmitting(true);
    setErrorMessage(null);
    try {
      const input = {
        email: authEmail,
        password: authPassword,
      };
      if (authMode === "register") {
        await signUp({ ...input, display_name: authDisplayName });
      } else {
        await signIn(input);
      }
      window.location.reload();
    } catch (error) {
      setErrorMessage(errorText(error));
    } finally {
      setAuthSubmitting(false);
    }
  };

  if (authLoading) {
    return <div className="auth-gate"><LoaderCircle className="spin" size={22} /> 正在連線至工作區…</div>;
  }

  if (!user) {
    return (
      <main className="auth-gate">
        <div className="auth-card">
          <div className="auth-mark"><BrandMark /></div>
          <span className="eyebrow">NEXUX 知識工作區</span>
          <h1>{authMode === "login" ? "登入你的知識空間" : "建立你的帳號"}</h1>
          <p>
            註冊或登入後即可使用；你的對話與文件會與其他使用者隔離。
          </p>
          {errorMessage && <div className="error-banner" role="alert">{errorMessage}</div>}
          <form className="auth-form" onSubmit={handleAuthSubmit}>
            {authMode === "register" && (
              <label>
                顯示名稱（選填）
                <input
                  autoComplete="name"
                  maxLength={80}
                  onChange={(event) => setAuthDisplayName(event.target.value)}
                  value={authDisplayName}
                />
              </label>
            )}
            <label>
              電子郵件
              <input
                autoComplete="email"
                maxLength={254}
                onChange={(event) => setAuthEmail(event.target.value)}
                required
                type="email"
                value={authEmail}
              />
            </label>
            <label>
              密碼
              <input
                autoComplete={authMode === "register" ? "new-password" : "current-password"}
                maxLength={128}
                minLength={authMode === "register" ? 8 : 1}
                onChange={(event) => setAuthPassword(event.target.value)}
                required
                type="password"
                value={authPassword}
              />
            </label>
            <button className="auth-button" disabled={authSubmitting} type="submit">
              {authSubmitting
                ? "處理中…"
                : authMode === "login"
                  ? "登入"
                  : "註冊並登入"}
            </button>
          </form>
          <button
            className="auth-switch"
            onClick={() => {
              setAuthMode(authMode === "login" ? "register" : "login");
              setErrorMessage(null);
            }}
            type="button"
          >
            {authMode === "login" ? "還沒有帳號？立即註冊" : "已有帳號？返回登入"}
          </button>
        </div>
      </main>
    );
  }

  return (
    <div
      className={`dashboard-shell${isSidebarOpen ? "" : " sidebar-collapsed"}`}
    >
      {isSidebarOpen && (
        <button
          aria-label="關閉導覽列"
          className="mobile-scrim"
          onClick={() => setSidebarOpen(false)}
          type="button"
        />
      )}

      <aside aria-label="主導覽列" className="left-sidebar">
        <div className="sidebar-brand">
          <a aria-label="NexuX 首頁" className="brand-lockup" href="#">
            <BrandMark />
            <span className="brand-wordmark">NEXUX</span>
          </a>
          <button
            aria-label={isSidebarOpen ? "收合導覽列" : "展開導覽列"}
            className="icon-button sidebar-collapse"
            onClick={toggleSidebar}
            type="button"
          >
            {isSidebarOpen ? <PanelLeftClose size={17} /> : <ChevronRight size={17} />}
          </button>
        </div>

        <button className="workspace-switcher" type="button">
          <span className="workspace-avatar">N</span>
          <span className="workspace-copy">
            <span className="eyebrow">工作區</span>
            <span className="workspace-name">知識探索</span>
          </span>
          <ChevronDown className="workspace-chevron" size={15} />
        </button>

        <nav className="primary-nav" aria-label="工作區導覽">
          <button
            className={`nav-item${isKnowledgeSearchOpen ? "" : " nav-item-active"}`}
            onClick={() => setKnowledgeSearchOpen(false)}
            type="button"
          >
            <LayoutDashboard size={17} />
            <span>總覽</span>
            {!isKnowledgeSearchOpen && <span className="nav-active-indicator" />}
          </button>
          <button
            aria-expanded={isKnowledgeSearchOpen}
            aria-haspopup="dialog"
            className={`nav-item${isKnowledgeSearchOpen ? " nav-item-active" : ""}`}
            onClick={() => setKnowledgeSearchOpen(true)}
            type="button"
          >
            <Search size={17} />
            <span>搜尋知識</span>
            <kbd>⌘ K</kbd>
          </button>
          <button className="nav-item" type="button">
            <FolderOpen size={17} />
            <span>知識庫</span>
            <span className="nav-count">{String(documents.length).padStart(2, "0")}</span>
          </button>
          <button className="nav-item" type="button">
            <Bot size={17} />
            <span>Agent 技能</span>
            <span className="online-dot" />
          </button>
        </nav>

        <div className="sidebar-section-heading">
          <span>最近對話</span>
          <button
            className="icon-button subtle-icon"
            aria-label="建立新對話"
            disabled={isSending}
            onClick={() => void startNewConversation()}
            type="button"
          >
            <Plus size={15} />
          </button>
        </div>
        <div className="session-list">
          {conversations.map((session) => (
            <button
              aria-current={activeSession === session.id ? "page" : undefined}
              className={`session-item${activeSession === session.id ? " session-active" : ""}`}
              disabled={isSending}
              key={session.id}
              onClick={() => void selectConversation(session.id)}
              type="button"
            >
              <MessageSquarePlus size={15} />
              <span>{conversationTitle(session.title)}</span>
            </button>
          ))}
          {conversations.length === 0 && (
            <span className="session-empty">目前沒有已儲存的對話</span>
          )}
        </div>

        <div className="sidebar-bottom">
          <div className="usage-card">
            <div className="usage-card-top">
              <span className="usage-icon"><Zap size={14} /></span>
              <span>工作區使用狀態</span>
              <MoreHorizontal size={15} />
            </div>
            <div className="usage-meter"><span /></div>
            <div className="usage-caption">
              <span>本機模型推論</span>
              <span>就緒</span>
            </div>
          </div>
          <button className="nav-item footer-nav-item" type="button">
            <Settings2 size={17} />
            <span>設定</span>
          </button>
          <button className="nav-item footer-nav-item" type="button">
            <CircleHelp size={17} />
            <span>說明中心</span>
          </button>
          <div className="profile-row">
            <div className="profile-avatar">
              {user.display_name.slice(0, 1).toUpperCase()}
            </div>
            <div className="profile-copy">
              <span>{user.display_name}</span>
              <span>{user.email ?? "組織帳號"}</span>
            </div>
            <button
              aria-label="登出"
              className="icon-button subtle-icon"
              onClick={() => void handleSignOut()}
              type="button"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main-workspace">
        <header className="top-bar">
          <div className="breadcrumb">
            <button
              aria-label={isSidebarOpen ? "關閉導覽列" : "開啟導覽列"}
              className="icon-button mobile-menu-button"
              onClick={toggleSidebar}
              type="button"
            >
              {isSidebarOpen ? <X size={17} /> : <PanelLeftClose size={17} />}
            </button>
            <span className="breadcrumb-muted">知識探索</span>
            <ChevronRight size={14} />
            <span className="breadcrumb-current">{activeSessionTitle}</span>
          </div>
          <div className="top-bar-actions">
            <div className="system-status">
              <span className="status-pulse" />
              <span>個人專屬工作區</span>
            </div>
            <button aria-label="活動狀態" className="icon-button top-action" type="button">
              <Activity size={17} />
            </button>
            <div aria-label={user.display_name} className="profile-avatar top-avatar">
              {user.display_name.slice(0, 1).toUpperCase()}
            </div>
          </div>
        </header>

        <div className="workspace-body">
          <div className="conversation-toolbar">
            <div className="conversation-label">
              <span className="toolbar-icon"><Sparkles size={15} /></span>
              <span className="eyebrow">知識對話</span>
              <span className="toolbar-divider" />
              <span className="session-id">
                {activeSession ? activeSession.slice(0, 8).toUpperCase() : "新工作階段"}
              </span>
            </div>
            <div className="conversation-controls">
              <label className="model-selector">
                <span className="model-indicator" />
                <select
                  aria-label="選擇對話模型"
                  className="model-select"
                  disabled={models.length === 0 || isSending}
                  onChange={(event) => {
                    const [provider, ...modelParts] = event.currentTarget.value.split(":");
                    const modelName = modelParts.join(":");
                    const selected = models.find(
                      (option) =>
                        option.provider === provider && option.model === modelName,
                    );
                    if (selected?.configured) setSelectedModel(selected);
                  }}
                  value={
                    selectedModel
                      ? `${selectedModel.provider}:${selectedModel.model}`
                      : ""
                  }
                >
                  {models.map((option) => (
                    <option
                      disabled={!option.configured}
                      key={`${option.provider}:${option.model}`}
                      value={`${option.provider}:${option.model}`}
                    >
                      {option.model} · {providerLabel(option.provider)}
                      {!option.configured ? "（尚未設定）" : ""}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} />
              </label>
              <button
                aria-pressed={chatMode === "agent"}
                className={`agent-status${chatMode === "agent" ? " agent-mode-active" : ""}`}
                disabled={isSending}
                onClick={() => {
                  setChatMode((mode) => (mode === "chat" ? "agent" : "chat"));
                  if (chatMode === "chat") setActivePanel("agent");
                }}
                type="button"
              >
                <span className="agent-status-icon"><Bot size={15} /></span>
                <span>{chatMode === "agent" ? "Agent 模式" : "一般對話"}</span>
                <span className="agent-ready-dot" />
              </button>
              <button className="icon-button more-button" aria-label="更多對話選項" type="button">
                <MoreHorizontal size={18} />
              </button>
            </div>
          </div>

          <section aria-label={activeSessionTitle} className="conversation-stage">
            <div className="welcome-orbit orbit-one" />
            <div className="welcome-orbit orbit-two" />
            {errorMessage && <div className="error-banner" role="alert">{errorMessage}</div>}
            {messages.length === 0 && !streamingText ? (
              <div className="welcome-content">
                <div className="welcome-emblem">
                  <BrandMark />
                  <span className="emblem-glow" />
                </div>
                <div className="welcome-overline">
                  <span className="overline-line" />
                  讓知識開始探索
                  <span className="overline-line" />
                </div>
                <h1 id="welcome-heading">
                  歡迎，{user.display_name.split(/\s+/)[0]}
                </h1>
                <p className="welcome-description">
                  探索知識、串連線索，將資訊轉化為洞見。
                </p>

                <div className="suggestion-grid">
                  <button
                    className="suggestion-card"
                    onClick={() => composerInput.current?.focus()}
                    type="button"
                  >
                    <span className="suggestion-icon violet-icon"><Search size={16} /></span>
                    <span className="suggestion-copy">
                      <span>搜尋關鍵線索</span>
                      <span>探索你的知識內容</span>
                    </span>
                    <ArrowUpRight size={15} />
                  </button>
                  <button
                    className="suggestion-card"
                    onClick={() => chatFileInput.current?.click()}
                    type="button"
                  >
                    <span className="suggestion-icon blue-icon"><FileText size={16} /></span>
                    <span className="suggestion-copy">
                      <span>解析一份文件</span>
                      <span>摘要核心概念與細節</span>
                    </span>
                    <ArrowUpRight size={15} />
                  </button>
                  <button
                    className="suggestion-card"
                    onClick={() => {
                      setChatMode("agent");
                      setActivePanel("agent");
                      composerInput.current?.focus();
                    }}
                    type="button"
                  >
                    <span className="suggestion-icon teal-icon"><Zap size={16} /></span>
                    <span className="suggestion-copy">
                      <span>執行 Agent 技能</span>
                      <span>使用已註冊的工具完成任務</span>
                    </span>
                    <ArrowUpRight size={15} />
                  </button>
                  <button
                    className="suggestion-card"
                    onClick={() => {
                      if (conversations[0]) void selectConversation(conversations[0].id);
                    }}
                    type="button"
                  >
                    <span className="suggestion-icon amber-icon"><History size={16} /></span>
                    <span className="suggestion-copy">
                      <span>繼續探索</span>
                      <span>接續上次的對話</span>
                    </span>
                    <ArrowUpRight size={15} />
                  </button>
                </div>
              </div>
            ) : (
              <div aria-live="polite" className="conversation-messages">
                {isLoadingConversation && (
                  <div className="loading-conversation">
                    <LoaderCircle className="spin" size={18} />
                    正在載入對話…
                  </div>
                )}
                {messages.map((message) => (
                  <article
                    className={`chat-message chat-message-${message.role}`}
                    key={message.id}
                  >
                    <div className="message-role">
                      {message.role === "user" ? "你" : "NexuX"}
                    </div>
                    <div className="message-bubble">
                      <MessageContent content={message.content} />
                      {message.images.length > 0 && (
                        <div className="message-relevant-images">
                          {message.images.map((image) => (
                            <a
                              className="message-relevant-image"
                              href={`${API_BASE_URL}${image.url}`}
                              key={`${image.document_id}-${image.image_id}`}
                              rel="noreferrer"
                              target="_blank"
                            >
                              <Image
                                alt={`${image.source_name}，${image.location}`}
                                className="message-relevant-image-preview"
                                height={360}
                                src={`${API_BASE_URL}${image.url}`}
                                unoptimized
                                width={640}
                              />
                              <span>{image.source_name} · {image.location}</span>
                            </a>
                          ))}
                        </div>
                      )}
                      {message.attachment_ids.length > 0 && (
                        <div className="message-attachments">
                          {message.attachment_ids.map((documentId) => (
                            <span className="message-attachment" key={documentId}>
                              <FileText size={12} />
                              {documents.find(
                                (document) => document.document_id === documentId,
                              )?.source_name ?? "已附加的文件"}
                            </span>
                          ))}
                        </div>
                      )}
                      {message.usage && (
                        <span className="message-usage">
                          {message.usage.total_tokens} 個 Token · {message.usage.source === "provider" ? "模型提供" : "估算"}
                        </span>
                      )}
                    </div>
                  </article>
                ))}
                {isSending && chatMode === "agent" && (
                  <div className="agent-thinking">
                    <LoaderCircle className="spin" size={16} />
                    Agent 正在檢查已註冊的技能…
                  </div>
                )}
                {streamingText && (
                  <article className="chat-message chat-message-assistant">
                    <div className="message-role">NexuX</div>
                    <div className="message-bubble">
                      <MessageContent content={streamingText} />
                    </div>
                  </article>
                )}
                {isSending && !streamingText && chatMode === "chat" && (
                  <div className="agent-thinking">
                    <LoaderCircle className="spin" size={16} />
                    正在搜尋你的工作區…
                  </div>
                )}
              </div>
            )}

            <div
              aria-label="Chat composer"
              className={`composer-card${isDraggingFiles ? " composer-dragging" : ""}`}
              onDragEnter={(event) => {
                event.preventDefault();
                setIsDraggingFiles(true);
              }}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                  setIsDraggingFiles(false);
                }
              }}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                setIsDraggingFiles(false);
                if (event.dataTransfer.files.length > 0) {
                  queueAttachments(event.dataTransfer.files);
                }
              }}
            >
              {isDraggingFiles && (
                <div className="drop-indicator">放開檔案即可附加至這段對話</div>
              )}
              <input
                accept={ACCEPTED_FILES}
                className="visually-hidden"
                multiple
                onChange={(event) => {
                  if (event.currentTarget.files) queueAttachments(event.currentTarget.files);
                  event.currentTarget.value = "";
                }}
                ref={chatFileInput}
                type="file"
              />
              <input
                accept={ACCEPTED_FILES}
                className="visually-hidden"
                multiple
                onChange={(event) => {
                  if (event.currentTarget.files) {
                    void uploadToLibrary(event.currentTarget.files);
                  }
                  event.currentTarget.value = "";
                }}
                ref={libraryFileInput}
                type="file"
              />
              {pendingAttachments.length > 0 && (
                <div className="pending-file-list">
                  {pendingAttachments.map((attachment) => (
                    <div className="pending-file" key={attachment.key}>
                      {attachment.previewUrl ? (
                        <Image
                          alt=""
                          className="pending-image-preview"
                          height={32}
                          src={attachment.previewUrl}
                          unoptimized
                          width={32}
                        />
                      ) : (
                        <FileText size={15} />
                      )}
                      <span className="pending-file-name">{attachment.file.name}</span>
                      <span className="pending-file-size">
                        {attachment.documentId ? "已完成索引" : formatBytes(attachment.file.size)}
                      </span>
                      <button
                        aria-label={`移除 ${attachment.file.name}`}
                        className="icon-button subtle-icon"
                        disabled={isSending}
                        onClick={() => removeAttachment(attachment.key)}
                        type="button"
                      >
                        <X size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div className="composer-input-row">
                <textarea
                  aria-label="訊息"
                  className="composer-input"
                  disabled={isSending}
                  placeholder="詢問任何與知識內容相關的問題…"
                  rows={1}
                  ref={composerInput}
                  value={draft}
                  onChange={(event) => setDraft(event.currentTarget.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void sendMessage();
                    }
                  }}
                />
                <button
                  aria-label={isSending ? "停止回覆" : "傳送訊息"}
                  className="send-button"
                  disabled={isSending && chatMode === "agent"}
                  onClick={() => {
                    if (isSending) composerAbort.current?.abort();
                    else void sendMessage();
                  }}
                  type="button"
                >
                  {isSending ? <X size={17} /> : <Send size={17} />}
                </button>
              </div>
              <div className="composer-footer">
                <div className="composer-tools">
                  <button
                    className="composer-tool"
                    disabled={isSending}
                    onClick={() => chatFileInput.current?.click()}
                    type="button"
                  >
                    <Paperclip size={15} />
                    <span>新增附件</span>
                  </button>
                  <span className="tool-divider" />
                  <span className="composer-hint">
                    {chatMode === "agent" ? "已註冊的 Python 技能" : "私人知識搜尋"}
                  </span>
                </div>
                <span className="composer-preview-label">
                  {isUploading ? "正在建立檔案索引…" : "按 Enter 傳送 · Shift+Enter 換行"}
                </span>
              </div>
            </div>

            <div className="stage-footer">
              <span><ShieldCheck size={13} /> 僅限本人帳號使用</span>
              <span>你的工作區僅供本人使用</span>
            </div>
          </section>
        </div>
      </main>

      <aside aria-label="工作區資訊面板" className="right-inspector">
        <div className="inspector-header">
          <div>
            <span className="eyebrow">工作區</span>
            <h2>知識與執行資訊</h2>
          </div>
          <button className="icon-button subtle-icon" aria-label="面板選項" type="button">
            <MoreHorizontal size={17} />
          </button>
        </div>

        <div aria-label="資訊面板檢視" className="inspector-tabs" role="tablist">
          <button
            aria-selected={activePanel === "knowledge"}
            className={`inspector-tab${activePanel === "knowledge" ? " inspector-tab-active" : ""}`}
            onClick={() => setActivePanel("knowledge")}
            role="tab"
            type="button"
          >
            <BookOpen size={14} /> 知識庫
          </button>
          <button
            aria-selected={activePanel === "agent"}
            className={`inspector-tab${activePanel === "agent" ? " inspector-tab-active" : ""}`}
            onClick={() => setActivePanel("agent")}
            role="tab"
            type="button"
          >
            <Terminal size={14} /> Agent 執行記錄
          </button>
        </div>

        {activePanel === "knowledge" ? (
          <div className="inspector-content">
            <div className="inspector-section-title">
              <div>
                <span className="eyebrow">你的文件</span>
                <h3>知識庫</h3>
              </div>
              <span className="document-count">
                {String(documents.length).padStart(2, "0")}
              </span>
            </div>
            <button
              className="upload-dropzone"
              disabled={isUploading}
              onClick={() => libraryFileInput.current?.click()}
              type="button"
            >
              <span className="upload-icon"><UploadCloud size={18} /></span>
              <span className="upload-copy">
                <span>{isUploading ? "正在建立文件索引…" : "新增至知識庫"}</span>
                <span>PDF、Office、文字與圖片 · 上限 100 MB</span>
              </span>
              {isUploading ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}
            </button>
            {uploadProgress && (
              <div aria-live="polite" className="upload-progress">
                <div className="upload-progress-copy">
                  <span>
                    已完成 {uploadProgress.completed} / {uploadProgress.total} 個文件
                  </span>
                  <span className="upload-progress-file" title={uploadProgress.currentFile}>
                    正在處理：{uploadProgress.currentFile}
                  </span>
                </div>
                <div
                  aria-label="文件索引進度"
                  aria-valuemax={uploadProgress.total}
                  aria-valuemin={0}
                  aria-valuenow={uploadProgress.completed}
                  className="upload-progress-track"
                  role="progressbar"
                >
                  <span
                    className="upload-progress-fill"
                    style={{
                      width: `${(uploadProgress.completed / uploadProgress.total) * 100}%`,
                    }}
                  />
                </div>
              </div>
            )}
            <div className="document-list">
              {documents.map((document) => (
                <div className="document-item" key={document.document_id}>
                  <span className={`document-icon ${documentColor(document.source_name)}`}>
                    <FileText size={16} />
                  </span>
                  <span className="document-copy">
                    <span>{document.source_name}</span>
                    <span>{document.chunks_indexed} 個索引片段</span>
                  </span>
                  <span className="document-timestamp">
                    {new Date(document.uploaded_at).toLocaleDateString("zh-TW")}
                  </span>
                </div>
              ))}
              {documents.length === 0 && (
                <div className="library-empty">
                  上傳的文件會建立索引，並僅供你的帳號使用。
                </div>
              )}
            </div>

            <div className="inspector-divider" />

            <div className="inspector-section-title collection-title">
              <div>
                <span className="eyebrow">帳號範圍</span>
                <h3>私人索引</h3>
              </div>
            </div>

            <div className="storage-card">
              <div className="storage-topline">
                <span>索引狀態</span>
                <span className={`indexed-state${documents.length === 0 ? " index-empty" : ""}`}>
                  <span /> {documents.length > 0 ? "就緒" : "尚無文件"}
                </span>
              </div>
              <div className="storage-title">
                {documents.length} 個文件
              </div>
              <div className="storage-caption">
                <span>混合搜尋 · 使用者資料隔離</span>
                {documents.length > 0 && <Check size={14} />}
              </div>
            </div>
          </div>
        ) : (
          <div className="inspector-content agent-log-content">
            <div className="inspector-section-title">
              <div>
                <span className="eyebrow">執行狀態</span>
                <h3>Agent 活動</h3>
              </div>
              <span className="live-label"><span /> {agentCalls.length > 0 ? "最近執行" : "就緒"}</span>
            </div>
            {agentCalls.length === 0 ? (
              <div className="agent-empty-state">
                <span className="agent-empty-icon"><Bot size={20} /></span>
                <span className="agent-empty-title">等待任務</span>
                <span className="agent-empty-copy">
                  切換至 Agent 模式並傳送任務，即可查看技能呼叫與執行結果。
                </span>
              </div>
            ) : (
              <div className="agent-call-list">
                {agentCalls.map((call, index) => (
                  <div
                    className={`agent-call${call.error ? " agent-call-error" : ""}`}
                    key={`${call.skill_name}-${index}`}
                  >
                    <div className="agent-call-heading">
                      <Terminal size={13} />
                      <span>{call.skill_name}</span>
                      <span>{call.error ? "錯誤" : "完成"}</span>
                    </div>
                    <pre>
                      {call.error ??
                        JSON.stringify(call.result, null, 2) ??
                        String(call.result)}
                    </pre>
                  </div>
                ))}
              </div>
            )}
            <div className="inspector-divider" />
            <div className="inspector-section-title skill-title">
              <div>
                <span className="eyebrow">可用工具</span>
                <h3>已註冊技能</h3>
              </div>
              <span className="document-count">
                {String(skills.length).padStart(2, "0")}
              </span>
            </div>
            {skills.map((skill) => (
              <div className="skill-card" key={skill.name}>
                <div className="skill-card-top">
                  <span className="skill-symbol"><Terminal size={15} /></span>
                  <span className="skill-ready">就緒</span>
                </div>
                <div className="skill-name">{skill.name}</div>
                <p>
                  {skill.name === "text_stats"
                    ? "統計指定文字的字元數、單字數與行數。"
                    : skill.description}
                </p>
                <div className="skill-card-footer">
                  <span>Python 技能</span>
                  <span><Clock3 size={12} /> 已註冊</span>
                </div>
              </div>
            ))}
            <div className="runtime-note">
              <Activity size={14} />
              <span>Agent 技能透過平台 API 安全執行。</span>
            </div>
          </div>
        )}

        <div className="inspector-footer">
          <span className="security-mark"><ShieldCheck size={14} /></span>
          <span><strong>隱私優先設計</strong><br />你的工作區，由你掌握。</span>
          <ChevronRight size={15} />
        </div>
      </aside>
      {isKnowledgeSearchOpen && (
        <div
          className="knowledge-search-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setKnowledgeSearchOpen(false);
            }
          }}
        >
          <section
            aria-labelledby="knowledge-search-title"
            aria-modal="true"
            className="knowledge-search-dialog"
            role="dialog"
          >
            <header className="knowledge-search-header">
              <div>
                <span className="eyebrow">個人知識庫</span>
                <h2 id="knowledge-search-title">搜尋知識</h2>
              </div>
              <button
                aria-label="關閉知識搜尋"
                className="icon-button"
                onClick={() => setKnowledgeSearchOpen(false)}
                type="button"
              >
                <X size={17} />
              </button>
            </header>
            <p className="knowledge-search-description">
              搜尋已上傳文件中的內容，只會顯示你帳號的索引結果。
            </p>
            <form className="knowledge-search-form" onSubmit={handleKnowledgeSearch}>
              <Search aria-hidden="true" size={17} />
              <input
                aria-label="搜尋文件內容"
                disabled={isKnowledgeSearching}
                maxLength={8192}
                onChange={(event) => {
                  setKnowledgeQuery(event.target.value);
                  setHasSearchedKnowledge(false);
                  setKnowledgeResults([]);
                }}
                placeholder="輸入關鍵字或問題…"
                ref={knowledgeSearchInput}
                required
                value={knowledgeQuery}
              />
              <button disabled={isKnowledgeSearching || !knowledgeQuery.trim()} type="submit">
                {isKnowledgeSearching ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  "搜尋"
                )}
              </button>
            </form>
            {knowledgeSearchError && (
              <div className="error-banner knowledge-search-error" role="alert">
                {knowledgeSearchError}
              </div>
            )}
            <div aria-live="polite" className="knowledge-search-results">
              {isKnowledgeSearching ? (
                <div className="knowledge-search-state">
                  <LoaderCircle className="spin" size={19} />
                  正在搜尋你的文件…
                </div>
              ) : knowledgeResults.length > 0 ? (
                <>
                  <div className="knowledge-search-result-count">
                    找到 {knowledgeResults.length} 個相關片段
                  </div>
                  {knowledgeResults.map((result) => {
                    const sourceName =
                      typeof result.metadata.source_name === "string"
                        ? result.metadata.source_name
                        : "文件";
                    const pageNumber = result.metadata.page_number;
                    return (
                      <article className="knowledge-search-result" key={result.chunk_id}>
                        <div className="knowledge-search-result-heading">
                          <FileText size={15} />
                          <strong>{sourceName}</strong>
                          {typeof pageNumber === "number" && (
                            <span>第 {pageNumber} 頁</span>
                          )}
                        </div>
                        <p>{result.content}</p>
                        <button
                          className="knowledge-search-continue"
                          onClick={() => continueSearchInChat(sourceName)}
                          type="button"
                        >
                          用這份文件繼續提問 <ArrowUpRight size={13} />
                        </button>
                      </article>
                    );
                  })}
                </>
              ) : hasSearchedKnowledge && knowledgeQuery && !knowledgeSearchError ? (
                <div className="knowledge-search-state">
                  沒有找到相關片段，試試其他關鍵字或確認文件已完成索引。
                </div>
              ) : documents.length === 0 ? (
                <div className="knowledge-search-state">
                  知識庫目前沒有文件。請先在右側「知識庫」分頁上傳並建立索引。
                </div>
              ) : (
                <div className="knowledge-search-state">
                  輸入文件中的關鍵字或問題，開始搜尋你的知識庫。
                </div>
              )}
            </div>
            <footer className="knowledge-search-footer">
              搜尋採用向量語意與 BM25 全文混合檢索
              <button onClick={() => setKnowledgeSearchOpen(false)} type="button">
                按 Esc 關閉
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}
