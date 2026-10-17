import { BridgeError, isAgentName } from "./types.js";
import type {
  Agent,
  Attachment,
  AgentName,
  Conversation,
  IncomingMessage,
  Logger,
  Reply,
} from "./types.js";
import { conversationKey, SessionStore } from "./store.js";

interface BridgeOptions {
  workspace?: string;
  defaultAgent: AgentName;
  maxConcurrent: number;
  requestsPerMinute: number;
  timeoutMs: number;
  authorize(message: IncomingMessage): boolean;
  models?: Partial<Record<AgentName, string[]>>;
}

interface LogicalInput {
  prompt: string;
  attachments: Attachment[];
}
export type PrepareInput = (
  signal: AbortSignal,
) => Promise<{ text: string; attachments?: Attachment[] }>;

async function abortable<T>(
  operation: Promise<T>,
  signal: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(signal.reason);
    signal.addEventListener("abort", onAbort, { once: true });
    operation
      .then(resolve, reject)
      .finally(() => signal.removeEventListener("abort", onAbort));
    if (signal.aborted) onAbort();
  });
}

interface RunningTask {
  controller: AbortController;
  done: Promise<void>;
}

const HELP =
  "/agent：查看执行器\n/agent codex 或 /agent cursor：切换执行器\n/status：查看会话状态\n/reset（/new）：归档并开启新会话\n/sessions：列出当前执行器的历史\n/resume <序号>：恢复历史会话\n/model [模型 ID|default]：查看或切换模型\n/rerun：重跑上一条问题\n/cancel（/stop）：取消当前任务\n/help：查看帮助";

export class Bridge {
  private readonly running = new Map<string, RunningTask>();
  private readonly seen = new Map<string, number>();
  private readonly rates = new Map<string, number[]>();
  private readonly lastPrompts = new Map<
    string,
    Partial<Record<AgentName, LogicalInput>>
  >();
  private closing = false;

  constructor(
    private readonly agents: Record<AgentName, Agent>,
    private readonly store: SessionStore,
    private readonly options: BridgeOptions,
    private readonly logger: Logger,
  ) {}

  accepts(message: IncomingMessage): boolean {
    return !this.closing && this.options.authorize(message);
  }

  snapshot(): { accepting: boolean; running: number } {
    return { accepting: !this.closing, running: this.running.size };
  }

  async handle(
    message: IncomingMessage,
    reply: Reply,
    prepare?: PrepareInput,
  ): Promise<void> {
    if (!this.options.authorize(message)) return;
    if (this.closing) {
      await reply.finish("服务正在停止，请稍后重试。");
      return;
    }
    if (
      [
        message.channel,
        message.accountId,
        message.conversationId,
        message.userId,
        message.messageId,
      ].some(
        (value) => typeof value !== "string" || !value || value.length > 500,
      )
    )
      return;
    let text = message.text.trim();
    let attachments = message.attachments ?? [];
    if ((!text && !prepare) || text.length > 32_000) {
      await reply.finish("请输入 1～32,000 字符的消息。");
      return;
    }
    const key = conversationKey(message, this.options.workspace);
    const dedup = JSON.stringify([
      message.channel,
      message.accountId,
      message.messageId,
    ]);
    const now = Date.now();
    for (const [id, time] of this.seen) {
      if (now - time > 86_400_000) this.seen.delete(id);
    }
    if (this.seen.has(dedup)) return;
    this.seen.set(dedup, now);
    if (this.seen.size > 10_000)
      this.seen.delete(this.seen.keys().next().value!);
    const conversation = this.store.get(key) ?? {
      selectedAgent: this.options.defaultAgent,
      sessions: {},
      updatedAt: now,
    };
    if (!attachments.length && ["/cancel", "/stop"].includes(text)) {
      await this.command(key, conversation, text, reply);
      return;
    }
    const rateKey = JSON.stringify([
      message.channel,
      message.accountId,
      message.userId,
    ]);
    for (const [id, times] of this.rates) {
      if (now - times[times.length - 1]! >= 60_000) this.rates.delete(id);
    }
    const timestamps = (this.rates.get(rateKey) ?? []).filter(
      (time) => now - time < 60_000,
    );
    if (timestamps.length >= this.options.requestsPerMinute) {
      await reply.finish("请求过于频繁，请稍后重试。");
      return;
    }
    if (!this.rates.has(rateKey) && this.rates.size >= 10_000) {
      await reply.finish("服务繁忙，请稍后重试。");
      return;
    }
    this.rates.set(rateKey, [...timestamps, now]);
    if (text === "/rerun") {
      const previous = this.lastPrompts.get(key)?.[conversation.selectedAgent];
      if (!previous) {
        await reply.finish("当前执行器没有可重跑的问题。");
        return;
      }
      prepare = undefined;
      text = previous.prompt;
      attachments = structuredClone(previous.attachments);
    }
    if (
      [
        "/agent",
        "/status",
        "/reset",
        "/new",
        "/cancel",
        "/stop",
        "/help",
        "/sessions",
        "/resume",
        "/model",
      ].includes(text.split(/\s+/)[0]!) &&
      !attachments.length
    ) {
      await this.command(key, conversation, text, reply);
      return;
    }
    if (this.running.has(key)) {
      await reply.finish("当前会话有任务运行，可使用 /cancel 取消。");
      return;
    }
    if (this.running.size >= this.options.maxConcurrent) {
      await reply.finish("任务并发达到上限，请稍后重试。");
      return;
    }
    const controller = new AbortController();
    // 先占用会话，再执行异步平台回复，避免相邻消息同时启动。
    const done = Promise.resolve().then(() =>
      this.execute(
        key,
        conversation,
        text,
        controller,
        reply,
        attachments,
        prepare,
      ),
    );
    this.running.set(key, { controller, done });
    try {
      await done;
    } finally {
      this.running.delete(key);
    }
  }

  private async command(
    key: string,
    conversation: Conversation,
    text: string,
    reply: Reply,
  ): Promise<void> {
    const [command, argument, ...rest] = text.split(/\s+/);
    const running = this.running.get(key);
    const name = conversation.selectedAgent;
    if (command === "/sessions" && !argument) {
      const entries = conversation.history?.[name] ?? [];
      const lines = entries.map(
        (entry, index) => `${index + 1}. ${entry.title || entry.id}`,
      );
      await reply.finish(
        `${name} 当前会话：${conversation.sessions[name] ? "可恢复" : "新会话"}\n${lines.length ? lines.join("\n") : "没有归档会话。"}`,
      );
      return;
    }
    if (command === "/model" && !argument) {
      const choices = this.options.models?.[name] ?? [];
      await reply.finish(
        `当前模型：${conversation.models?.[name] ?? "部署默认"}\n可选模型：${choices.join("、") || "未配置，请在配置文件中设置 agents.<name>.models"}`,
      );
      return;
    }
    if (command === "/resume" || (command === "/model" && argument)) {
      if (running) {
        await reply.finish("任务运行期间无法切换或重置，请先使用 /cancel。");
        return;
      }
      if (rest.length) {
        await reply.finish("命令参数无效。");
        return;
      }
      if (command === "/resume") {
        const entries = conversation.history?.[name] ?? [];
        const index =
          argument && /^[1-9]\d?$/.test(argument) ? Number(argument) - 1 : -1;
        const target = entries[index];
        if (!target) {
          await reply.finish("请使用 /sessions 中的有效序号。");
          return;
        }
        this.archive(key, conversation);
        conversation.sessions[name] = target.id;
        conversation.history![name] = conversation.history![name]!.filter(
          (entry) => entry.id !== target.id,
        );
      } else {
        const choices = this.options.models?.[name] ?? [];
        if (argument !== "default" && !choices.includes(argument!)) {
          await reply.finish("模型不在部署配置的可选列表中。");
          return;
        }
        conversation.models ??= {};
        if (argument === "default") delete conversation.models[name];
        else conversation.models[name] = argument!;
      }
      conversation.updatedAt = Date.now();
      try {
        this.store.put(key, conversation);
      } catch {
        await reply.finish("会话保存失败，请检查状态目录。");
        return;
      }
      await reply.finish(
        command === "/resume"
          ? "已恢复选中的历史会话。"
          : "模型设置对下一条消息生效。",
      );
      return;
    }
    if (
      (command === "/agent" && !argument) ||
      (command === "/status" && !argument)
    ) {
      await reply.finish(
        `当前执行器：${conversation.selectedAgent}\n状态：${running ? "运行中" : "空闲"}\n上下文：${conversation.sessions[conversation.selectedAgent] ? "可恢复" : "新会话"}`,
      );
      return;
    }
    if (command === "/help" && !argument) {
      await reply.finish(HELP);
      return;
    }
    if ((command === "/cancel" || command === "/stop") && !argument) {
      if (running) running.controller.abort(new BridgeError("任务已取消。"));
      await reply.finish(
        running ? "正在取消当前任务。" : "当前没有运行中的任务。",
      );
      return;
    }
    if (
      (command === "/agent" && isAgentName(argument) && rest.length === 0) ||
      ((command === "/reset" || command === "/new") && !argument)
    ) {
      if (running) {
        await reply.finish("任务运行期间无法切换或重置，请先使用 /cancel。");
        return;
      }
      if (command === "/agent" && isAgentName(argument))
        conversation.selectedAgent = argument;
      else this.archive(key, conversation);
      conversation.updatedAt = Date.now();
      try {
        this.store.put(key, conversation);
      } catch {
        await reply.finish("会话保存失败，请检查状态目录。");
        return;
      }
      await reply.finish(
        command === "/agent"
          ? `已切换为 ${conversation.selectedAgent}。`
          : `已清空 ${conversation.selectedAgent} 上下文。`,
      );
      return;
    }
    await reply.finish(`命令无效。\n${HELP}`);
  }

  private async execute(
    key: string,
    conversation: Conversation,
    prompt: string,
    controller: AbortController,
    reply: Reply,
    attachments: Attachment[] = [],
    prepare?: PrepareInput,
  ): Promise<void> {
    const name = conversation.selectedAgent;
    const timer = setTimeout(
      () => controller.abort(new BridgeError("任务超时，已停止执行。")),
      this.options.timeoutMs,
    );
    timer.unref();
    let content = "";
    try {
      await reply.update(`${name} 正在处理，可使用 /cancel 取消。`);
      controller.signal.throwIfAborted();
      if (prepare) {
        const input = await abortable(
          prepare(controller.signal),
          controller.signal,
        );
        prompt = input.text.trim();
        attachments = input.attachments ?? [];
      }
      controller.signal.throwIfAborted();
      if (!prompt || prompt.length > 32_000)
        throw new BridgeError("请输入 1～32,000 字符的消息。");
      conversation.updatedAt = Date.now();
      this.store.put(key, conversation);
      const prompts = this.lastPrompts.get(key) ?? {};
      prompts[name] = { prompt, attachments: structuredClone(attachments) };
      this.lastPrompts.set(key, prompts);
      if (this.lastPrompts.size > 1000)
        this.lastPrompts.delete(this.lastPrompts.keys().next().value!);
      let completed = false;
      const sessionId = conversation.sessions[name];
      const model = conversation.models?.[name];
      for await (const event of this.agents[name].run({
        prompt: `[聊天通道约定]\n只执行用户明确提出的任务。需要用户决定时用文本提问并结束本轮，本通道无法回答交互式工具。长任务先给出阶段性结论。\n\n[用户消息]\n${prompt}${attachments.length ? `\n\n[用户附件，本地路径]\n${attachments.map((attachment) => `${JSON.stringify(attachment.path)}（${attachment.mimeType}）`).join("\n")}` : ""}`,
        signal: controller.signal,
        ...(attachments.some((attachment) =>
          attachment.mimeType.startsWith("image/"),
        )
          ? {
              images: attachments
                .filter((attachment) =>
                  attachment.mimeType.startsWith("image/"),
                )
                .map((attachment) => attachment.path),
            }
          : {}),
        ...(sessionId ? { sessionId } : {}),
        ...(model ? { model } : {}),
      })) {
        controller.signal.throwIfAborted();
        if (event.type === "session") {
          conversation.sessions[name] = event.id;
          conversation.updatedAt = Date.now();
          this.store.put(key, conversation);
        }
        if (event.type === "text") {
          content = event.content;
          await reply.update(content);
        }
        if (event.type === "completed") completed = true;
      }
      controller.signal.throwIfAborted();
      if (!completed) throw new BridgeError("Agent 未确认任务完成。");
    } catch (error) {
      const failure = controller.signal.aborted
        ? controller.signal.reason
        : error;
      const message =
        failure instanceof BridgeError
          ? failure.message
          : "任务执行失败，请检查本机配置和状态目录。";
      this.logger.error(`${name}: ${message}`);
      content = `${content ? `${content}\n\n` : ""}${message}`;
    } finally {
      clearTimeout(timer);
    }
    await reply.finish(content || "任务完成，Agent 未返回文本。");
  }

  async close(): Promise<void> {
    this.closing = true;
    const tasks = [...this.running.values()];
    for (const task of tasks)
      task.controller.abort(new BridgeError("服务停止，任务已取消。"));
    await Promise.allSettled(tasks.map((task) => task.done));
  }

  private archive(key: string, conversation: Conversation): void {
    const name = conversation.selectedAgent;
    const id = conversation.sessions[name];
    conversation.history ??= {};
    const entries = conversation.history[name] ?? [];
    if (id)
      conversation.history[name] = [
        {
          id,
          title: (this.lastPrompts.get(key)?.[name]?.prompt ?? "").slice(0, 60),
          updatedAt: Date.now(),
        },
        ...entries.filter((entry) => entry.id !== id),
      ].slice(0, 10);
    delete conversation.sessions[name];
    const prompts = this.lastPrompts.get(key);
    if (prompts) delete prompts[name];
  }

  async idle(): Promise<void> {
    await Promise.allSettled(
      [...this.running.values()].map((task) => task.done),
    );
  }
}
