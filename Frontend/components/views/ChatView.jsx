'use client';
import React, { useEffect, useRef, useState } from 'react';
import {
  Bot,
  Check,
  CircleHelp,
  Copy,
  Database,
  LoaderCircle,
  RotateCcw,
  Send,
  ShieldCheck,
  Sparkles,
  UserRound,
  X,
} from 'lucide-react';
import { api } from '../../lib/api';

const initialMessage = {
  id: 'welcome',
  role: 'assistant',
  content: "Hi, I'm your MediFlow operations assistant. Ask me about current medicine stock, batches and expiry, facility inventory, risks, forecasts, or how a transfer works.",
  suggestions: [
    'How much medicine stock is available?',
    'Which batches are closest to expiry?',
    'How does a safe stock transfer work?',
  ],
};

const providerLabels = {
  meko: 'MEKO memory',
  yugabyte_pgvector: 'YugabyteDB knowledge',
  local_sqlite: 'Local knowledge base',
};

export function ChatView({ activeFacility, compact = false, onClose }) {
  const [messages, setMessages] = useState([initialMessage]);
  const [question, setQuestion] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState('');
  const [copiedMessageId, setCopiedMessageId] = useState(null);
  const scrollContainer = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    scrollContainer.current?.scrollTo({
      top: scrollContainer.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages, isSending]);

  const submitQuestion = async (value = question) => {
    const text = value.trim();
    if (!text || isSending) return;

    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
    };
    const history = messages
      .filter((message) => message.id !== 'welcome')
      .slice(-6)
      .map(({ role, content }) => ({ role, content }));

    setMessages((current) => [...current, userMessage]);
    setQuestion('');
    setError('');
    setIsSending(true);

    try {
      const result = await api.askInventoryAssistant({
        question: text,
        facility_id: activeFacility?.id || null,
        history,
      });
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: result.answer,
          sources: result.sources || [],
          retrievalProvider: result.retrieval_provider,
          answerProvider: result.answer_provider,
          suggestions: result.suggestions || [],
        },
      ]);
    } catch (requestError) {
      setError(requestError.message || 'The assistant could not answer right now. Please try again.');
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  };

  const copyAnswer = async (message) => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessageId(message.id);
      window.setTimeout(() => setCopiedMessageId(null), 1600);
    } catch {
      setError('Could not copy the answer to your clipboard.');
    }
  };

  const clearConversation = () => {
    setMessages([initialMessage]);
    setQuestion('');
    setError('');
    inputRef.current?.focus();
  };

  const containerClass = compact
    ? 'flex h-full min-h-0 w-full max-w-none flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl'
    : 'mx-auto flex h-[calc(100vh-9.5rem)] min-h-[34rem] max-w-5xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm';

  return (
    <section className={containerClass}>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 sm:px-7">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-700 text-white shadow-sm shadow-emerald-900/10">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-slate-900">Ask MediFlow</h1>
            <p className="mt-0.5 text-xs text-slate-500">
              Inventory answers grounded in your operational data
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {activeFacility && (
            <span className="hidden max-w-52 truncate rounded-full bg-slate-50 px-3 py-1.5 text-[11px] font-medium text-slate-600 sm:inline-flex">
              {activeFacility.name}
            </span>
          )}
          <button
            type="button"
            onClick={clearConversation}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
            aria-label="Start a new chat"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">New chat</span>
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
              aria-label="Close assistant"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </header>

      <div ref={scrollContainer} className={`flex-1 space-y-6 overflow-y-auto bg-slate-50/60 px-4 py-6 ${compact ? 'sm:px-4' : 'sm:px-8'}`}>
        {messages.map((message) => {
          const isAssistant = message.role === 'assistant';
          return (
            <article key={message.id} className={`flex gap-3 ${isAssistant ? '' : 'flex-row-reverse'}`}>
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                isAssistant ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
              }`}>
                {isAssistant ? <Bot className="h-4 w-4" /> : <UserRound className="h-4 w-4" />}
              </div>
              <div className={`min-w-0 max-w-[88%] sm:max-w-[78%] ${isAssistant ? '' : 'text-right'}`}>
                <div className={`inline-block rounded-2xl px-4 py-3 text-left shadow-sm ${
                  isAssistant
                    ? 'rounded-tl-md border border-slate-200 bg-white text-slate-700'
                    : 'rounded-tr-md bg-emerald-800 text-white'
                }`}>
                  <p className="whitespace-pre-wrap text-[13px] leading-6">{message.content}</p>
                </div>

                {isAssistant && message.id !== 'welcome' && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-1 text-[10px] font-medium text-slate-500 ring-1 ring-slate-200">
                      <Database className="h-3 w-3" />
                      {providerLabels[message.retrievalProvider] || 'MediFlow context'}
                    </span>
                    {message.sources?.map((source, index) => (
                      <span
                        key={`${source.source}-${source.reference || source.title}-${index}`}
                        title={source.title}
                        className="max-w-52 truncate rounded-full bg-white px-2 py-1 text-[10px] text-slate-500 ring-1 ring-slate-200"
                      >
                        {source.title}
                      </span>
                    ))}
                    <button
                      type="button"
                      onClick={() => copyAnswer(message)}
                      className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] text-slate-400 transition hover:bg-white hover:text-slate-700"
                      aria-label="Copy answer"
                    >
                      {copiedMessageId === message.id
                        ? <Check className="h-3 w-3" />
                        : <Copy className="h-3 w-3" />}
                      {copiedMessageId === message.id ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                )}
                {isAssistant && message.suggestions?.length > 0 && (
                  <div className="mt-3 flex max-w-2xl flex-wrap gap-2">
                    {message.suggestions.slice(0, 3).map((suggestion) => (
                      <button
                        type="button"
                        key={suggestion}
                        onClick={() => submitQuestion(suggestion)}
                        disabled={isSending}
                        className="rounded-full border border-emerald-100 bg-white px-3 py-2 text-left text-[11px] leading-4 text-emerald-900 transition hover:border-emerald-300 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </article>
          );
        })}

        {isSending && (
          <div className="flex gap-3" role="status" aria-live="polite">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 text-emerald-800">
              <Bot className="h-4 w-4" />
            </div>
            <div className="flex items-center gap-2 rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 text-xs text-slate-500">
              <LoaderCircle className="h-4 w-4 animate-spin text-emerald-700" />
              Checking operational data and relevant context…
            </div>
          </div>
        )}

        {error && (
          <div className="ml-11 flex max-w-xl items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs leading-5 text-rose-800">
            <CircleHelp className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>

      <footer className="border-t border-slate-100 bg-white px-4 py-4 sm:px-7">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submitQuestion();
          }}
          className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm transition focus-within:border-emerald-400 focus-within:ring-4 focus-within:ring-emerald-50"
        >
          <label className="sr-only" htmlFor="assistant-question">Ask an inventory question</label>
          <textarea
            id="assistant-question"
            ref={inputRef}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submitQuestion();
              }
            }}
            maxLength={2000}
            rows={1}
            placeholder="Ask about stock, batches, expiry, facilities…"
            className="max-h-32 min-h-10 flex-1 resize-y border-0 bg-transparent px-3 py-2 text-[13px] text-slate-800 outline-none placeholder:text-slate-400 focus:ring-0"
          />
          <button
            type="submit"
            disabled={!question.trim() || isSending}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-800 text-white transition hover:bg-emerald-900 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
            aria-label="Send message"
          >
            {isSending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </form>
        <p className="mt-2 flex items-center justify-center gap-1.5 text-center text-[10px] text-slate-400">
          <ShieldCheck className="h-3 w-3" />
          Operational guidance only. Don’t include patient details; verify inventory before acting.
        </p>
      </footer>
    </section>
  );
}
