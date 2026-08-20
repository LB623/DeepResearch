import type { Client } from "@langchain/langgraph-sdk";
import { describe, expect, it, vi } from "vitest";

import { disableIdleReconnect } from "./langgraphClient";

describe("disableIdleReconnect", () => {
  it("disables the SSE idle watchdog for long-running local requests", () => {
    const stream = vi.fn();
    const client = { runs: { stream } } as unknown as Client;

    disableIdleReconnect(client);
    client.runs.stream("thread-id", "agent", { input: null });

    expect(stream).toHaveBeenCalledWith(
      "thread-id",
      "agent",
      expect.objectContaining({ streamIdleReconnect: 0 }),
    );
  });
});
