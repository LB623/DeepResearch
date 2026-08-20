import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Message } from "@langchain/langgraph-sdk";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

interface CapturedStreamOptions {
  onError?: (error: unknown) => void;
  onUpdateEvent?: (event: unknown) => void;
}

const streamHarness = vi.hoisted(() => ({
  messages: [] as Message[],
  isLoading: false,
  submit: vi.fn(),
  stop: vi.fn(),
  options: null as CapturedStreamOptions | null,
}));

vi.mock("@langchain/langgraph-sdk/react", () => ({
  useStream: (options: unknown) => {
    streamHarness.options = options as CapturedStreamOptions;
    return streamHarness;
  },
}));

describe("App user flows", () => {
  beforeEach(() => {
    streamHarness.messages = [];
    streamHarness.isLoading = false;
    streamHarness.submit.mockReset();
    streamHarness.stop.mockReset();
    streamHarness.options = null;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          models: [
            {
              model_id: "model-a",
              display_name: "Model A",
              icon: "Zap",
              icon_color: "yellow-400",
            },
          ],
        }),
      }),
    );
  });

  it("maps a low-effort submission to one query and one loop", async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    await user.type(
      screen.getByPlaceholderText("如何评价DeepSeek成立Harness团队？"),
      "分析 AI 芯片市场",
    );
    await user.click(screen.getByRole("button", { name: "开始研究" }));

    expect(streamHarness.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        initial_search_query_count: 1,
        max_research_loops: 1,
        reasoning_model: "model-a",
        plan_status: "unconfirmed",
      }),
      {
        onDisconnect: "continue",
        streamResumable: true,
      },
    );
  });

  it("shows an understandable error before a first message exists", async () => {
    render(<App />);

    act(() => {
      streamHarness.options?.onError?.(new Error("service offline"));
    });

    expect(await screen.findByText("service offline")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("cancels an active task without reloading the page", async () => {
    streamHarness.isLoading = true;
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "取消研究" }));

    expect(streamHarness.stop).toHaveBeenCalledOnce();
  });

  it("confirms a generated plan and resumes research", async () => {
    streamHarness.messages = [
      {
        type: "ai",
        id: "plan-message",
        content: "# 研究计划",
      },
    ];
    streamHarness.isLoading = false;
    const user = userEvent.setup();
    render(<App />);

    act(() => {
      streamHarness.options?.onUpdateEvent?.({
        generate_plan: { plan: "# 研究计划" },
      });
    });

    await user.click(
      await screen.findByRole("button", { name: "按此计划开始研究" }),
    );

    expect(streamHarness.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        plan_status: "confirmed",
        messages: expect.arrayContaining([
          expect.objectContaining({
            type: "human",
            content: "需求确认",
          }),
        ]),
      }),
      {
        onDisconnect: "continue",
        streamResumable: true,
      },
    );
  });
});
