import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { Button } from "@/components/ui/button";
import {
  ArrowRight,
  Brain,
  Cpu,
  SquarePen,
  StopCircle,
  Zap,
} from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { fetchAvailableModels, type ModelConfig } from "@/lib/api";
import { cn } from "@/lib/utils";

// Updated InputFormProps
interface InputFormProps {
  onSubmit: (inputValue: string, effort: string, model: string) => void;
  onCancel: () => void;
  isLoading: boolean;
  hasHistory: boolean;
}

export interface InputFormHandle {
  submitInput: (value: string) => void;
  setInputValue: (value: string) => void;
}

export const InputForm = forwardRef<InputFormHandle, InputFormProps>(function InputForm(
  { onSubmit, onCancel, isLoading, hasHistory },
  ref
) {
  const [internalInputValue, setInternalInputValue] = useState("");
  const [effort, setEffort] = useState("low");
  const [model, setModel] = useState("");
  const [availableModels, setAvailableModels] = useState<ModelConfig[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const selectedModel = model || availableModels[0]?.model_id || "";

  // 加载可用模型列表
  useEffect(() => {
    fetchAvailableModels().then((models) => {
      setAvailableModels(models);
      setModel((currentModel) =>
        models.some(({ model_id }) => model_id === currentModel)
          ? currentModel
          : (models[0]?.model_id ?? ""),
      );
    });
  }, []);

  const canSubmit = Boolean(
    internalInputValue.trim() && selectedModel && !isLoading,
  );

  const handleInternalSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!canSubmit) return;
    onSubmit(internalInputValue, effort, selectedModel);
    setInternalInputValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;

    e.preventDefault();
    handleInternalSubmit();
  };

  useImperativeHandle(
    ref,
    () => ({
      submitInput(value: string) {
        if (!value.trim() || !selectedModel || isLoading) return;
        onSubmit(value, effort, selectedModel);
        setInternalInputValue("");
      },
      setInputValue(value: string) {
        setInternalInputValue(value);
        textareaRef.current?.focus();
      },
    }),
    [effort, isLoading, onSubmit, selectedModel]
  );

  return (
    <form
      onSubmit={handleInternalSubmit}
      className={cn(
        "research-composer overflow-hidden border border-border bg-card shadow-[0_28px_90px_-48px_rgba(15,28,24,0.5)]",
        hasHistory
          ? "mx-auto w-full max-w-[960px] rounded-2xl shadow-[0_18px_50px_-38px_rgba(15,28,24,0.45)]"
          : "research-composer-primary w-full rounded-2xl",
      )}
    >
      <div className={cn("px-4 pt-4 md:px-5 md:pt-5", hasHistory ? "pb-2" : "pb-4")}>
        <div className="mb-2 flex items-center justify-between gap-4">
          <label
            htmlFor={hasHistory ? "research-follow-up" : "research-question"}
            className="block text-xs font-medium text-muted-foreground"
          >
            {hasHistory ? "继续追问" : "研究问题"}
          </label>
          {!hasHistory && (
            <span className="text-[0.7rem] text-muted-foreground sm:hidden">
              回车发送
            </span>
          )}
        </div>
        <Textarea
          ref={textareaRef}
          id={hasHistory ? "research-follow-up" : "research-question"}
          value={internalInputValue}
          onChange={(e) => setInternalInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          enterKeyHint="send"
          placeholder="如何评价DeepSeek成立Harness团队？"
          className={cn(
            "w-full resize-none border-0 bg-transparent px-0 text-[1rem] leading-7 text-foreground shadow-none outline-none placeholder:text-muted-foreground/60 focus-visible:ring-0 md:text-[1.04rem]",
            hasHistory
              ? "min-h-[4.5rem] max-h-[12rem]"
              : "min-h-[8rem] max-h-[18rem] text-[1.05rem] leading-8 md:min-h-[9.5rem] md:text-[1.12rem]",
          )}
          rows={hasHistory ? 2 : 4}
        />
      </div>
      <div className="flex flex-col gap-3 border-t border-border bg-secondary/35 px-3 py-3 sm:flex-row sm:items-center sm:justify-between md:px-4">
        <div className="grid min-w-0 grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          <div className="control-cluster flex min-w-0 items-center rounded-lg border border-border bg-card pl-3">
            <Brain className="size-3.5 shrink-0 text-primary" strokeWidth={1.7} />
            <span className="ml-2 hidden text-xs text-muted-foreground xs:inline">研究深度</span>
            <Select value={effort} onValueChange={setEffort}>
              <SelectTrigger
                aria-label="研究深度"
                className="min-w-0 flex-1 cursor-pointer border-0 bg-transparent px-2 text-xs font-medium shadow-none data-[size=default]:h-11 focus-visible:ring-0 sm:w-[4.5rem] sm:data-[size=default]:h-9"
              >
                <SelectValue placeholder="深度" />
              </SelectTrigger>
              <SelectContent className="rounded-xl border-border bg-popover text-popover-foreground shadow-xl">
                <SelectItem
                  value="low"
                  className="cursor-pointer rounded-lg focus:bg-accent"
                >
                  快速
                </SelectItem>
                <SelectItem
                  value="medium"
                  className="cursor-pointer rounded-lg focus:bg-accent"
                >
                  标准
                </SelectItem>
                <SelectItem
                  value="high"
                  className="cursor-pointer rounded-lg focus:bg-accent"
                >
                  深入
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="control-cluster flex min-w-0 items-center rounded-lg border border-border bg-card pl-1 xs:pl-3">
            <Cpu className="hidden size-3.5 shrink-0 text-primary xs:block" strokeWidth={1.7} />
            <span className="ml-2 hidden text-xs text-muted-foreground xs:inline">模型</span>
            <Select value={selectedModel} onValueChange={setModel}>
              <SelectTrigger
                aria-label="推理模型"
                className="min-w-0 flex-1 cursor-pointer border-0 bg-transparent px-2 text-xs font-medium shadow-none data-[size=default]:h-11 focus-visible:ring-0 sm:w-[9rem] sm:data-[size=default]:h-9"
                disabled={availableModels.length === 0}
              >
                <SelectValue placeholder="正在载入" />
              </SelectTrigger>
              <SelectContent className="rounded-xl border-border bg-popover text-popover-foreground shadow-xl">
                {availableModels.map((modelConfig) => {
                  const IconComponent = modelConfig.icon === "Cpu" ? Cpu : Zap;
                  return (
                    <SelectItem
                      key={modelConfig.model_id}
                      value={modelConfig.model_id}
                      className="cursor-pointer rounded-lg focus:bg-accent"
                    >
                      <div className="flex items-center">
                        <IconComponent className="mr-2 size-3.5 text-primary" strokeWidth={1.7} />
                        {modelConfig.display_name}
                      </div>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex w-full gap-2 sm:w-auto">
          {hasHistory && (
            <Button
              type="button"
              className="h-11 flex-1 cursor-pointer rounded-lg border-border bg-card px-3 text-xs font-medium text-foreground shadow-none hover:bg-accent active:translate-y-px sm:h-9 sm:flex-none"
              variant="outline"
              onClick={() => window.location.reload()}
            >
              <SquarePen className="size-3.5" strokeWidth={1.7} />
              新建研究
            </Button>
          )}

          {isLoading ? (
            <Button
              type="button"
              aria-label="取消研究"
              variant="outline"
              className="h-11 flex-1 cursor-pointer rounded-lg border-destructive/20 bg-destructive/5 px-5 text-sm font-medium text-destructive shadow-none hover:bg-destructive/10 hover:text-destructive active:translate-y-px sm:min-w-[8.5rem] sm:flex-none"
              onClick={onCancel}
            >
              <StopCircle className="size-4" strokeWidth={1.8} />
              取消研究
            </Button>
          ) : (
            <Button
              type="submit"
              aria-label={hasHistory ? "发送追问" : "开始研究"}
              className="h-11 flex-1 cursor-pointer rounded-lg border border-transparent bg-primary px-5 text-sm font-medium text-primary-foreground shadow-none hover:bg-primary/90 active:translate-y-px disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-muted-foreground sm:min-w-[8.5rem] sm:flex-none"
              disabled={!canSubmit}
            >
              <span>{hasHistory ? "发送追问" : "开始研究"}</span>
              <ArrowRight className="size-4" strokeWidth={1.9} />
            </Button>
          )}
        </div>
      </div>
    </form>
  );
});
