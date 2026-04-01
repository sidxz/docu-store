import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import { loadConfig } from "../utils/config.js";
import { getAuthCredentials, authHeaders } from "../api/client.js";
import { extractApiError } from "../utils/api-error.js";
import * as log from "../utils/logger.js";
import pc from "picocolors";
import ora from "ora";

// ── Types ────────────────────────────────────────────────────────────

interface ChatOptions {
  interactive?: boolean;
  mode?: string;
  json?: boolean;
  apiUrl?: string;
}

interface ConversationDTO {
  conversation_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  is_archived: boolean;
}

interface ChatMessageDTO {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceCitation[];
  created_at: string;
}

interface ConversationDetailDTO extends ConversationDTO {
  messages: ChatMessageDTO[];
}

interface SourceCitation {
  artifact_id: string;
  artifact_title: string | null;
  page_index: number | null;
  citation_index: number;
  text_excerpt: string | null;
}

interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

// ── One-shot chat ────────────────────────────────────────────────────

export async function chatCommand(
  message: string | undefined,
  opts: ChatOptions,
): Promise<void> {
  if (!message && !opts.interactive) {
    log.error('Provide a message or use --interactive (-i) for REPL mode.');
    log.info('Usage: docu chat "your question" or docu chat -i');
    process.exit(1);
  }

  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  if (opts.interactive) {
    await interactiveMode(apiUrl, creds, opts);
    return;
  }

  // One-shot: create conversation, send message, delete conversation
  const conv = await createConversation(apiUrl, creds);
  try {
    const result = await sendAndStream(apiUrl, creds, conv.conversation_id, message!, opts);
    if (opts.json) {
      console.log(JSON.stringify(result, null, 2));
    }
  } catch (err) {
    log.error(`Chat error: ${err instanceof Error ? err.message : "Unknown error"}`);
    process.exit(1);
  } finally {
    // Clean up ephemeral conversation
    await fetch(`${apiUrl}/chat/${conv.conversation_id}`, {
      method: "DELETE",
      headers: authHeaders(creds),
    }).catch(() => {});
  }
}

// ── Interactive REPL ─────────────────────────────────────────────────

async function interactiveMode(
  apiUrl: string,
  creds: { idp_token: string; authz_token: string },
  opts: ChatOptions,
): Promise<void> {
  const conv = await createConversation(apiUrl, creds);
  console.log(pc.dim(`Conversation: ${conv.conversation_id}`));
  console.log(pc.dim("Type your message. Ctrl+C to exit.\n"));

  const rl = createInterface({ input: stdin, output: stdout });

  try {
    while (true) {
      const message = await rl.question(pc.cyan("docu> "));
      const trimmed = message.trim();
      if (!trimmed) continue;

      if (trimmed === "/quit" || trimmed === "/exit") break;

      try {
        await sendAndStream(apiUrl, creds, conv.conversation_id, trimmed, opts);
      } catch (err) {
        log.error(`Chat error: ${err instanceof Error ? err.message : "Unknown error"}`);
      }
      console.log("");
    }
  } catch (err) {
    // Ctrl+C triggers ERR_USE_AFTER_CLOSE
    if ((err as NodeJS.ErrnoException).code !== "ERR_USE_AFTER_CLOSE") {
      throw err;
    }
  } finally {
    rl.close();
    console.log(pc.dim("\nSession ended."));
  }
}

// ── List conversations ───────────────────────────────────────────────

export async function chatListCommand(opts: {
  limit: string;
  json?: boolean;
  apiUrl?: string;
}): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();
  const limit = parseInt(opts.limit, 10);

  const resp = await fetch(
    `${apiUrl}/chat?skip=0&limit=${limit}&is_archived=false`,
    { headers: authHeaders(creds) },
  );

  if (!resp.ok) {
    log.error(`Failed to list conversations: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  const conversations = (await resp.json()) as ConversationDTO[];

  if (opts.json) {
    console.log(JSON.stringify(conversations, null, 2));
    return;
  }

  if (!conversations.length) {
    log.info("No conversations found.");
    return;
  }

  console.log(`\n${pc.bold("Conversations")} (${conversations.length})`);
  console.log("─".repeat(70));

  for (const c of conversations) {
    const title = c.title || pc.dim("(untitled)");
    const date = c.updated_at.split("T")[0];
    const msgs = `${c.message_count} msg${c.message_count !== 1 ? "s" : ""}`;
    console.log(
      `  ${pc.dim(c.conversation_id.slice(0, 8))}  ${title.padEnd(40)}  ${pc.dim(date)}  ${pc.dim(msgs)}`,
    );
  }
  console.log("");
}

// ── Show conversation ────────────────────────────────────────────────

export async function chatShowCommand(
  conversationId: string,
  opts: { json?: boolean; apiUrl?: string },
): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  const resp = await fetch(
    `${apiUrl}/chat/${conversationId}?skip=0&limit=100`,
    { headers: authHeaders(creds) },
  );

  if (resp.status === 404) {
    log.error("Conversation not found.");
    process.exit(1);
  }

  if (!resp.ok) {
    log.error(`Failed: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  const detail = (await resp.json()) as ConversationDetailDTO;

  if (opts.json) {
    console.log(JSON.stringify(detail, null, 2));
    return;
  }

  console.log(`\n${pc.bold(detail.title || "(untitled)")}`);
  console.log(pc.dim(`ID: ${detail.conversation_id}`));
  console.log("─".repeat(70));

  for (const msg of detail.messages) {
    const role =
      msg.role === "user"
        ? pc.cyan(pc.bold("You"))
        : pc.green(pc.bold("Assistant"));
    console.log(`\n${role}  ${pc.dim(msg.created_at.split("T")[0])}`);
    console.log(msg.content);

    if (msg.sources.length > 0) {
      console.log(pc.dim("\n  Sources:"));
      for (const s of msg.sources) {
        const label = s.artifact_title || s.artifact_id.slice(0, 8);
        const page = s.page_index != null ? ` p${s.page_index}` : "";
        console.log(pc.dim(`    [${s.citation_index}] ${label}${page}`));
      }
    }
  }
  console.log("");
}

// ── Delete conversation ──────────────────────────────────────────────

export async function chatDeleteCommand(
  conversationId: string,
  opts: { force?: boolean; apiUrl?: string },
): Promise<void> {
  const config = loadConfig();
  const apiUrl = (opts.apiUrl || config.api_url).replace(/\/$/, "");
  const creds = await getAuthCredentials();

  if (!opts.force) {
    const rl = createInterface({ input: stdin, output: stdout });
    try {
      const answer = await rl.question(
        `Delete conversation ${conversationId.slice(0, 8)}...? [y/N]: `,
      );
      if (answer.trim().toLowerCase() !== "y") {
        log.info("Cancelled.");
        return;
      }
    } finally {
      rl.close();
    }
  }

  const resp = await fetch(`${apiUrl}/chat/${conversationId}`, {
    method: "DELETE",
    headers: authHeaders(creds),
  });

  if (resp.status === 204 || resp.ok) {
    log.success("Conversation deleted.");
  } else if (resp.status === 404) {
    log.error("Conversation not found.");
  } else {
    log.error(`Delete failed: ${resp.status}`);
  }
}

// ── SSE streaming ────────────────────────────────────────────────────

async function createConversation(
  apiUrl: string,
  creds: { idp_token: string; authz_token: string },
): Promise<ConversationDTO> {
  const resp = await fetch(`${apiUrl}/chat`, {
    method: "POST",
    headers: {
      ...authHeaders(creds),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });

  if (!resp.ok) {
    log.error(`Failed to create conversation: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  return (await resp.json()) as ConversationDTO;
}

interface StreamResult {
  content: string;
  sources: SourceCitation[];
  tokens: { prompt: number; completion: number; total: number } | null;
}

async function sendAndStream(
  apiUrl: string,
  creds: { idp_token: string; authz_token: string },
  conversationId: string,
  message: string,
  opts: ChatOptions,
): Promise<StreamResult> {
  const body: Record<string, unknown> = { message };
  if (opts.mode) body.mode = opts.mode;

  const resp = await fetch(`${apiUrl}/chat/${conversationId}/messages`, {
    method: "POST",
    headers: {
      ...authHeaders(creds),
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    log.error(`Chat failed: ${await extractApiError(resp)}`);
    process.exit(1);
  }

  if (!resp.body) {
    log.error("No response stream received.");
    process.exit(1);
  }

  const result: StreamResult = { content: "", sources: [], tokens: null };
  const spinner = ora({ text: "Thinking...", stream: process.stderr });
  let spinnerActive = false;
  let streamStarted = false;

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode(); // flush remaining multi-byte sequences
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      const events = parseSSEBuffer(buffer);
      buffer = events.remaining;

      for (const evt of events.parsed) {
        switch (evt.event) {
          case "agent_step": {
            const step = (evt.data.step as string) || "";
            const status = evt.data.status as string;
            if (status === "started") {
              const label = step.replace(/_/g, " ");
              if (!spinnerActive) {
                spinner.start(label);
                spinnerActive = true;
              } else {
                spinner.text = label;
              }
            }
            break;
          }

          case "token": {
            if (spinnerActive) {
              spinner.stop();
              spinnerActive = false;
              if (!streamStarted && !opts.json) {
                console.log("");
                streamStarted = true;
              }
            }
            const delta = (evt.data.delta as string) || "";
            result.content += delta;
            if (!opts.json) {
              process.stdout.write(delta);
            }
            break;
          }

          case "retrieval_results": {
            const sources = evt.data.sources as SourceCitation[] | undefined;
            if (sources) result.sources = sources;
            break;
          }

          case "done": {
            if (spinnerActive) {
              spinner.stop();
              spinnerActive = false;
            }
            if (evt.data.total_tokens) {
              result.tokens = {
                prompt: (evt.data.prompt_tokens as number) || 0,
                completion: (evt.data.completion_tokens as number) || 0,
                total: (evt.data.total_tokens as number) || 0,
              };
            }
            break;
          }

          case "error": {
            if (spinnerActive) {
              spinner.stop();
              spinnerActive = false;
            }
            const errMsg = (evt.data.error_message as string) || "Unknown error";
            throw new Error(errMsg);
          }
        }
      }
    }
  } finally {
    if (spinnerActive) spinner.stop();
  }

  // Process any remaining events in the buffer after stream ends
  if (buffer.trim()) {
    const final = parseSSEBuffer(buffer + "\n\n");
    for (const evt of final.parsed) {
      if (evt.event === "token") {
        const delta = (evt.data.delta as string) || "";
        result.content += delta;
        if (!opts.json) process.stdout.write(delta);
      } else if (evt.event === "retrieval_results") {
        const sources = evt.data.sources as SourceCitation[] | undefined;
        if (sources) result.sources = sources;
      }
    }
  }

  // Print newline after streamed content
  if (streamStarted && !opts.json) {
    console.log("");
  }

  // Show sources
  if (!opts.json && result.sources.length > 0) {
    console.log(pc.dim("\nSources:"));
    for (const s of result.sources) {
      const label = s.artifact_title || s.artifact_id.slice(0, 8);
      const page = s.page_index != null ? ` p${s.page_index}` : "";
      console.log(pc.dim(`  [${s.citation_index}] ${label}${page}`));
    }
  }

  return result;
}

// ── SSE parser ───────────────────────────────────────────────────────

function parseSSEBuffer(buffer: string): {
  parsed: SSEEvent[];
  remaining: string;
} {
  const parsed: SSEEvent[] = [];
  const blocks = buffer.split("\n\n");

  // Last block may be incomplete
  const remaining = blocks.pop() || "";

  for (const block of blocks) {
    if (!block.trim()) continue;

    let eventType = "message";
    let dataLines: string[] = [];

    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }

    if (dataLines.length > 0) {
      const rawData = dataLines.join("\n");
      try {
        const data = JSON.parse(rawData);
        parsed.push({ event: eventType, data });
      } catch {
        // Skip malformed JSON
      }
    }
  }

  return { parsed, remaining };
}
