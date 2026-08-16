import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchAvailableModels } from "./api";

describe("fetchAvailableModels", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("returns models from the API response", async () => {
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

    await expect(fetchAvailableModels()).resolves.toEqual([
      {
        model_id: "model-a",
        display_name: "Model A",
        icon: "Zap",
        icon_color: "yellow-400",
      },
    ]);
  });

  it("returns stable fallback models when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    vi.spyOn(console, "warn").mockImplementation(() => undefined);

    const models = await fetchAvailableModels();

    expect(models).toHaveLength(3);
    expect(models[0].model_id).toBe("qwen3.6-flash");
  });
});
