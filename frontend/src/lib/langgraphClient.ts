import { Client } from "@langchain/langgraph-sdk";

export function disableIdleReconnect(client: Client): Client {
  const stream = client.runs.stream.bind(client.runs);

  client.runs.stream = ((
    threadId: string,
    assistantId: string,
    payload: Record<string, unknown> = {},
  ) =>
    stream(threadId, assistantId, {
      ...payload,
      streamIdleReconnect: 0,
    })) as typeof client.runs.stream;

  return client;
}

export function createLocalLangGraphClient(apiUrl: string): Client {
  return disableIdleReconnect(new Client({ apiUrl }));
}
