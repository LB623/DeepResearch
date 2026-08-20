import { useStream } from "@langchain/langgraph-sdk/react";
import type { Message } from "@langchain/langgraph-sdk";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ProcessedEvent } from "@/components/ActivityTimeline";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import { Button } from "@/components/ui/button";
import { createLocalLangGraphClient } from "@/lib/langgraphClient";
import { AlertCircle } from "lucide-react";

const ChatMessagesView = lazy(() =>
  import("@/components/ChatMessagesView").then((module) => ({
    default: module.ChatMessagesView,
  })),
);

interface StreamSource {
  label?: string;
}

interface StreamUpdateEvent {
  generate_plan?: { plan?: string };
  generate_query?: { search_query?: string[] };
  web_research?: { sources_gathered?: StreamSource[] };
  reflection?: unknown;
  finalize_answer?: unknown;
}

export default function App() {
  const brandIconUrl = `${import.meta.env.BASE_URL}research-mark.svg`;
  const [processedEventsTimeline, setProcessedEventsTimeline] = useState<
    ProcessedEvent[]
  >([]);
  const [historicalActivities, setHistoricalActivities] = useState<
    Record<string, ProcessedEvent[]>
  >({});
  const [awaitingPlanConfirmation, setAwaitingPlanConfirmation] = useState("unconfirmed");
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const hasFinalizeEventOccurredRef = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [savedEffort, setSavedEffort] = useState("medium");
  const [savedModel, setSavedModel] = useState("qwen-plus-latest");
  const langGraphClient = useMemo(
    () =>
      createLocalLangGraphClient(
        import.meta.env.DEV ? "http://localhost:2024" : window.location.origin,
      ),
    [],
  );
  const thread = useStream<{
    messages: Message[];
    initial_search_query_count: number;
    max_research_loops: number;
    reasoning_model: string;
    plan_status: string;
  }>({
    client: langGraphClient,
    assistantId: "agent",
    messagesKey: "messages",
    onUpdateEvent: (event: StreamUpdateEvent) => {
      let processedEvent: ProcessedEvent | null = null;
      if (event.generate_plan){
        processedEvent = {
          title: "生成计划",
          data: event.generate_plan?.plan || "暂未生成研究计划"
        }
        setAwaitingPlanConfirmation("confirmed");
        hasFinalizeEventOccurredRef.current = true;
      }
      else if (event.generate_query) {
        processedEvent = {
          title: "生成搜索查询",
          data: event.generate_query?.search_query?.join(", ") || "",
        };
      } else if (event.web_research) {
        const sources = event.web_research.sources_gathered || [];
        const numSources = sources.length;
        const uniqueLabels = [
          ...new Set(
            sources
              .map((source) => source.label)
              .filter((label): label is string => Boolean(label)),
          ),
        ];
        const exampleLabels = uniqueLabels.slice(0, 3).join(", ");
        processedEvent = {
          title: "网络研究",
          data: `已汇集 ${numSources} 个来源${
            exampleLabels ? `，涉及：${exampleLabels}` : ""
          }。`,
        };
      } else if (event.reflection) {
        processedEvent = {
          title: "反思和分析",
          data: "正在比较检索结果并核对分歧",
        };
      } else if (event.finalize_answer) {
        processedEvent = {
          title: "最终确定答案",
          data: "正在整理证据并生成最终报告",
        };
        hasFinalizeEventOccurredRef.current = true;
      }
      if (processedEvent) {
        setProcessedEventsTimeline((prevEvents) => [
          ...prevEvents,
          processedEvent!,
        ]);
      }
    },
    onError: (streamError: unknown) => {
      setError(
        streamError instanceof Error ? streamError.message : "研究任务暂时不可用",
      );
    },
  });

  useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollViewport = scrollAreaRef.current.querySelector(
        "[data-radix-scroll-area-viewport]"
      );
      if (scrollViewport) {
        scrollViewport.scrollTop = scrollViewport.scrollHeight;
      }
    }
  }, [thread.messages]);

  useEffect(() => {
    if (
      hasFinalizeEventOccurredRef.current &&
      !thread.isLoading &&
      thread.messages.length > 0
    ) {
      const lastMessage = thread.messages[thread.messages.length - 1];
      if (lastMessage && lastMessage.type === "ai" && lastMessage.id) {
        setHistoricalActivities((prev) => ({
          ...prev,
          [lastMessage.id!]: [...processedEventsTimeline],
        }));
      }
      hasFinalizeEventOccurredRef.current = false;
    }
  }, [thread.messages, thread.isLoading, processedEventsTimeline]);

  const handleSubmit = useCallback(
    (submittedInputValue: string, effort: string, model: string) => {
      if (!submittedInputValue.trim()) return;
      setProcessedEventsTimeline([]);
      hasFinalizeEventOccurredRef.current = false;

      // 如果是第一次提交（没有历史消息），保存effort和模型值
      if (thread.messages.length === 0) {
        setSavedEffort(effort);
        setSavedModel(model);
      }

      // 使用保存的值或传入的值
      const currentEffort = thread.messages.length === 0 ? effort : savedEffort;
      const currentModel = thread.messages.length === 0 ? model : savedModel;

      // convert effort to, initial_search_query_count and max_research_loops
      // low means max 1 loop and 1 query
      // medium means max 3 loops and 3 queries
      // high means max 10 loops and 5 queries
      let initial_search_query_count = 0;
      let max_research_loops = 0;
      switch (currentEffort) {
        case "low":
          initial_search_query_count = 1;
          max_research_loops = 1;
          break;
        case "medium":
          initial_search_query_count = 3;
          max_research_loops = 3;
          break;
        case "high":
          initial_search_query_count = 5;
          max_research_loops = 10;
          break;
      }

      const newMessages: Message[] = [
        ...(thread.messages || []),
        {
          type: "human",
          content: submittedInputValue,
          id: Date.now().toString(),
        },
      ];
      thread.submit(
        {
          messages: newMessages,
          initial_search_query_count: initial_search_query_count,
          max_research_loops: max_research_loops,
          reasoning_model: currentModel,
          plan_status: awaitingPlanConfirmation,
        },
        {
          // Kimi can have a long time-to-first-token. Keep the run alive when
          // the SDK replaces an idle SSE connection, then resume its events.
          onDisconnect: "continue",
          streamResumable: true,
        },
      );
    },
    [awaitingPlanConfirmation, thread, savedEffort, savedModel]
  );

  const handleCancel = useCallback(() => {
    thread.stop();
    setError(null);
  }, [thread]);

  return (
    <div className="app-shell flex h-dvh min-h-[36rem] flex-col overflow-hidden bg-background text-foreground antialiased">
      <header className="app-header shrink-0 border-b border-border/80 bg-background/90">
        <div className="mx-auto flex h-[4.25rem] w-full max-w-[1080px] items-center justify-between px-5 md:px-8">
          <div className="flex items-center gap-3" aria-label="DeepResearch">
            <img
              className="brand-mark"
              src={brandIconUrl}
              alt=""
              width="32"
              height="32"
            />
            <span className="text-[0.96rem] font-semibold tracking-[-0.025em]">
              DeepResearch
            </span>
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span
              className={`size-1.5 rounded-full ${
                error
                  ? "bg-destructive"
                  : thread.isLoading
                    ? "animate-pulse bg-primary"
                    : "bg-primary"
              }`}
              aria-hidden="true"
            />
            <span>{error ? "连接中断" : thread.isLoading ? "研究进行中" : "就绪"}</span>
          </div>
        </div>
      </header>

      <main className="min-h-0 w-full flex-1">
        {error ? (
          <div className="mx-auto flex h-full max-w-xl items-center justify-center px-6">
            <section className="w-full rounded-2xl border border-border bg-card p-7 shadow-[0_24px_70px_-42px_rgba(15,28,24,0.35)] md:p-9">
              <div className="mb-6 flex size-10 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
                <AlertCircle className="size-5" strokeWidth={1.7} />
              </div>
              <p className="mb-2 text-xs text-muted-foreground">服务状态</p>
              <h1 className="text-2xl font-semibold tracking-[-0.035em]">
                研究连接暂时中断
              </h1>
              <p className="mt-3 break-words text-sm leading-6 text-muted-foreground">
                {error}
              </p>
              <Button
                className="mt-7 rounded-lg bg-foreground px-5 text-background hover:bg-foreground/88 active:translate-y-px"
                onClick={() => setError(null)}
              >
                重试
              </Button>
            </section>
          </div>
        ) : thread.messages.length === 0 ? (
            <WelcomeScreen
              handleSubmit={handleSubmit}
              isLoading={thread.isLoading}
              onCancel={handleCancel}
            />
        ) : (
          <Suspense
            fallback={
              <div className="mx-auto flex h-full max-w-5xl items-center px-6">
                <div className="w-full space-y-4" aria-label="正在加载研究报告">
                  <div className="h-3 w-24 animate-pulse rounded-full bg-muted" />
                  <div className="h-8 w-2/3 animate-pulse rounded-lg bg-muted" />
                  <div className="h-3 w-full animate-pulse rounded-full bg-muted" />
                  <div className="h-3 w-5/6 animate-pulse rounded-full bg-muted" />
                </div>
              </div>
            }
          >
            <ChatMessagesView
              messages={thread.messages}
              isLoading={thread.isLoading}
              scrollAreaRef={scrollAreaRef}
              onSubmit={handleSubmit}
              onCancel={handleCancel}
              liveActivityEvents={processedEventsTimeline}
              historicalActivities={historicalActivities}
            />
          </Suspense>
        )}
      </main>
    </div>
  );
}
