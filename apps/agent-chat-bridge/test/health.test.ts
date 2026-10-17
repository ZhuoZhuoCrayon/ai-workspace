import test from "node:test";
import assert from "node:assert/strict";
import { startHealthServer } from "../src/health.js";

test("健康检查只绑定环回，连接丢失和停机反映为不可用", async () => {
  let connected = true,
    accepting = true;
  const server = await startHealthServer(0, () => ({
    connected,
    accepting,
    running: 2,
  }));
  const address = server.address();
  assert(address && typeof address !== "string");
  assert.equal(address.address, "127.0.0.1");
  const root = `http://127.0.0.1:${address.port}`;
  try {
    assert.equal((await fetch(`${root}/healthz`)).status, 200);
    connected = false;
    assert.equal((await fetch(`${root}/healthz`)).status, 503);
    connected = true;
    accepting = false;
    assert.equal((await fetch(`${root}/healthz`)).status, 503);
    assert.deepEqual(await (await fetch(`${root}/metrics`)).json(), {
      connected: true,
      accepting: false,
      running: 2,
    });
    assert.equal((await fetch(`${root}/unknown`)).status, 404);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
