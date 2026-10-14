import React, { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  ChevronRight,
  Send,
  Shield,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { chatbotApi } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  ChatActionLink,
  ChatInitialConfigResponse,
  ChatMessageItem,
  ChatQueryResponse,
} from "@/types";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  isConfidentialBlock?: boolean;
  actionLinks?: ChatActionLink[];
  suggestions?: string[];
}

export function FloatingChatbot() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [roleContext, setRoleContext] = useState<string>("User");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasUnread, setHasUnread] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom of messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
      setHasUnread(false);
      inputRef.current?.focus();
    }
  }, [isOpen, messages]);

  // Load initial config when user logs in
  useEffect(() => {
    if (!user) return;

    let isMounted = true;
    chatbotApi
      .getConfig()
      .then((config: ChatInitialConfigResponse) => {
        if (!isMounted) return;
        setRoleContext(config.role_context);
        setSuggestions(config.suggestions);

        // Add welcome message if chat is empty
        setMessages((prev) => {
          if (prev.length > 0) return prev;
          return [
            {
              id: "welcome",
              role: "assistant",
              content: config.greeting,
              timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              suggestions: config.suggestions,
            },
          ];
        });
      })
      .catch((err) => {
        console.error("Failed to load chatbot config:", err);
      });

    return () => {
      isMounted = false;
    };
  }, [user]);

  // Handle closing with Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || input).trim();
    if (!query || isLoading) return;

    setInput("");
    const userMsgId = `user-${Date.now()}`;
    const nowTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    // Append user message immediately
    const updatedMessages: DisplayMessage[] = [
      ...messages,
      {
        id: userMsgId,
        role: "user",
        content: query,
        timestamp: nowTime,
      },
    ];
    setMessages(updatedMessages);
    setIsLoading(true);

    try {
      // Build lightweight history
      const historyPayload: ChatMessageItem[] = updatedMessages
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));

      const res: ChatQueryResponse = await chatbotApi.sendQuery(query, historyPayload);

      setRoleContext(res.role_context);
      if (res.suggestions && res.suggestions.length > 0) {
        setSuggestions(res.suggestions);
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `bot-${Date.now()}`,
          role: "assistant",
          content: res.reply,
          timestamp: res.timestamp || nowTime,
          isConfidentialBlock: res.is_confidential_block,
          actionLinks: res.action_links,
          suggestions: res.suggestions,
        },
      ]);

      if (!isOpen) {
        setHasUnread(true);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot-err-${Date.now()}`,
          role: "assistant",
          content:
            "⚠️ Unable to reach the campus assistant service right now. Please check your network connection and try again.",
          timestamp: nowTime,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearChat = () => {
    setMessages([
      {
        id: `reset-${Date.now()}`,
        role: "assistant",
        content: `Chat session refreshed. How can I assist you with your academics or duties today?`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        suggestions: suggestions,
      },
    ]);
  };

  // If user is not logged in, don't show floating chatbot
  if (!user) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 select-none">
      {/* Floating Trigger Button */}
      <AnimatePresence>
        {!isOpen && (
          <motion.button
            key="chat-fab"
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
            onClick={() => setIsOpen(true)}
            className="group relative flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-tr from-brand-600 via-indigo-600 to-violet-600 text-white shadow-xl shadow-brand-500/25 transition-all focus:outline-none focus:ring-4 focus:ring-brand-500/30"
            aria-label="Open CampusBot Assistant"
            title="CampusHub Academic & Coordination Assistant"
          >
            {/* Pulsing ring indicator */}
            <span className="absolute -inset-1 -z-10 rounded-full bg-gradient-to-r from-brand-500 to-violet-500 opacity-40 blur-sm group-hover:opacity-75 transition-opacity duration-300 animate-pulse" />

            <Bot className="h-6 w-6 transition-transform duration-300 group-hover:rotate-6" />

            {/* Unread badge dot */}
            {hasUnread && (
              <span className="absolute top-0 right-0 flex h-3.5 w-3.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-amber-500 border-2 border-white" />
              </span>
            )}
          </motion.button>
        )}
      </AnimatePresence>

      {/* Floating Chat Drawer Window */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="chat-drawer"
            initial={{ opacity: 0, y: 30, scale: 0.94 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 30, scale: 0.94 }}
            transition={{ type: "spring", stiffness: 350, damping: 28 }}
            className="flex flex-col w-[92vw] sm:w-[420px] h-[580px] max-h-[85vh] rounded-3xl bg-surface/98 backdrop-blur-2xl border border-line shadow-2xl overflow-hidden text-ink"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3.5 border-b border-line bg-surface-muted/60">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-brand-600 to-violet-600 text-white shadow-sm">
                  <Bot className="h-5 w-5" />
                  <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-surface" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-sm tracking-tight text-ink truncate">CampusBot</span>
                    <Sparkles className="h-3 w-3 text-amber-500 shrink-0" />
                  </div>
                  <div className="flex items-center gap-1 text-[11px] text-ink-subtle truncate">
                    <span className="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-md bg-brand-500/10 text-brand-700 dark:text-brand-300 font-medium">
                      <Shield className="h-2.5 w-2.5 shrink-0" />
                      {roleContext}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={handleClearChat}
                  title="Clear conversation"
                  className="rounded-lg p-1.5 text-ink-subtle hover:text-ink hover:bg-surface-muted transition-colors"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  title="Minimize"
                  className="rounded-lg p-1.5 text-ink-subtle hover:text-ink hover:bg-surface-muted transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Role Guard Security Strip */}
            <div className="flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-500/10 border-b border-emerald-500/20 text-[11px] text-emerald-800 dark:text-emerald-300">
              <Shield className="h-3 w-3 shrink-0" />
              <span className="truncate">Role-Protected Access · Confidential Records Guard Active</span>
            </div>

            {/* Messages Scroll Area */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 text-sm scroll-smooth">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 leading-relaxed shadow-sm ${
                      msg.role === "user"
                        ? "bg-gradient-to-r from-brand-600 to-indigo-600 text-white rounded-tr-sm"
                        : msg.isConfidentialBlock
                        ? "bg-rose-50 dark:bg-rose-950/30 border border-rose-300 dark:border-rose-800 text-rose-950 dark:text-rose-100 rounded-tl-sm"
                        : "bg-surface-muted/80 text-ink border border-line/60 rounded-tl-sm"
                    }`}
                  >
                    {/* Confidential Block Alert Header */}
                    {msg.isConfidentialBlock && (
                      <div className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400 font-semibold mb-1 text-xs">
                        <ShieldAlert className="h-4 w-4 shrink-0" />
                        <span>Confidentiality Restriction</span>
                      </div>
                    )}

                    {/* Content Renderer */}
                    <div className="space-y-1.5 text-[13px] leading-relaxed break-words">
                      <MarkdownMessage content={msg.content} />
                    </div>

                    {/* Action Links (if any) */}
                    {msg.actionLinks && msg.actionLinks.length > 0 && (
                      <div className="mt-2.5 pt-2 border-t border-line/40 flex flex-wrap gap-1.5">
                        {msg.actionLinks.map((link) => (
                          <button
                            key={link.path}
                            type="button"
                            onClick={() => {
                              navigate(link.path);
                              setIsOpen(false);
                            }}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-brand-500/10 hover:bg-brand-500/20 text-brand-700 dark:text-brand-300 border border-brand-500/30 transition-all active:scale-95"
                          >
                            <span>{link.title}</span>
                            <ChevronRight className="h-3 w-3" />
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Timestamp */}
                    <div
                      className={`text-[10px] mt-1 ${
                        msg.role === "user" ? "text-white/70 text-right" : "text-ink-subtle"
                      }`}
                    >
                      {msg.timestamp}
                    </div>
                  </div>
                </div>
              ))}

              {/* Bot Typing Indicator */}
              {isLoading && (
                <div className="flex items-center gap-2 text-ink-subtle text-xs py-1">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-surface-muted border border-line">
                    <Bot className="h-3.5 w-3.5 text-brand-500 animate-pulse" />
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-brand-500 animate-bounce" />
                    <span className="h-1.5 w-1.5 rounded-full bg-brand-500 animate-bounce [animation-delay:0.2s]" />
                    <span className="h-1.5 w-1.5 rounded-full bg-brand-500 animate-bounce [animation-delay:0.4s]" />
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Quick Suggestion Chips */}
            {suggestions.length > 0 && !isLoading && (
              <div className="px-3.5 py-2 border-t border-line/40 bg-surface-muted/30">
                <div className="flex items-center gap-1 text-[11px] font-medium text-ink-subtle mb-1.5">
                  <Sparkles className="h-3 w-3 text-amber-500" />
                  <span>Suggested queries:</span>
                </div>
                <div className="flex gap-1.5 overflow-x-auto pb-1 no-scrollbar">
                  {suggestions.slice(0, 4).map((suggestion, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSendMessage(suggestion)}
                      className="shrink-0 text-left px-2.5 py-1 rounded-full text-[11px] bg-surface border border-line hover:border-brand-500/60 hover:bg-brand-500/5 text-ink-subtle hover:text-ink transition-all active:scale-95"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Input Form */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage();
              }}
              className="p-3 border-t border-line bg-surface"
            >
              <div className="flex items-center gap-1.5 rounded-2xl border border-line bg-surface-muted/50 px-3 py-1.5 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/20 transition-all">
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={`Ask CampusBot as ${roleContext}...`}
                  disabled={isLoading}
                  className="flex-1 bg-transparent text-xs text-ink placeholder:text-ink-subtle focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading}
                  className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm hover:bg-brand-700 disabled:opacity-30 disabled:pointer-events-none transition-all"
                  aria-label="Send message"
                >
                  <Send className="h-3.5 w-3.5" />
                </button>
              </div>
              <p className="text-[10px] text-ink-subtle text-center mt-1.5">
                CampusHub Academic Assistant · Confidential records strictly protected
              </p>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * Clean, lightweight Markdown message formatter that handles:
 * - Bold (**text**)
 * - Code (`code`)
 * - Bullet lists (- item)
 * - Tables (| a | b |)
 * - Headings (### Title)
 * - Blockquotes (> note)
 */
function MarkdownMessage({ content }: { content: string }) {
  const lines = content.split("\n");
  const renderedElements: React.ReactNode[] = [];
  let inTable = false;
  let tableRows: string[][] = [];

  const flushTable = () => {
    if (tableRows.length > 0) {
      const [headerRow, ...bodyRows] = tableRows;
      renderedElements.push(
        <div key={`table-${renderedElements.length}`} className="my-2 overflow-x-auto">
          <table className="w-full text-left text-xs border border-line rounded-lg overflow-hidden">
            {headerRow && (
              <thead className="bg-surface-muted border-b border-line font-medium text-ink">
                <tr>
                  {headerRow.map((cell, idx) => (
                    <th key={idx} className="px-2.5 py-1.5 border-r border-line last:border-r-0">
                      <FormatInline text={cell.trim()} />
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {bodyRows
                .filter((row) => !row.every((c) => c.trim().match(/^[:\s-]+$/)))
                .map((row, rIdx) => (
                  <tr key={rIdx} className="border-b border-line last:border-b-0 hover:bg-surface-muted/30">
                    {row.map((cell, cIdx) => (
                      <td key={cIdx} className="px-2.5 py-1 border-r border-line last:border-r-0">
                        <FormatInline text={cell.trim()} />
                      </td>
                    ))}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      );
      tableRows = [];
    }
    inTable = false;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Table line
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      inTable = true;
      const cells = line
        .trim()
        .slice(1, -1)
        .split("|");
      tableRows.push(cells);
      continue;
    } else if (inTable) {
      flushTable();
    }

    // Headings
    if (line.startsWith("### ")) {
      renderedElements.push(
        <h4 key={i} className="font-semibold text-ink text-sm mt-1.5 mb-0.5">
          <FormatInline text={line.slice(4)} />
        </h4>
      );
      continue;
    }
    if (line.startsWith("#### ")) {
      renderedElements.push(
        <h5 key={i} className="font-medium text-ink text-xs mt-1 mb-0.5 text-brand-700 dark:text-brand-300">
          <FormatInline text={line.slice(5)} />
        </h5>
      );
      continue;
    }

    // Bullet lists
    if (line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
      renderedElements.push(
        <div key={i} className="flex items-start gap-1.5 ml-1">
          <span className="text-brand-500 font-bold mt-0.5">•</span>
          <span className="flex-1">
            <FormatInline text={line.trim().slice(2)} />
          </span>
        </div>
      );
      continue;
    }

    // Blockquotes
    if (line.trim().startsWith("> ")) {
      renderedElements.push(
        <div
          key={i}
          className="my-1.5 pl-2.5 py-1 border-l-2 border-brand-500 bg-brand-500/5 text-xs text-ink-subtle rounded-r-md"
        >
          <FormatInline text={line.trim().slice(2)} />
        </div>
      );
      continue;
    }

    // Empty line
    if (!line.trim()) {
      renderedElements.push(<div key={i} className="h-1" />);
      continue;
    }

    // Standard paragraph line
    renderedElements.push(
      <p key={i}>
        <FormatInline text={line} />
      </p>
    );
  }

  if (inTable) {
    flushTable();
  }

  return <>{renderedElements}</>;
}

/** Format inline markdown: bold, code, highlights */
function FormatInline({ text }: { text: string }) {
  // Split on bold (`**text**`) and code (`` `code` ``)
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);

  return (
    <>
      {tokens.map((token, idx) => {
        if (token.startsWith("**") && token.endsWith("**")) {
          return (
            <strong key={idx} className="font-semibold text-ink">
              {token.slice(2, -2)}
            </strong>
          );
        }
        if (token.startsWith("`") && token.endsWith("`")) {
          return (
            <code
              key={idx}
              className="px-1 py-0.2 rounded bg-surface border border-line text-[11px] font-mono text-brand-600 dark:text-brand-300"
            >
              {token.slice(1, -1)}
            </code>
          );
        }
        return <React.Fragment key={idx}>{token}</React.Fragment>;
      })}
    </>
  );
}
