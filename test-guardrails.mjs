#!/usr/bin/env node
/**
 * Guardrails unit tests — run with: node test-guardrails.mjs
 * No external dependencies required; uses the compiled dist files.
 */

import assert from "node:assert/strict";

// ── helpers ──────────────────────────────────────────────────────────────────

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${err.message}`);
    failed++;
  }
}

function assertThrows(fn, msgFragment) {
  let threw = false;
  try { fn(); } catch (err) {
    threw = true;
    if (msgFragment && !err.message.includes(msgFragment)) {
      throw new Error(`Expected message containing "${msgFragment}", got: "${err.message}"`);
    }
  }
  if (!threw) throw new Error("Expected function to throw but it did not");
}

// ── import compiled modules ───────────────────────────────────────────────────

const { filterTools, loadGuardrailsConfig, validateToolArguments, assertToolCallAllowed } =
  await import("./dist/guardrails.js");

// ── loadGuardrailsConfig ──────────────────────────────────────────────────────

console.log("\nloadGuardrailsConfig");

test("defaults to readonly when DEVSTACK_MODE is unset", () => {
  const cfg = loadGuardrailsConfig({});
  assert.equal(cfg.mode, "readonly");
});

test("parses workshop mode", () => {
  const cfg = loadGuardrailsConfig({ DEVSTACK_MODE: "workshop" });
  assert.equal(cfg.mode, "workshop");
});

test("parses full mode", () => {
  const cfg = loadGuardrailsConfig({ DEVSTACK_MODE: "full" });
  assert.equal(cfg.mode, "full");
});

test("throws on invalid mode", () => {
  assertThrows(
    () => loadGuardrailsConfig({ DEVSTACK_MODE: "superuser" }),
    "Invalid DEVSTACK_MODE",
  );
});

test("parses DEVSTACK_TOOLS csv into a Set", () => {
  const cfg = loadGuardrailsConfig({ DEVSTACK_TOOLS: "jira_myself, jira_get_issue" });
  assert.ok(cfg.allowedTools instanceof Set);
  assert.ok(cfg.allowedTools.has("jira_myself"));
  assert.ok(cfg.allowedTools.has("jira_get_issue"));
});

// ── filterTools ───────────────────────────────────────────────────────────────

console.log("\nfilterTools");

const mockTools = [
  { name: "jira_myself",      description: "", inputSchema: { type: "object", properties: {} }, handler: async () => {} },
  { name: "jira_create_issue",description: "", inputSchema: { type: "object", properties: {} }, handler: async () => {} },
  { name: "jira_delete_issue",description: "", inputSchema: { type: "object", properties: {} }, handler: async () => {} },
  { name: "confluence_add_comment", description: "", inputSchema: { type: "object", properties: {} }, handler: async () => {} },
];

test("readonly mode hides write tools", () => {
  const { tools, hidden } = filterTools(mockTools, { mode: "readonly" });
  assert.ok(tools.some(t => t.name === "jira_myself"));
  assert.ok(!tools.some(t => t.name === "jira_create_issue"));
  assert.ok(!tools.some(t => t.name === "jira_delete_issue"));
  assert.ok(hidden.length >= 2);
});

test("workshop mode shows read + create/comment but not delete", () => {
  const { tools } = filterTools(mockTools, { mode: "workshop" });
  assert.ok(tools.some(t => t.name === "jira_myself"));
  assert.ok(tools.some(t => t.name === "jira_create_issue"));
  assert.ok(tools.some(t => t.name === "confluence_add_comment"));
  assert.ok(!tools.some(t => t.name === "jira_delete_issue"));
});

test("full mode shows all tools", () => {
  const { tools } = filterTools(mockTools, { mode: "full" });
  assert.equal(tools.length, mockTools.length);
});

test("DEVSTACK_TOOLS allowlist takes precedence", () => {
  const cfg = { mode: "full", allowedTools: new Set(["jira_myself"]) };
  const { tools } = filterTools(mockTools, cfg);
  assert.equal(tools.length, 1);
  assert.equal(tools[0].name, "jira_myself");
});

// ── validateToolArguments ─────────────────────────────────────────────────────

console.log("\nvalidateToolArguments");

const searchTool = {
  name: "jira_search_issues",
  description: "",
  inputSchema: {
    type: "object",
    properties: {
      jql: { type: "string" },
      maxResults: { type: "number" },
    },
    required: ["jql"],
  },
  handler: async () => {},
};

test("accepts valid args", () => {
  const args = validateToolArguments(searchTool, { jql: "project = DEV", maxResults: 10 });
  assert.equal(args.jql, "project = DEV");
});

test("throws when required arg is missing", () => {
  assertThrows(() => validateToolArguments(searchTool, {}), 'Missing required argument "jql"');
});

test("throws on unexpected argument", () => {
  assertThrows(
    () => validateToolArguments(searchTool, { jql: "x", extra: "bad" }),
    'Unexpected argument "extra"',
  );
});

test("throws when maxResults is out of range", () => {
  assertThrows(
    () => validateToolArguments(searchTool, { jql: "x", maxResults: 200 }),
    "maxResults",
  );
});

test("throws when jql is not a string", () => {
  assertThrows(
    () => validateToolArguments(searchTool, { jql: 42 }),
    "expected string",
  );
});

// ── assertToolCallAllowed ─────────────────────────────────────────────────────

console.log("\nassertToolCallAllowed");

test("allows read tool in readonly mode", () => {
  assertToolCallAllowed(
    { name: "jira_myself", description: "", inputSchema: { type: "object", properties: {} }, handler: async () => {} },
    {},
    { mode: "readonly" },
  );
});

test("throws for write tool in readonly mode", () => {
  assertThrows(
    () =>
      assertToolCallAllowed(
        { name: "jira_create_issue", description: "", inputSchema: { type: "object", properties: {} }, handler: async () => {} },
        {},
        { mode: "readonly" },
      ),
    "not available",
  );
});

// ── summary ───────────────────────────────────────────────────────────────────

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
