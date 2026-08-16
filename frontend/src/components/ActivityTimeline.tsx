import { useEffect, useId, useState } from "react";
import {
  Activity,
  Brain,
  Check,
  ChevronDown,
  CircleDot,
  FilePenLine,
  Info,
  LoaderCircle,
  Search,
  TextSearch,
} from "lucide-react";

export interface ProcessedEvent {
  title: string;
  data: unknown;
}

interface ActivityTimelineProps {
  processedEvents: ProcessedEvent[];
  isLoading: boolean;
  title?: string;
}

function eventIcon(title: string, isCurrent: boolean) {
  const normalized = title.toLowerCase();
  const iconClassName = "size-3.5";

  if (isCurrent) {
    return <LoaderCircle className={`${iconClassName} animate-spin`} strokeWidth={1.8} />;
  }
  if (normalized.includes("查询") || normalized.includes("query")) {
    return <TextSearch className={iconClassName} strokeWidth={1.7} />;
  }
  if (normalized.includes("反思") || normalized.includes("reflection")) {
    return <Brain className={iconClassName} strokeWidth={1.7} />;
  }
  if (normalized.includes("研究") || normalized.includes("research")) {
    return <Search className={iconClassName} strokeWidth={1.7} />;
  }
  if (normalized.includes("答案") || normalized.includes("final")) {
    return <FilePenLine className={iconClassName} strokeWidth={1.7} />;
  }
  if (normalized.includes("计划") || normalized.includes("plan")) {
    return <CircleDot className={iconClassName} strokeWidth={1.7} />;
  }
  return <Activity className={iconClassName} strokeWidth={1.7} />;
}

function eventDescription(data: unknown) {
  if (typeof data === "string") return data;
  if (Array.isArray(data)) return data.join("，");
  return JSON.stringify(data);
}

export function ActivityTimeline({
  processedEvents,
  isLoading,
  title = "研究路径",
}: ActivityTimelineProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const panelId = `${useId()}-panel`;

  useEffect(() => {
    if (!isLoading && processedEvents.length > 0) {
      setIsCollapsed(true);
    }
    if (processedEvents.some((event) => event.title === "生成计划")) {
      setIsCollapsed(false);
    }
  }, [isLoading, processedEvents]);

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <button
        type="button"
        aria-expanded={!isCollapsed}
        aria-controls={panelId}
        className="flex w-full cursor-pointer items-center justify-between gap-4 px-4 py-3.5 text-left transition-colors hover:bg-secondary/55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/35 md:px-5"
        onClick={() => setIsCollapsed((current) => !current)}
      >
        <span className="flex min-w-0 items-center gap-3">
          <span
            className={`flex size-7 shrink-0 items-center justify-center rounded-lg ${
              isLoading
                ? "bg-primary/10 text-primary"
                : "bg-secondary text-muted-foreground"
            }`}
          >
            {isLoading ? (
              <LoaderCircle className="size-3.5 animate-spin" strokeWidth={1.8} />
            ) : (
              <Check className="size-3.5" strokeWidth={1.9} />
            )}
          </span>
          <span>
            <span className="block text-xs font-semibold text-foreground">{title}</span>
            <span className="mt-0.5 block text-[0.68rem] text-muted-foreground">
              {isLoading
                ? `正在执行 · ${processedEvents.length} 个阶段`
                : `已完成 · ${processedEvents.length} 个阶段`}
            </span>
          </span>
        </span>
        <ChevronDown
          className={`size-4 shrink-0 text-muted-foreground transition-transform duration-200 ${
            isCollapsed ? "" : "rotate-180"
          }`}
          strokeWidth={1.7}
        />
      </button>

      {!isCollapsed && (
        <div id={panelId} className="border-t border-border px-4 py-5 md:px-5">
          {processedEvents.length > 0 ? (
            <ol className="space-y-0">
              {processedEvents.map((event, index) => {
                const isCurrent = isLoading && index === processedEvents.length - 1;
                return (
                  <li key={`${event.title}-${index}`} className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3 pb-5 last:pb-0">
                    {index < processedEvents.length - 1 && (
                      <span className="absolute bottom-0 left-[0.85rem] top-7 w-px bg-border" />
                    )}
                    <span
                      className={`relative z-10 flex size-7 items-center justify-center rounded-lg border ${
                        isCurrent
                          ? "border-primary/25 bg-primary/8 text-primary"
                          : "border-border bg-background text-muted-foreground"
                      }`}
                    >
                      {eventIcon(event.title, isCurrent)}
                    </span>
                    <div className="min-w-0 pt-0.5">
                      <p className="text-xs font-semibold leading-5 text-foreground">
                        {event.title}
                      </p>
                      <p className="mt-0.5 whitespace-pre-line break-words text-[0.7rem] leading-5 text-muted-foreground">
                        {eventDescription(event.data)}
                      </p>
                    </div>
                  </li>
                );
              })}
              {isLoading && (
                <li className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3 pt-5">
                  <span className="absolute left-[0.85rem] top-0 h-5 w-px bg-border" />
                  <span className="relative z-10 flex size-7 items-center justify-center rounded-lg border border-primary/25 bg-primary/8 text-primary">
                    <LoaderCircle className="size-3.5 animate-spin" strokeWidth={1.8} />
                  </span>
                  <p className="pt-1 text-xs text-muted-foreground">继续检索与综合…</p>
                </li>
              )}
            </ol>
          ) : !isLoading ? (
            <div className="flex items-center gap-3 rounded-xl bg-secondary/55 p-4 text-xs text-muted-foreground">
              <Info className="size-4 shrink-0" strokeWidth={1.7} />
              研究开始后，这里会记录查询、来源与综合过程。
            </div>
          ) : (
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin text-primary" strokeWidth={1.8} />
              正在准备研究路径…
            </div>
          )}
        </div>
      )}
    </section>
  );
}
