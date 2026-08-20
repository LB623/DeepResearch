import React, { useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import { WelcomeScreen } from "@/components/WelcomeScreen";
import {
  ActivityTimeline,
  type ProcessedEvent,
} from "@/components/ActivityTimeline";
import { ChatMessagesView } from "@/components/ChatMessagesView";
import "./capture.css";

type CaptureWindow = Window & {
  __CAPTURE_READY__?: boolean;
  __CAPTURE_ERROR__?: string;
};
type CapturePage = "search" | "workflow" | "report";

const BRAND_MARK_URL = "/research-mark.svg";

const SEARCH_QUERY =
  "分析虚构的 Orion-7 推理引擎：架构取舍、生态依赖与潜在风险";

const searchEvents: ProcessedEvent[] = [
  {
    title: "生成计划",
    data: "将 Orion-7 主题拆分为架构、运行时、生态与风险 4 个研究面。",
  },
  {
    title: "Research Query · 01",
    data: "Orion-7 speculative scheduler memory topology",
  },
  {
    title: "Research Query · 02",
    data: "Orion-7 runtime portability ecosystem constraints",
  },
  {
    title: "Research Sources",
    data: "已汇集 28 条虚构资料：Northstar Labs Docs、Vector Systems Blog、Open Compute Notes。",
  },
];

const workflowEvents: ProcessedEvent[] = [
  {
    title: "生成计划",
    data: "确认研究边界与证据标准；建立架构、生态、风险三条主线。",
  },
  {
    title: "Generating Search Queries",
    data: "并行生成 6 条 Orion-7 虚构检索分支。",
  },
  {
    title: "Research Sources",
    data: "读取 28 条虚构资料，并保留来源标签与证据片段。",
  },
  {
    title: "Reflection & Analysis",
    data: "识别 3 处证据缺口；回查运行时兼容性与部署成本。",
  },
  {
    title: "Finalizing Report",
    data: "组织对比表、结论与引用，完成结构化研究报告。",
  },
];

const reportMarkdown = `# Orion-7 推理引擎：架构取舍与生态风险

> 演示说明：以下实体、资料与结论全部为虚构数据，仅用于展示 DeepResearch 的分析与引用布局。

## 核心结论

Orion-7 以分层调度降低长上下文推理的峰值显存，但跨运行时适配仍是主要工程风险。现有虚构资料共同指向：吞吐收益依赖批处理形态，不能脱离部署约束单独评价。

## 证据对比

| 维度 | 观察 | 工程取舍 | 证据状态 |
| --- | --- | --- | --- |
| 调度 | 分层队列减少空转 | 延迟对负载分布敏感 | 3 条资料交叉印证 |
| 内存 | 分块缓存压低峰值 | 增加运行时复杂度 | 2 条资料支持 |
| 生态 | 提供两类适配接口 | 插件兼容仍需验证 | 存在 1 处证据缺口 |

## 引用

[Northstar Labs Docs](https://northstar.example.invalid/orion-7) · [Vector Systems Blog](https://vector.example.invalid/runtime) · [Open Compute Notes](https://compute.example.invalid/ecosystem)
`;

const reportMessages: React.ComponentProps<
  typeof ChatMessagesView
>["messages"] = [
  {
    id: "demo-orion-7-report",
    type: "ai",
    content: reportMarkdown,
  },
];

const Header: React.FC<{ section: string }> = ({ section }) => (
  <header className="capture-header">
    <div className="capture-brand">
      <img
        className="capture-brand-mark"
        src={BRAND_MARK_URL}
        alt=""
        width="32"
        height="32"
      />
      <div>
        <p className="capture-brand-name">DeepResearch</p>
        <p className="capture-brand-subtitle">深度研究工作台</p>
      </div>
    </div>
    <div className="capture-meta">
      <span>{section}</span>
      <span className="capture-meta-pill">
        <span className="capture-meta-dot" /> local fixture · network isolated
      </span>
    </div>
  </header>
);

const SearchPage: React.FC = () => (
  <main
    className="capture-page"
    data-page="search"
    data-fixture="fictional-orion-7"
  >
    <Header section="AI SEARCH" />
    <div className="capture-content search-grid">
      <section className="search-welcome" data-capture="search-welcome">
        <WelcomeScreen
          handleSubmit={() => undefined}
          onCancel={() => undefined}
          isLoading={false}
        />
      </section>
      <aside className="search-evidence" data-capture="search-evidence">
        <p className="eyebrow">evidence-first research</p>
        <h2 className="panel-title">查询拆解后，证据持续汇入</h2>
        <p className="panel-copy">
          保留检索分支、来源标签和过程记录，让结论可以回到证据。
        </p>
        <ActivityTimeline
          processedEvents={searchEvents}
          isLoading={false}
          title="Orion-7 · AI 搜索"
        />
        <span className="demo-label">DEMO DATA · FICTIONAL</span>
      </aside>
    </div>
  </main>
);

const WorkflowPage: React.FC = () => (
  <main
    className="capture-page"
    data-page="workflow"
    data-fixture="fictional-orion-7"
  >
    <Header section="AUTOMATED WORKFLOW" />
    <div className="capture-content workflow-stage">
      <section className="workflow-intro">
        <p className="eyebrow">observable by design</p>
        <h1 className="panel-title">研究过程，持续可见</h1>
        <p className="panel-copy">
          从计划、检索与证据反思，到分析写作和引用整理，多阶段任务自动推进。
        </p>
        <span className="demo-label">DEMO DATA · FICTIONAL</span>
      </section>
      <section className="workflow-panel" data-capture="workflow-timeline">
        <ActivityTimeline
          processedEvents={workflowEvents}
          isLoading={false}
          title="Orion-7 研究工作流"
        />
      </section>
    </div>
  </main>
);

const ReportPage: React.FC = () => {
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  return (
    <main
      className="capture-page"
      data-page="report"
      data-fixture="fictional-orion-7"
    >
      <Header section="STRUCTURED ANALYSIS" />
      <div className="capture-content report-stage">
        <section className="report-panel" data-capture="report-view">
          <span className="demo-label report-demo-label">
            DEMO DATA · FICTIONAL
          </span>
          <ChatMessagesView
            messages={reportMessages}
            isLoading={false}
            scrollAreaRef={scrollAreaRef}
            onSubmit={() => undefined}
            onCancel={() => undefined}
            liveActivityEvents={[]}
            historicalActivities={{}}
          />
        </section>
      </div>
    </main>
  );
};

const selectedPage = (): CapturePage => {
  const candidate = new URLSearchParams(window.location.search).get("page");
  return candidate === "workflow" || candidate === "report"
    ? candidate
    : "search";
};

const annotateCaptureRegions = (page: CapturePage) => {
  if (page === "workflow") {
    const events = document.querySelectorAll(
      '[data-capture="workflow-timeline"] ol > li',
    );
    if (events.length !== workflowEvents.length) {
      throw new Error(
        `Expected ${workflowEvents.length} workflow events, found ${events.length}`,
      );
    }
    events.forEach((event, index) => {
      event.setAttribute("data-capture", `workflow-event${index + 1}`);
    });
  }

  if (page === "report") {
    const documents = document.querySelectorAll(
      '[data-capture="report-view"] article.report-markdown',
    );
    if (documents.length !== 1) {
      throw new Error(`Expected one report document, found ${documents.length}`);
    }
    const bubble = documents[0];
    bubble?.setAttribute("data-capture", "report-document");
    const tables = bubble.querySelectorAll("table");
    if (tables.length !== 1) {
      throw new Error(`Expected one report table, found ${tables.length}`);
    }
    tables[0].setAttribute("data-capture", "report-table");

    const referencesHeading = [...bubble.querySelectorAll("h2")].find(
      (heading) => heading.textContent?.trim() === "引用",
    );
    if (!referencesHeading || !referencesHeading.nextElementSibling) {
      throw new Error("Expected report references heading and content");
    }
    referencesHeading?.setAttribute("data-capture", "report-references-heading");
    referencesHeading?.nextElementSibling?.setAttribute(
      "data-capture",
      "report-references-content",
    );
  }
};

const App: React.FC = () => {
  const page = selectedPage();

  useEffect(() => {
    const ready = window as CaptureWindow;
    ready.__CAPTURE_READY__ = false;
    ready.__CAPTURE_ERROR__ = undefined;
    let secondFrame = 0;
    const firstFrame = requestAnimationFrame(() => {
      secondFrame = requestAnimationFrame(() => {
        try {
          annotateCaptureRegions(page);
          ready.__CAPTURE_READY__ = true;
        } catch (error) {
          ready.__CAPTURE_ERROR__ =
            error instanceof Error ? error.message : String(error);
        }
      });
    });
    return () => {
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
    };
  }, [page]);

  if (page === "workflow") return <WorkflowPage />;
  if (page === "report") return <ReportPage />;
  return <SearchPage />;
};

createRoot(document.getElementById("root")!).render(<App />);

export { SEARCH_QUERY };
