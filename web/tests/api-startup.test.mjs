import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

// Execute the actual TypeScript modules with fake network/React boundaries: no credits used.
function load(file, imports, globals = {}) {
  const source = fs.readFileSync(path.join(import.meta.dirname, "../src", file), "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const compiledModule = { exports: {} };
  vm.runInNewContext(code, {
    module: compiledModule, exports: compiledModule.exports,
    require: (name) => {
      assert.ok(name in imports, `Unexpected import: ${name}`);
      return imports[name];
    },
    AbortController, DOMException, setTimeout, clearTimeout, performance, ...globals,
  }, { filename: file });
  return compiledModule.exports;
}

const api = { API_URL: "https://price-engine.example" };
const ready = { model: "ready", serpapi_key_configured: true };
const response = (body, ok = true) => ({ ok, json: async () => body });

test("503 and warming responses are retried using health only", async () => {
  const urls = [];
  const responses = [response(null, false), response({ model: "warming" }), response(ready)];
  const { waitForApiReady } = load("lib/apiReady.ts", { "./api": api }, {
    fetch: async (url) => { urls.push(url); return responses.shift(); },
  });
  await waitForApiReady({ signal: new AbortController().signal, retryMs: 1 });
  assert.deepEqual(urls, Array(3).fill(`${api.API_URL}/api/health`));
});

test("a hung health request times out and can recover", async () => {
  let calls = 0;
  const { waitForApiReady } = load("lib/apiReady.ts", { "./api": api }, {
    fetch: async (_url, { signal }) => {
      if (++calls > 1) return response(ready);
      return new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(new DOMException("Timeout", "AbortError"))));
    },
  });
  await waitForApiReady({ signal: new AbortController().signal, requestTimeoutMs: 5, retryMs: 1 });
  assert.equal(calls, 2);
});

test("startup is bounded and cancellation stops polling", async () => {
  let calls = 0;
  const { waitForApiReady } = load("lib/apiReady.ts", { "./api": api }, {
    fetch: async () => { calls++; return response(null, false); },
  });
  await assert.rejects(waitForApiReady({ signal: new AbortController().signal, timeoutMs: 10, retryMs: 1 }), /temporarily unavailable/);
  const controller = new AbortController();
  const pending = waitForApiReady({ signal: controller.signal, retryMs: 100 });
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
  const stoppedAt = calls;
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(calls, stoppedAt);
});

test("failed model never permits a search", async () => {
  const { waitForApiReady } = load("lib/apiReady.ts", { "./api": api }, {
    fetch: async () => response({ model: "failed" }),
  });
  await assert.rejects(waitForApiReady({ signal: new AbortController().signal }), /temporarily unavailable/);
});

test("page mount wakes in the background and unmount cancels it", () => {
  let cleanup;
  let signal;
  const { default: WakeApi } = load("components/shell/WakeApi.tsx", {
    react: { useEffect: (effect) => { cleanup = effect(); } },
    "@/lib/apiReady": { waitForApiReady: (options) => {
      signal = options.signal;
      return Promise.resolve();
    } },
  });
  assert.equal(WakeApi(), null);
  assert.equal(signal.aborted, false);
  cleanup();
  assert.equal(signal.aborted, true);
});

for (const [file, hook, args, endpoint] of [
  ["useSearch", "useSearch", ["Dolo 650", "110001", false], "search"],
  ["usePrescription", "usePrescription", [[{ q: "Dolo 650", tablets: 10 }], "110001", false], "prescription"],
]) {
  function harness(waitForApiReady) {
    let state;
    const cleanups = [];
    const streams = [];
    class EventSource {
      static CLOSED = 2;
      readyState = 0;
      constructor(url) { this.url = url; streams.push(this); }
      addEventListener() {}
      close() { this.readyState = EventSource.CLOSED; }
    }
    const react = {
      useCallback: (fn) => fn,
      useRef: () => ({ current: null }),
      useState: (initial) => {
        state = initial;
        return [initial, (update) => { state = typeof update === "function" ? update(state) : update; }];
      },
      useEffect: (effect) => cleanups.push(effect()),
    };
    const loadedHook = load(`lib/${file}.ts`, {
      react, "./api": api, "./apiReady": { waitForApiReady },
    }, { EventSource });
    return { ...loadedHook[hook](), streams, cleanups, state: () => state };
  }

  test(`${endpoint}: wait before opening exactly one search stream; never auto-replay`, async () => {
    let finishWake;
    const h = harness(() => new Promise((resolve) => { finishWake = resolve; }));
    const pending = h.run(...args);
    assert.equal(h.state().waking, true);
    assert.equal(h.streams.length, 0);
    finishWake();
    await pending;
    assert.equal(h.state().waking, false);
    assert.equal(h.streams.length, 1);
    assert.ok(h.streams[0].url.includes(`/api/${endpoint}/stream?`));
    h.streams[0].onopen();
    h.streams[0].onerror();
    assert.equal(h.state().status, "error");
    assert.equal(h.streams.length, 1);
  });

  test(`${endpoint}: unmount and replacement cancel queued searches`, async () => {
    const wakeups = [];
    const h = harness(() => new Promise((resolve) => wakeups.push(resolve)));
    const first = h.run(...args);
    const second = h.run(...args);
    wakeups[0]();
    await first;
    assert.equal(h.streams.length, 0);
    h.cleanups.forEach((cleanup) => cleanup());
    wakeups[1]();
    await second;
    assert.equal(h.streams.length, 0);
  });

  test(`${endpoint}: unavailable API gives an app error without sending a search`, async () => {
    const h = harness(async () => { throw new Error("temporarily unavailable"); });
    await h.run(...args);
    assert.equal(h.state().status, "error");
    assert.equal(h.state().waking, false);
    assert.equal(h.streams.length, 0);
  });
}
