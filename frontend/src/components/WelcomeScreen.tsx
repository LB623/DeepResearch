import { useRef } from "react";
import {
  ArrowUpRight,
  ScanSearch,
  ScrollText,
  Search,
} from "lucide-react";

import { InputForm, type InputFormHandle } from "./InputForm";

interface WelcomeScreenProps {
  handleSubmit: (
    submittedInputValue: string,
    effort: string,
    model: string,
  ) => void;
  onCancel: () => void;
  isLoading: boolean;
}

const promptStarters = [
  {
    label: "方案比较",
    question: "比较两种方案的能力、成本与适用边界",
  },
  {
    label: "观点核查",
    question: "核查一个观点的证据、反例与主要争议",
  },
  {
    label: "进展梳理",
    question: "梳理一项技术近期的关键进展与影响",
  },
];

const researchSteps = [
  {
    title: "拆解问题",
    description: "明确范围与需要回答的判断",
    icon: Search,
  },
  {
    title: "核对证据",
    description: "比较来源，标记共识与分歧",
    icon: ScanSearch,
  },
  {
    title: "形成结论",
    description: "保留引用与可回查的依据",
    icon: ScrollText,
  },
];

export const WelcomeScreen: React.FC<WelcomeScreenProps> = ({
  handleSubmit,
  onCancel,
  isLoading,
}) => {
  const inputFormRef = useRef<InputFormHandle>(null);

  return (
    <div className="h-full overflow-y-auto">
      <section className="welcome-stage mx-auto flex min-h-full w-full max-w-[1080px] flex-col px-5 py-8 md:px-8 md:py-9">
        <header className="animate-enter max-w-[46rem]">
          <h1 className="text-[2.1rem] font-semibold leading-[1.08] tracking-[-0.04em] text-foreground md:text-[2.75rem]">
            把复杂问题，<br className="sm:hidden" />研究清楚。
          </h1>
          <p className="mt-3 max-w-[44rem] text-[0.95rem] leading-7 text-muted-foreground md:text-base">
            输入一个问题。系统会检索多方来源、核对分歧，并把结论连接回证据。
          </p>
        </header>

        <div className="animate-enter animation-delay-200 mt-6 w-full">
          <div className="mb-3 flex items-end justify-between gap-5 px-0.5">
            <div>
              <h2 className="text-base font-semibold tracking-[-0.02em] text-foreground">
                你想研究什么？
              </h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground sm:text-sm">
                可以是一条问题、一个判断，或一组需要比较的对象。
              </p>
            </div>
            <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">
              回车发送 · ⇧ + 回车换行
            </span>
          </div>

          <InputForm
            ref={inputFormRef}
            onSubmit={handleSubmit}
            isLoading={isLoading}
            onCancel={onCancel}
            hasHistory={false}
          />
        </div>

        <section className="animate-enter animation-delay-300 mt-7 grid border-y border-border md:grid-cols-[1.08fr_0.92fr]">
          <div className="py-4 md:border-r md:border-border md:py-5 md:pr-7">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="text-sm font-semibold tracking-[-0.01em] text-foreground">
                从一个结构开始
              </h2>
              <p className="text-[0.7rem] text-muted-foreground">
                点击填入，再补充具体对象
              </p>
            </div>

            <div className="mt-3 divide-y divide-border">
              {promptStarters.map((prompt) => (
                <button
                  key={prompt.label}
                  type="button"
                  className="group grid w-full cursor-pointer grid-cols-[4.25rem_minmax(0,1fr)_1rem] items-center gap-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/35"
                  aria-label={`填入示例：${prompt.question}`}
                  onClick={() => inputFormRef.current?.setInputValue(prompt.question)}
                >
                  <span className="text-[0.68rem] text-muted-foreground">
                    {prompt.label}
                  </span>
                  <span className="text-xs leading-5 text-foreground/85 transition-colors group-hover:text-primary sm:text-sm">
                    {prompt.question}
                  </span>
                  <ArrowUpRight
                    className="size-3.5 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary"
                    strokeWidth={1.7}
                    aria-hidden="true"
                  />
                </button>
              ))}
            </div>
          </div>

          <div className="border-t border-border py-4 md:border-t-0 md:py-5 md:pl-7">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="text-sm font-semibold tracking-[-0.01em] text-foreground">
                研究如何完成
              </h2>
              <p className="text-[0.7rem] text-muted-foreground">过程实时可见</p>
            </div>

            <ol className="mt-3 grid gap-3">
              {researchSteps.map((step, index) => {
                const Icon = step.icon;

                return (
                  <li
                    key={step.title}
                    className="grid grid-cols-[2rem_minmax(0,1fr)] items-center gap-3"
                  >
                    <span className="flex size-8 items-center justify-center rounded-lg border border-border bg-card text-primary">
                      <Icon className="size-3.5" strokeWidth={1.7} aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex items-baseline gap-2">
                        <span className="text-[0.64rem] tabular-nums text-muted-foreground">
                          0{index + 1}
                        </span>
                        <h3 className="text-xs font-medium text-foreground sm:text-sm">
                          {step.title}
                        </h3>
                      </div>
                      <p className="mt-0.5 text-[0.7rem] leading-4 text-muted-foreground">
                        {step.description}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        </section>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[0.72rem] leading-5 text-muted-foreground">
          <p>重要结论仍应回到原始来源核验。</p>
          <p>研究深度与模型可在提交前调整。</p>
        </div>
      </section>
    </div>
  );
};
