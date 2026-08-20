import type React from "react";
import { useRef, useState } from "react";
import type { Message } from "@langchain/langgraph-sdk";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Check,
  Copy,
  FileText,
  LoaderCircle,
  Play,
} from "lucide-react";

import {
  ActivityTimeline,
  type ProcessedEvent,
} from "@/components/ActivityTimeline";
import { InputForm, type InputFormHandle } from "@/components/InputForm";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

const mdComponents: Components = {
  h1: ({ className, children, ...props }) => (
    <h1
      className={cn(
        "mb-6 mt-2 text-3xl font-semibold leading-[1.15] tracking-[-0.045em] text-foreground md:text-[2.25rem]",
        className,
      )}
      {...props}
    >
      {children}
    </h1>
  ),
  h2: ({ className, children, ...props }) => (
    <h2
      className={cn(
        "mb-3 mt-10 border-t border-border pt-8 text-xl font-semibold tracking-[-0.03em] text-foreground first:mt-0 first:border-0 first:pt-0 md:text-2xl",
        className,
      )}
      {...props}
    >
      {children}
    </h2>
  ),
  h3: ({ className, children, ...props }) => (
    <h3
      className={cn(
        "mb-2 mt-7 text-base font-semibold tracking-[-0.015em] text-foreground md:text-lg",
        className,
      )}
      {...props}
    >
      {children}
    </h3>
  ),
  p: ({ className, children, ...props }) => (
    <p
      className={cn(
        "mb-5 text-[0.96rem] leading-7 text-foreground/88 md:text-base md:leading-8",
        className,
      )}
      {...props}
    >
      {children}
    </p>
  ),
  a: ({ className, children, href, ...props }) => {
    const isInternalPlaceholder = /^https?:\/\/search\.com\/id\//i.test(
      href || "",
    );
    const isCitation =
      typeof children === "string" && /^\d{1,3}$/.test(children);

    if (isInternalPlaceholder) {
      return (
        <span
          className={cn(
            "mx-1 inline-flex items-center gap-1 rounded-md border border-destructive/20 bg-destructive/[0.06] px-1.5 py-0.5 text-[0.76em] font-medium leading-none text-destructive",
            className,
          )}
          title="内部引用未能映射到真实来源，已禁止跳转"
          aria-label={`来源未解析：${String(children)}`}
          {...props}
        >
          <span>{children}</span>
          <span aria-hidden="true">· 来源未解析</span>
        </span>
      );
    }

    return (
      <a
        className={cn(
          isCitation
            ? "mx-1 inline-flex min-w-5 -translate-y-px items-center justify-center rounded-md border border-primary/20 bg-primary/[0.07] px-1.5 py-0.5 text-[0.72em] font-semibold leading-none text-primary no-underline transition-colors hover:bg-primary/[0.13] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
            : "font-medium text-primary underline decoration-primary/35 underline-offset-[3px] transition-colors hover:decoration-primary focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
          className,
        )}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={isCitation ? `打开来源 ${children}` : undefined}
        {...props}
      >
        {children}
      </a>
    );
  },
  img: ({ className, alt, ...props }) => (
    <img
      className={cn(
        "my-5 max-h-[34rem] w-auto max-w-full rounded-xl border border-border bg-secondary/35 object-contain shadow-sm",
        className,
      )}
      alt={alt || "检索到的媒体证据"}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      {...props}
    />
  ),
  strong: ({ className, children, ...props }) => (
    <strong className={cn("font-semibold text-foreground", className)} {...props}>
      {children}
    </strong>
  ),
  ul: ({ className, children, ...props }) => (
    <ul
      className={cn(
        "mb-5 ml-1 list-disc space-y-2 pl-5 marker:text-primary",
        className,
      )}
      {...props}
    >
      {children}
    </ul>
  ),
  ol: ({ className, children, ...props }) => (
    <ol
      className={cn(
        "mb-5 ml-1 list-decimal space-y-2 pl-5 marker:font-mono marker:text-xs marker:text-primary",
        className,
      )}
      {...props}
    >
      {children}
    </ol>
  ),
  li: ({ className, children, ...props }) => (
    <li
      className={cn("pl-1 text-[0.96rem] leading-7 text-foreground/88", className)}
      {...props}
    >
      {children}
    </li>
  ),
  blockquote: ({ className, children, ...props }) => (
    <blockquote
      className={cn(
        "my-7 border-l-2 border-primary bg-primary/[0.045] py-3 pl-5 pr-4 text-sm text-foreground/75 [&>p:last-child]:mb-0",
        className,
      )}
      {...props}
    >
      {children}
    </blockquote>
  ),
  code: ({ className, children, ...props }) => (
    <code
      className={cn(
        "rounded-md bg-secondary px-1.5 py-0.5 font-mono text-[0.82em] text-foreground",
        className,
      )}
      {...props}
    >
      {children}
    </code>
  ),
  pre: ({ className, children, ...props }) => (
    <pre
      className={cn(
        "my-6 overflow-x-auto rounded-xl border border-border bg-[#111715] p-4 font-mono text-xs leading-6 text-[#dce5e1] shadow-inner [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-inherit",
        className,
      )}
      {...props}
    >
      {children}
    </pre>
  ),
  hr: ({ className, ...props }) => (
    <hr className={cn("my-9 border-border", className)} {...props} />
  ),
  table: ({ className, children, ...props }) => (
    <div className="my-7 overflow-x-auto rounded-xl border border-border">
      <table
        className={cn("w-full min-w-[36rem] border-collapse text-sm", className)}
        {...props}
      >
        {children}
      </table>
    </div>
  ),
  th: ({ className, children, ...props }) => (
    <th
      className={cn(
        "border-b border-r border-border bg-secondary/70 px-4 py-3 text-left text-xs font-semibold text-foreground last:border-r-0",
        className,
      )}
      {...props}
    >
      {children}
    </th>
  ),
  td: ({ className, children, ...props }) => (
    <td
      className={cn(
        "border-b border-r border-border px-4 py-3 align-top leading-6 text-foreground/80 last:border-r-0",
        className,
      )}
      {...props}
    >
      {children}
    </td>
  ),
};

const humanMdComponents: Components = {
  p: ({ className, children, ...props }) => (
    <p className={cn("m-0 text-sm leading-6 text-foreground", className)} {...props}>
      {children}
    </p>
  ),
  a: mdComponents.a,
  code: mdComponents.code,
};

function messageText(message: Message): string {
  return typeof message.content === "string"
    ? message.content
    : JSON.stringify(message.content);
}

interface HumanMessageBubbleProps {
  message: Message;
}

function HumanMessageBubble({ message }: HumanMessageBubbleProps) {
  return (
    <div className="ml-auto max-w-[92%] md:max-w-[74%]">
      <p className="mb-2 text-right text-xs text-muted-foreground">
        你的问题
      </p>
      <div className="rounded-2xl rounded-tr-md border border-border bg-secondary/75 px-4 py-3.5 md:px-5">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={humanMdComponents}>
          {messageText(message)}
        </ReactMarkdown>
      </div>
    </div>
  );
}

interface AiMessageBubbleProps {
  message: Message;
  historicalActivity: ProcessedEvent[] | undefined;
  liveActivity: ProcessedEvent[] | undefined;
  isLastMessage: boolean;
  isOverallLoading: boolean;
  handleCopy: (text: string, messageId: string) => void;
  copiedMessageId: string | null;
  onStartResearch?: () => void;
  researchStarted?: boolean;
  showStartResearchButton?: boolean;
}

function AiMessageBubble({
  message,
  historicalActivity,
  liveActivity,
  isLastMessage,
  isOverallLoading,
  handleCopy,
  copiedMessageId,
  onStartResearch,
  researchStarted,
  showStartResearchButton,
}: AiMessageBubbleProps) {
  const activityForThisBubble =
    isLastMessage && isOverallLoading ? liveActivity : historicalActivity;
  const isLiveActivityForThisBubble = isLastMessage && isOverallLoading;
  const hasResearchPlan = (activityForThisBubble || []).some(
    (event) => event.title === "生成计划",
  );
  const content = messageText(message);

  return (
    <section className="grid min-w-0 gap-4 md:grid-cols-[5.5rem_minmax(0,1fr)] md:gap-7">
      <div className="pt-1">
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
          {hasResearchPlan ? "研究计划" : "研究报告"}
        </p>
      </div>

      <div className="min-w-0">
        {hasResearchPlan && onStartResearch ? (
          <div className="rounded-2xl border border-border bg-card p-5 shadow-[0_20px_60px_-48px_rgba(15,28,24,0.55)] md:p-7">
            <div className="mb-5 flex size-9 items-center justify-center rounded-xl bg-primary/8 text-primary">
              <FileText className="size-4" strokeWidth={1.7} />
            </div>
            <div className="report-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                {content}
              </ReactMarkdown>
            </div>
            {showStartResearchButton && (
              <Button
                aria-label="按此计划开始研究"
                className="mt-2 h-10 rounded-lg bg-foreground px-5 text-sm text-background shadow-none hover:bg-foreground/88 active:translate-y-px disabled:bg-muted disabled:text-muted-foreground"
                onClick={onStartResearch}
                disabled={researchStarted}
              >
                {researchStarted ? (
                  <LoaderCircle className="size-4 animate-spin" strokeWidth={1.8} />
                ) : (
                  <Play className="size-3.5 fill-current" strokeWidth={1.7} />
                )}
                {researchStarted ? "研究已启动" : "按此计划开始"}
              </Button>
            )}
          </div>
        ) : (
          <>
            {activityForThisBubble && activityForThisBubble.length > 0 && (
              <ActivityTimeline
                processedEvents={activityForThisBubble}
                isLoading={isLiveActivityForThisBubble}
                title="研究路径"
              />
            )}

            {content.length > 0 && (
              <article className="report-markdown mt-7 min-w-0">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                  {content}
                </ReactMarkdown>
              </article>
            )}

            {content.length > 0 && (
              <div className="mt-6 flex justify-end border-t border-border pt-4">
                <Button
                  variant="ghost"
                  className="h-8 cursor-pointer rounded-lg px-2.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground active:translate-y-px"
                  onClick={() => handleCopy(content, message.id!)}
                >
                  {copiedMessageId === message.id ? (
                    <Check className="size-3.5 text-primary" strokeWidth={1.9} />
                  ) : (
                    <Copy className="size-3.5" strokeWidth={1.7} />
                  )}
                  {copiedMessageId === message.id ? "已复制" : "复制报告"}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}

interface ChatMessagesViewProps {
  messages: Message[];
  isLoading: boolean;
  scrollAreaRef: React.RefObject<HTMLDivElement | null>;
  onSubmit: (inputValue: string, effort: string, model: string) => void;
  onCancel: () => void;
  liveActivityEvents: ProcessedEvent[];
  historicalActivities: Record<string, ProcessedEvent[]>;
}

export function ChatMessagesView({
  messages,
  isLoading,
  scrollAreaRef,
  onSubmit,
  onCancel,
  liveActivityEvents,
  historicalActivities,
}: ChatMessagesViewProps) {
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const [researchStarted, setResearchStarted] = useState(false);
  const inputFormRef = useRef<InputFormHandle>(null);

  const handleCopy = async (text: string, messageId: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedMessageId(messageId);
      window.setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (copyError) {
      console.error("Failed to copy report", copyError);
    }
  };

  const handleStartResearch = () => {
    if (!inputFormRef.current) return;
    inputFormRef.current.submitInput("需求确认");
    setResearchStarted(true);
  };

  let lastResearchProposalIndex = -1;
  messages.forEach((message, index) => {
    if (message.type === "human") return;
    const isLast = index === messages.length - 1;
    const activity =
      isLast && isLoading
        ? liveActivityEvents
        : historicalActivities[message.id!];
    if ((activity || []).some((event) => event.title === "生成计划")) {
      lastResearchProposalIndex = index;
    }
  });

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ScrollArea className="min-h-0 flex-1" ref={scrollAreaRef}>
        <div className="mx-auto w-full max-w-[1040px] space-y-12 px-5 pb-16 pt-10 md:space-y-16 md:px-8 md:pb-20 md:pt-14">
          <div className="flex items-end justify-between border-b border-border pb-4">
            <div>
              <p className="text-xs text-primary">当前研究</p>
              <p className="mt-2 text-sm font-medium tracking-[-0.01em]">研究记录</p>
            </div>
            <p className="text-xs text-muted-foreground">
              {messages.length} 条消息
            </p>
          </div>

          {messages.map((message, index) => {
            const isLast = index === messages.length - 1;
            const activity =
              isLast && isLoading
                ? liveActivityEvents
                : historicalActivities[message.id!];
            const hasResearchPlan =
              message.type !== "human" &&
              (activity || []).some((event) => event.title === "生成计划");
            const showStartResearch =
              hasResearchPlan && index === lastResearchProposalIndex;

            return (
              <div key={message.id || `message-${index}`} className="animate-enter">
                {message.type === "human" ? (
                  <HumanMessageBubble message={message} />
                ) : (
                  <AiMessageBubble
                    message={message}
                    historicalActivity={historicalActivities[message.id!]}
                    liveActivity={liveActivityEvents}
                    isLastMessage={isLast}
                    isOverallLoading={isLoading}
                    handleCopy={handleCopy}
                    copiedMessageId={copiedMessageId}
                    onStartResearch={
                      showStartResearch ? handleStartResearch : undefined
                    }
                    researchStarted={researchStarted}
                    showStartResearchButton={showStartResearch}
                  />
                )}
              </div>
            );
          })}

          {isLoading &&
            (messages.length === 0 ||
              messages[messages.length - 1].type === "human") && (
              <section className="animate-enter grid gap-4 md:grid-cols-[5.5rem_minmax(0,1fr)] md:gap-7">
                <p className="flex items-center gap-2 pt-1 text-xs text-muted-foreground">
                  <span className="size-1.5 animate-pulse rounded-full bg-primary" />
                  正在研究
                </p>
                {liveActivityEvents.length > 0 ? (
                  <ActivityTimeline
                    processedEvents={liveActivityEvents}
                    isLoading={true}
                    title="研究路径"
                  />
                ) : (
                  <div className="rounded-2xl border border-border bg-card p-5">
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                      <LoaderCircle className="size-4 animate-spin text-primary" strokeWidth={1.7} />
                      正在拆解问题并准备检索…
                    </div>
                    <div className="mt-5 space-y-2.5" aria-hidden="true">
                      <div className="h-2.5 w-5/6 animate-pulse rounded-full bg-muted" />
                      <div className="h-2.5 w-2/3 animate-pulse rounded-full bg-muted" />
                    </div>
                  </div>
                )}
              </section>
            )}
        </div>
      </ScrollArea>

      <div className="composer-dock shrink-0 border-t border-border/80 bg-background/92 px-4 py-3 md:px-8 md:py-4">
        <InputForm
          ref={inputFormRef}
          onSubmit={onSubmit}
          isLoading={isLoading}
          onCancel={onCancel}
          hasHistory={messages.length > 0}
        />
      </div>
    </div>
  );
}
