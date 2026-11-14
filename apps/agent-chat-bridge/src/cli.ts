#!/usr/bin/env node
import { WSClient } from "@wecom/aibot-node-sdk";
import { loadConfig } from "./config.js";
import { Bridge } from "./bridge.js";
import { CliAgent } from "./agents/cli-agent.js";
import { SessionStore } from "./store.js";
import { connectWeCom } from "./channels/wecom.js";
import { runTerminal } from "./channels/terminal.js";
import { BridgeError } from "./types.js";
import { startHealthServer } from "./health.js";
import type { Server } from "node:http";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { parseEnv } from "node:util";
import { initialize, savePairedUser } from "./setup.js";
import { PairingGate } from "./pairing.js";
import { execFileSync } from "node:child_process";

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  if (args.includes("--help")) {
    console.log(
      "agent-chat-bridge [init] [--config <file>] [--channel terminal|wecom]\n无参数时使用 bridge.local.json；首次在终端运行会启动配置向导。",
    );
    return;
  }
  if (process.platform === "win32")
    throw new BridgeError("进程组取消需要 macOS 或 Linux。");
  if (args[0] === "init") {
    if (args.length !== 1 || !process.stdin.isTTY)
      throw new BridgeError("请在交互终端运行 npm run setup 完成向导。");
    const file = await initialize(process.cwd());
    console.log(`配置已准备：${file}\n运行 npm start 即可启动。`);
    return;
  }
  let configFile = resolve("bridge.local.json");
  let channelOverride: string | undefined;
  for (let index = 0; index < args.length; index += 2) {
    const key = args[index],
      value = args[index + 1];
    if (!value || !["--config", "--channel"].includes(key!))
      throw new BridgeError("参数无效，请运行 --help 查看用法。");
    if (key === "--config") configFile = resolve(value);
    else channelOverride = value;
  }
  if (!existsSync(configFile)) {
    if (args.length || !process.stdin.isTTY)
      throw new BridgeError(
        "配置文件不存在，请先在交互终端运行 npm run setup。",
      );
    configFile = await initialize(process.cwd());
  }
  const envFile = join(dirname(configFile), ".env");
  if (existsSync(envFile)) {
    const values = parseEnv(readFileSync(envFile, "utf8"));
    for (const key of ["WECOM_BOT_ID", "WECOM_BOT_SECRET"])
      if (values[key] !== undefined) process.env[key] ??= values[key];
  }
  const config = loadConfig(configFile);
  const channel = channelOverride ?? config.channel;
  if (channel !== "terminal" && channel !== "wecom")
    throw new BridgeError("channel 只能是 wecom 或 terminal。");
  const botId = process.env.WECOM_BOT_ID;
  const secret = process.env.WECOM_BOT_SECRET;
  if (channel === "wecom" && (!botId || !secret))
    throw new BridgeError(
      "缺少机器人凭据，请运行 npm run setup 或设置 WECOM_BOT_ID / WECOM_BOT_SECRET。",
    );
  try {
    const env = Object.fromEntries(
      Object.entries(process.env).filter(
        ([key]) => !key.startsWith("WECOM_") && !key.startsWith("BRIDGE_"),
      ),
    );
    execFileSync(config.agents[config.defaultAgent].command, ["--version"], {
      timeout: 5000,
      stdio: "ignore",
      env,
    });
  } catch {
    const install =
      config.defaultAgent === "codex"
        ? "npm install -g @openai/codex，然后 codex login"
        : "curl https://cursor.com/install -fsS | bash，然后 cursor-agent login";
    throw new BridgeError(
      `${config.defaultAgent} CLI 不可用。请先运行：${install}，再重新启动。已安装时请检查 agents.${config.defaultAgent}.command。`,
    );
  }
  let pairing: PairingGate | undefined;
  if (channel === "wecom" && !config.wecom.allowedUsers.length) {
    if (!process.stdin.isTTY || !process.stderr.isTTY)
      throw new BridgeError(
        "首次配对需要前台交互终端，请先运行 npm start 完成绑定，再作为后台服务启动。",
      );
    pairing = new PairingGate({
      accountId: botId!,
      saveUser: (userId) => {
        savePairedUser(configFile, userId);
        config.wecom.allowedUsers.push(userId);
      },
    });
    console.error(
      `首次绑定：请私聊机器人发送 /pair ${pairing.code}（10 分钟有效）。`,
    );
  }
  const logger = {
    info: (message: string) => console.error(message),
    error: (message: string) => console.error(message),
  };
  const store = new SessionStore(config.stateDir);
  const bridge = new Bridge(
    {
      codex: new CliAgent("codex", config.agents.codex, config.workspace),
      cursor: new CliAgent("cursor", config.agents.cursor, config.workspace),
    },
    store,
    {
      ...config,
      models: {
        codex: config.agents.codex.models ?? [],
        cursor: config.agents.cursor.models ?? [],
      },
      defaultModels: Object.fromEntries(
        Object.entries(config.agents).flatMap(([name, agent]) =>
          agent.model ? [[name, agent.model]] : [],
        ),
      ),
      authorize: (message) =>
        message.channel === "terminal"
          ? channel === "terminal"
          : message.channel === "wecom" &&
            message.accountId === botId &&
            config.wecom.allowedUsers.includes(message.userId),
    },
    logger,
  );
  let client: WSClient | undefined;
  let health: Server | undefined;
  let connected = channel === "terminal";
  let shutdown: Promise<void> | undefined;
  const stop = (): Promise<void> =>
    (shutdown ??= (async () => {
      await bridge.close();
      client?.disconnect();
      if (health)
        await new Promise<void>((resolve) => health!.close(() => resolve()));
      store.close();
    })());
  const signal = (): void => {
    void stop().then(() =>
      process.exit(process.exitCode ? Number(process.exitCode) : 0),
    );
  };
  process.once("SIGINT", signal);
  process.once("SIGTERM", signal);
  try {
    if (config.healthPort)
      health = await startHealthServer(config.healthPort, () => ({
        connected:
          connected &&
          (channel === "terminal" || config.wecom.allowedUsers.length > 0),
        ...bridge.snapshot(),
        timeouts: {
          idleTimeoutMs: config.idleTimeoutMs,
          hardTimeoutMs: config.hardTimeoutMs,
        },
      }));
    if (channel === "terminal") {
      await runTerminal(bridge, logger);
      await stop();
    } else {
      client = new WSClient({
        botId: botId!,
        secret: secret!,
        maxReconnectAttempts: 10,
        maxAuthFailureAttempts: 3,
        logger: {
          debug() {},
          info() {},
          warn() {},
          error() {},
        },
      });
      client.on("authenticated", () => {
        connected = true;
      });
      client.on("disconnected", () => {
        connected = false;
      });
      await connectWeCom(
        client,
        bridge,
        botId!,
        logger,
        () => {
          process.exitCode = 1;
          signal();
        },
        {
          ...config.wecom,
          attachmentDir: `${config.stateDir}/attachments`,
          workspace: config.workspace,
          ...(pairing ? { pairing } : {}),
        },
      );
    }
  } catch (error) {
    await stop();
    throw error;
  }
}

main().catch((error: unknown) => {
  console.error(
    error instanceof BridgeError
      ? error.message
      : "启动失败，请检查配置文件、路径与平台连接。",
  );
  process.exitCode = 1;
});
