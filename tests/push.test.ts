import assert from "node:assert/strict";
import test from "node:test";
import { sendExpoPush } from "../lib/push.ts";

test("no push token performs no network call", async () => {
  const originalFetch = globalThis.fetch;
  let called = false;
  globalThis.fetch = async () => {
    called = true;
    return new Response(null, { status: 200 });
  };
  try {
    await sendExpoPush([], "title", "body", {});
    assert.equal(called, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("push message uses the emergency Android channel", async () => {
  const originalFetch = globalThis.fetch;
  let captured: Record<string, unknown>[] = [];
  globalThis.fetch = async (_input, init) => {
    captured = JSON.parse(String(init?.body));
    return new Response(null, { status: 200 });
  };
  try {
    await sendExpoPush(
      ["ExponentPushToken[test]"],
      "전기차 화재 위험 감지",
      "A-01 시험 경보",
      { parkingSpotId: "A-01" },
    );
    assert.equal(captured.length, 1);
    assert.equal(captured[0].channelId, "fire-alerts");
    assert.equal(captured[0].priority, "high");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
