import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createRef } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InputForm, type InputFormHandle } from "./InputForm";

describe("InputForm", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("submits the topic with the selected default model and effort", async () => {
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
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(
      <InputForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isLoading={false}
        hasHistory={false}
      />,
    );

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(screen.getAllByText("Model A").length).toBeGreaterThan(0),
    );
    await user.type(
      screen.getByPlaceholderText("如何评价DeepSeek成立Harness团队？"),
      "分析 AI 芯片市场",
    );
    await user.click(screen.getByRole("button", { name: "开始研究" }));

    expect(onSubmit).toHaveBeenCalledWith("分析 AI 芯片市场", "low", "model-a");
  });

  it("submits with Enter and keeps Shift+Enter as a line break", async () => {
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
    const onSubmit = vi.fn();
    const user = userEvent.setup();

    render(
      <InputForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isLoading={false}
        hasHistory={false}
      />,
    );

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    const textarea = screen.getByPlaceholderText(
      "如何评价DeepSeek成立Harness团队？",
    );

    await user.type(textarea, "比较两类框架{Shift>}{Enter}{/Shift}并说明取舍");
    expect(textarea).toHaveValue("比较两类框架\n并说明取舍");
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(textarea, "{Enter}");

    expect(onSubmit).toHaveBeenCalledWith(
      "比较两类框架\n并说明取舍",
      "low",
      "model-a",
    );
    expect(textarea).toHaveValue("");
  });

  it("does not submit Enter while composing text or while research is loading", async () => {
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
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <InputForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isLoading={false}
        hasHistory={false}
      />,
    );

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    const textarea = screen.getByPlaceholderText(
      "如何评价DeepSeek成立Harness团队？",
    );
    await user.type(textarea, "中文输入中的问题");

    fireEvent.keyDown(textarea, {
      key: "Enter",
      code: "Enter",
      isComposing: true,
      keyCode: 229,
    });
    expect(onSubmit).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("中文输入中的问题");

    rerender(
      <InputForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isLoading={true}
        hasHistory={false}
      />,
    );
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter" });

    expect(onSubmit).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("中文输入中的问题");
  });

  it("fills and focuses a suggested research structure", async () => {
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
    const ref = createRef<InputFormHandle>();

    render(
      <InputForm
        ref={ref}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isLoading={false}
        hasHistory={false}
      />,
    );

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    act(() => {
      ref.current?.setInputValue("核查一个观点的证据、反例与主要争议");
    });

    const textarea = screen.getByPlaceholderText(
      "如何评价DeepSeek成立Harness团队？",
    );
    await waitFor(() => {
      expect(textarea).toHaveValue("核查一个观点的证据、反例与主要争议");
      expect(textarea).toHaveFocus();
    });
  });
});
