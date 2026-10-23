import { AGENT_NAMES, BridgeError, isAgentName } from "./types.js";
import type {
  Agent,
  Attachment,
  AgentName,
  AgentPreference,
  Conversation,
  IncomingMessage,
  Logger,
  Reply,
  Progress,
  ReplyChoice,
} from "./types.js";
import { conversationKey, SessionStore } from "./store.js";
import { modelLabel } from "./agents/presets.js";
import { buildPrompt } from "./prompt.js";
import type { AuditSink } from "./audit.js";
import { DEFAULT_TASK_TIMEOUTS } from "./config.js";

interface BridgeOptions {
  workspace?: string;
  defaultAgent: AgentName;
  maxConcurrent: number;
  requestsPerMinute: number;
  timeoutMs?: number;
  idleTimeoutMs?: number;
  hardTimeoutMs?: number;
  authorize(message: IncomingMessage): boolean;
  models?: Partial<Record<AgentName, string[]>>;
  defaultModels?: Partial<Record<AgentName, string>>;
  persona?: string;
  isAdmin?(message: IncomingMessage): boolean;
  audit?: AuditSink;
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
  userId: string;
  controller: AbortController;
  done: Promise<void>;
}

const HELP =
  "/whoami：查看自己的身份与角色\n/access：管理员查看授权名单\n/allow <userid>：管理员邀请使用者\n/deny <userid>：管理员撤权\n/agent：选择执行器\n/agent <序号|codex|cursor>：切换执行器，对所有聊天生效\n/status：查看会话状态\n/reset（/new）：归档并开启新会话\n/sessions：列出当前执行器的历史\n/resume <序号>：恢复历史会话\n/model [序号|模型 ID|default]：查看或切换模型，对所有聊天生效\n/rerun：重跑上一条问题\n/cancel（/stop）：取消当前任务\n/help：查看帮助";

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

  revokeUser(userId: string): void {
    for (const task of this.running.values()) {
      if (task.userId === userId)
        task.controller.abort(new BridgeError("访问权限已撤销，任务停止。"));
    }
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
    if (
      /^\/(?:agent|model)\s+\S/.test(text) &&
      this.options.isAdmin &&
      !this.options.isAdmin(message)
    ) {
      this.options.audit?.record({
        action: "preference.denied",
        message,
        result: "not_admin",
      });
      await reply.finish(
        "全局执行器和模型仅允许管理员修改。可使用 /agent 或 /model 查看当前配置。",
      );
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
    this.applyPreference(conversation);
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
    this.options.audit?.record({
      action: "task.started",
      message,
      agent: conversation.selectedAgent,
    });
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
        message,
      ),
    );
    this.running.set(key, { controller, done, userId: message.userId });
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
    const [command, input, ...rest] = text.split(/\s+/);
    const running = this.running.get(key);
    const name = conversation.selectedAgent;
    let argument = input;
    if (command === "/agent" && argument && /^[1-9]\d*$/.test(argument))
      argument = AGENT_NAMES[Number(argument) - 1] ?? argument;
    if (command === "/model" && argument) {
      const scoped = /^(codex|cursor):(.+)$/.exec(argument);
      if (scoped) {
        if (scoped[1] !== name) {
          await reply.finish(
            `此选项属于 ${scoped[1]}，请先用 /agent 切换执行器。`,
          );
          return;
        }
        argument = scoped[2];
      }
      if (/^[1-9]\d*$/.test(argument!))
        argument =
          this.options.models?.[name]?.[Number(argument) - 1] ?? argument;
    }
    if (command === "/agent" && !argument) {
      const choices = AGENT_NAMES.map((agent) => ({
        label: `${agent === name ? "当前：" : ""}${agent}`,
        command: `/agent ${agent}`,
      }));
      await this.select(
        reply,
        `当前执行器：${name}\n${AGENT_NAMES.map((agent, i) => `${i + 1}. ${agent}${agent === name ? "（当前）" : ""}`).join("\n")}\n\n发送 /agent <序号或名称> 切换，例如 /agent 2。\n切换后使用 /model 选择对应模型。执行器和模型对所有聊天生效，各聊天保留各自的上下文。`,
        choices,
      );
      return;
    }
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
      await this.select(
        reply,
        `当前执行器：${name}\n当前模型：${modelLabel(name, conversation.models?.[name] ?? this.options.defaultModels?.[name] ?? "CLI 默认")}\n${choices.length ? choices.map((model, i) => `${i + 1}. ${modelLabel(name, model)}${model === (conversation.models?.[name] ?? this.options.defaultModels?.[name]) ? "（当前）" : ""}`).join("\n") : "未发现可选模型，可在配置中设置 agents." + name + ".models。"}\n\n发送 /model <序号或模型 ID> 切换，/model default 恢复默认。选择对所有聊天生效。`,
        choices.map((model) => ({
          label: modelLabel(name, model),
          command: `/model ${name}:${model}`,
        })),
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
        this.store.put(
          key,
          conversation,
          command === "/model" ? this.preferenceFrom(conversation) : undefined,
        );
      } catch {
        await reply.finish("会话保存失败，请检查状态目录。");
        return;
      }
      await reply.finish(
        command === "/resume"
          ? "已恢复选中的历史会话。"
          : `已设置 ${name} 模型：${modelLabel(name, conversation.models?.[name] ?? this.options.defaultModels?.[name] ?? "CLI 默认")}，对所有聊天的下一条消息生效。`,
      );
      return;
    }
    if (command === "/status" && !argument) {
      await reply.finish(
        `当前执行器：${conversation.selectedAgent}\n当前模型：${modelLabel(name, conversation.models?.[name] ?? this.options.defaultModels?.[name] ?? "CLI 默认")}\n状态：${running ? "运行中" : "空闲"}\n上下文：${conversation.sessions[conversation.selectedAgent] ? "可恢复" : "新会话"}`,
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
        this.store.put(
          key,
          conversation,
          command === "/agent" ? this.preferenceFrom(conversation) : undefined,
        );
      } catch {
        await reply.finish("会话保存失败，请检查状态目录。");
        return;
      }
      await reply.finish(
        command === "/agent"
          ? `已切换为 ${conversation.selectedAgent}，对所有聊天生效。\n当前模型：${modelLabel(conversation.selectedAgent, conversation.models?.[conversation.selectedAgent] ?? this.options.defaultModels?.[conversation.selectedAgent] ?? "CLI 默认")}\n发送 /model 查看可选模型。`
          : `已清空 ${conversation.selectedAgent} 上下文。`,
      );
      return;
    }
    await reply.finish(`命令无效。\n${HELP}`);
  }

  private applyPreference(conversation: Conversation): void {
    const preference = this.store.getPreference();
    if (!preference) return;
    conversation.selectedAgent = preference.selectedAgent;
    conversation.models = preference.models;
  }

  private preferenceFrom(conversation: Conversation): AgentPreference {
    return {
      selectedAgent: conversation.selectedAgent,
      models: structuredClone(conversation.models ?? {}),
      updatedAt: Date.now(),
    };
  }

  private async execute(
    key: string,
    conversation: Conversation,
    prompt: string,
    controller: AbortController,
    reply: Reply,
    attachments: Attachment[] = [],
    prepare?: PrepareInput,
    message?: IncomingMessage,
  ): Promise<void> {
    const name = conversation.selectedAgent;
    const idleTimeoutMs =
      this.options.idleTimeoutMs ?? DEFAULT_TASK_TIMEOUTS.idleTimeoutMs;
    const hardTimeoutMs =
      this.options.hardTimeoutMs ??
      this.options.timeoutMs ??
      DEFAULT_TASK_TIMEOUTS.hardTimeoutMs;
    let idleTimer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const clearTimers = (): void => {
      stopped = true;
      clearTimeout(idleTimer);
      clearTimeout(hardTimer);
    };
    const hardTimer = setTimeout(
      () =>
        controller.abort(
          new BridgeError(
            `任务执行超时：已达到总时限（${hardTimeoutMs / 1000} 秒），已停止执行。`,
          ),
        ),
      hardTimeoutMs,
    );
    hardTimer.unref();
    const onActivity = (): void => {
      if (stopped || controller.signal.aborted) return;
      clearTimeout(idleTimer);
      idleTimer = setTimeout(
        () =>
          controller.abort(
            new BridgeError(
              `任务连续 ${idleTimeoutMs / 1000} 秒无输出，已按空闲超时停止。`,
            ),
          ),
        idleTimeoutMs,
      );
      idleTimer.unref();
    };
    controller.signal.addEventListener("abort", clearTimers, { once: true });
    onActivity();
    let content = "";
    let progress: Progress = {
      content: `${name} 正在思考，可使用 /cancel 取消。`,
      active: true,
    };
    let receivedProgress = false;
    try {
      await reply.update("", progress);
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
      if (message && !this.options.authorize(message))
        throw new BridgeError("访问权限已撤销，任务停止。");
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
        prompt: buildPrompt(prompt, attachments, this.options.persona),
        signal: controller.signal,
        onActivity,
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
        if (message && !this.options.authorize(message))
          controller.abort(new BridgeError("访问权限已撤销，任务停止。"));
        controller.signal.throwIfAborted();
        onActivity();
        if (event.type === "session") {
          conversation.sessions[name] = event.id;
          conversation.updatedAt = Date.now();
          this.store.put(key, conversation);
        }
        if (event.type === "text") {
          content = event.content;
          progress = { ...progress, active: false };
          await reply.update(content, progress);
        }
        if (event.type === "progress") {
          receivedProgress = true;
          progress = { content: event.content, active: event.active };
          await reply.update(content, progress);
        }
        if (event.type === "completed") completed = true;
      }
      controller.signal.throwIfAborted();
      if (!completed) throw new BridgeError("Agent 未确认任务完成。");
      this.options.audit?.record({
        action: "task.completed",
        ...(message ? { message } : {}),
        agent: name,
      });
    } catch (error) {
      try {
        this.options.audit?.record({
          action: controller.signal.aborted ? "task.cancelled" : "task.failed",
          ...(message ? { message } : {}),
          agent: name,
        });
      } catch {
        this.logger.error("任务审计写入失败。");
      }
      const failure = controller.signal.aborted
        ? controller.signal.reason
        : error;
      const failureText =
        failure instanceof BridgeError
          ? failure.message
          : "任务执行失败，请检查本机配置和状态目录。";
      this.logger.error(`${name}: ${failureText}`);
      content = `${content ? `${content}\n\n` : ""}${failureText}`;
    } finally {
      clearTimers();
      controller.signal.removeEventListener("abort", clearTimers);
    }
    await reply.finish(content || "任务完成，Agent 未返回文本。", {
      ...progress,
      content: receivedProgress ? progress.content : "本次处理已结束。",
      active: false,
    });
  }

  private async select(
    reply: Reply,
    content: string,
    choices: ReplyChoice[],
  ): Promise<void> {
    if (reply.select && choices.length) await reply.select(content, choices);
    else await reply.finish(content);
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
