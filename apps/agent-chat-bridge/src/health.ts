import { createServer } from "node:http";
import type { Server } from "node:http";

export async function startHealthServer(
  port: number,
  state: () => { connected: boolean; accepting: boolean; running: number },
): Promise<Server> {
  const server = createServer((request, response) => {
    const snapshot = state();
    if (
      request.method !== "GET" ||
      !["/healthz", "/metrics"].includes(request.url ?? "")
    ) {
      response.writeHead(404).end();
      return;
    }
    const healthy = snapshot.connected && snapshot.accepting;
    response.writeHead(request.url === "/healthz" && !healthy ? 503 : 200, {
      "content-type": "application/json",
    });
    response.end(
      JSON.stringify(
        request.url === "/healthz"
          ? { status: healthy ? "ok" : "unavailable" }
          : snapshot,
      ),
    );
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      server.off("error", reject);
      resolve();
    });
  });
  return server;
}
