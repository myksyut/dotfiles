import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createHash } from "node:crypto";
import { mkdirSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import gate, {
	assertPlanGrillReady,
	beginPlanReview,
	endPlanReview,
	expectedPlanPath,
	hashPlanBytes,
	hasUnfencedGrillHeading,
	parseGrillCheckpointFields,
	planGrillIo,
	readCanonicalPlanBytes,
	resetPlanGrill,
} from "../plan-grill-gate.ts";
import planViewer from "../plan-viewer.ts";
import { PlannotatorBridgeError, reviewPlanWithPlannotator } from "../lib/plannotator-client.ts";
import { buildPlanPrompt, PLAN_PROMPT } from "../lib/mode-prompts.ts";

class FakeEventBus {
	private handlers = new Map<string, Set<(data: unknown) => void>>();
	on(channel: string, handler: (data: unknown) => void): () => void {
		const handlers = this.handlers.get(channel) ?? new Set();
		handlers.add(handler);
		this.handlers.set(channel, handlers);
		return () => handlers.delete(handler);
	}
	emit(channel: string, data: unknown): void {
		for (const handler of [...(this.handlers.get(channel) ?? [])]) handler(data);
	}
}

function createFakePi(events = new FakeEventBus()) {
	const tools = new Map<string, any>();
	const commands = new Map<string, any>();
	const handlers = new Map<string, Array<(event: any, ctx: any) => any>>();
	const messages: any[] = [];
	const pi = {
		events,
		registerTool(tool: any) { tools.set(tool.name, tool); },
		registerCommand(name: string, spec: any) { commands.set(name, spec); },
		on(event: string, handler: any) {
			const list = handlers.get(event) ?? [];
			list.push(handler);
			handlers.set(event, list);
		},
		messages,
		sendMessage(message: any) { messages.push(message); },
		tools,
		commands,
		handlers,
		async emit(event: string, payload: any, ctx: any = {}) {
			const results = [];
			for (const handler of handlers.get(event) ?? []) results.push(await handler(payload, ctx));
			return results;
		},
	};
	return pi;
}

function skillDir(): string {
	const dir = join(process.env.HOME!, ".pi", "agent", "skills", "grill-with-docs");
	mkdirSync(dir, { recursive: true });
	writeFileSync(join(dir, "SKILL.md"), "---\nname: grill-with-docs\n---\n# Grill\n", "utf-8");
	return join(dir, "SKILL.md");
}

function writePlan(cwd: string, extra = ""): Buffer {
	const dir = join(cwd, ".context");
	mkdirSync(dir, { recursive: true });
	const planPath = join(dir, "todo.md");
	try { unlinkSync(planPath); } catch {}
	const content = `# Plan\n\nDo the work.\n\n## Grill checkpoint\n\nSummary: bind the gate\nDecisions: keep cwd path\n${extra}`;
	const bytes = Buffer.from(content, "utf8");
	writeFileSync(planPath, bytes);
	return bytes;
}

function bind(cwd: string, bytes: Buffer, summary = "bind the gate", decisions = ["keep cwd path"]) {
	const g = globalThis as any;
	g.__piCurrentMode = "PLAN";
	g.__piPlanGrillComplete = true;
	g.__piPlanGrillCheckpoint = {
		planFilePath: expectedPlanPath(cwd),
		planHash: hashPlanBytes(bytes),
		summary,
		decisions,
		openQuestions: [],
		skillPath: skillDir(),
	};
}

describe("Astra prompts stay without forced 4-scout", () => {
	it("keeps grill mandatory and show_plan approval language", () => {
		expect(PLAN_PROMPT).toContain("## Mandatory grill-with-docs gate");
		expect(PLAN_PROMPT).toContain("Call `show_plan` exactly once");
		expect(PLAN_PROMPT).toContain("plannotator_submit_plan");
		expect(buildPlanPrompt(true)).toContain("## Mandatory grill-with-docs gate");
		expect(buildPlanPrompt(true)).not.toContain("Everything else — spawn **4 scout subagents**");
		expect(buildPlanPrompt(false)).toContain("4 scout subagents");
	});
});

describe("PLAN grill validator", () => {
	const cwd = join(tmpdir(), `grill-cwd-${process.pid}`);
	beforeEach(() => {
		resetPlanGrill();
		mkdirSync(cwd, { recursive: true });
		skillDir();
	});
	afterEach(() => {
		resetPlanGrill();
		(globalThis as any).__piCurrentMode = undefined;
	});

	it("rejects missing checkpoint", () => {
		(globalThis as any).__piCurrentMode = "PLAN";
		writePlan(cwd);
		const ready = assertPlanGrillReady({ cwd, filePath: ".context/todo.md" });
		expect(ready.ok).toBe(false);
		if (!ready.ok) expect(ready.error).toBe("plan_grill_required");
	});

	it("rejects other path and other cwd", () => {
		const bytes = writePlan(cwd);
		bind(cwd, bytes);
		const other = assertPlanGrillReady({ cwd, filePath: "README.md" });
		expect(other.ok).toBe(false);
		if (!other.ok) expect(other.error).toBe("plan_grill_plan_path_required");
		const otherCwd = join(tmpdir(), `grill-other-${process.pid}`);
		mkdirSync(join(otherCwd, ".context"), { recursive: true });
		writeFileSync(join(otherCwd, ".context", "todo.md"), bytes);
		const moved = assertPlanGrillReady({ cwd: otherCwd, filePath: ".context/todo.md" });
		expect(moved.ok).toBe(false);
	});

	it("rejects hash change, inline mismatch, open questions, fenced heading", () => {
		const bytes = writePlan(cwd);
		bind(cwd, bytes);
		writeFileSync(join(cwd, ".context", "todo.md"), Buffer.concat([bytes, Buffer.from("\nedit\n")]));
		const changed = assertPlanGrillReady({ cwd, filePath: expectedPlanPath(cwd) });
		expect(changed.ok).toBe(false);
		if (!changed.ok) expect(changed.error).toBe("plan_grill_hash_mismatch");
		writeFileSync(join(cwd, ".context", "todo.md"), bytes);
		bind(cwd, bytes, "not in file");
		const inline = assertPlanGrillReady({ cwd, filePath: expectedPlanPath(cwd) });
		expect(inline.ok).toBe(false);
		if (!inline.ok) expect(inline.error).toBe("plan_grill_inline_mismatch");
		bind(cwd, bytes);
		(globalThis as any).__piPlanGrillCheckpoint.openQuestions = ["still open"];
		const open = assertPlanGrillReady({ cwd, filePath: expectedPlanPath(cwd) });
		expect(open.ok).toBe(false);
		const fenced = Buffer.from("# Plan\n\n```\n## Grill checkpoint\n```\n", "utf8");
		expect(hasUnfencedGrillHeading(fenced)).toBe(false);
		writeFileSync(join(cwd, ".context", "todo.md"), fenced);
		bind(cwd, fenced);
		const section = assertPlanGrillReady({ cwd, filePath: ".context/todo.md" });
		expect(section.ok).toBe(false);
		if (!section.ok) expect(section.error).toBe("plan_grill_section_required");
	});

	it("rejects symlink escape and non-regular files", () => {
		const bytes = writePlan(cwd);
		bind(cwd, bytes);
		const target = join(tmpdir(), `grill-escape-${process.pid}.md`);
		writeFileSync(target, bytes);
		const planPath = join(cwd, ".context", "todo.md");
		const { unlinkSync } = require("node:fs");
		unlinkSync(planPath);
		symlinkSync(target, planPath);
		const linked = assertPlanGrillReady({ cwd, filePath: ".context/todo.md" });
		expect(linked.ok).toBe(false);
		if (!linked.ok) expect(linked.error).toBe("plan_grill_symlink_escape");
	});

	it("hashes raw bytes and does not collapse invalid UTF-8", () => {
		const bytes = Buffer.concat([
			Buffer.from("# Plan\n\n## Grill checkpoint\n\nSummary: bind the gate\nDecisions: keep cwd path\n", "utf8"),
			Buffer.from([0xff, 0xfe]),
		]);
		mkdirSync(join(cwd, ".context"), { recursive: true });
		try { unlinkSync(join(cwd, ".context", "todo.md")); } catch {}
		writeFileSync(join(cwd, ".context", "todo.md"), bytes);
		bind(cwd, bytes);
		const asUtf8 = bytes.toString("utf8");
		expect(Buffer.from(asUtf8, "utf8").equals(bytes)).toBe(false);
		const ready = assertPlanGrillReady({ cwd, filePath: ".context/todo.md" });
		expect(ready.ok).toBe(true);
		const viaString = assertPlanGrillReady({ cwd, filePath: ".context/todo.md", content: asUtf8 });
		expect(viaString.ok).toBe(false);
	});

	it("accepts the bound plan once and ignores stale completion after reset", () => {
		const bytes = writePlan(cwd);
		bind(cwd, bytes);
		const ready = assertPlanGrillReady({ cwd, filePath: ".context/todo.md" });
		expect(ready.ok).toBe(true);
		const first = beginPlanReview();
		expect(first.ok).toBe(true);
		if (!first.ok) return;
		const second = beginPlanReview();
		expect(second.ok).toBe(false);
		const token = first.token;
		const generation = first.generation;
		resetPlanGrill();
		bind(cwd, bytes);
		endPlanReview(token, true);
		expect((globalThis as any).__piPlanGrillComplete).toBe(true);
		expect((globalThis as any).__piPlanGrillGeneration).not.toBe(generation);
		const fresh = beginPlanReview();
		expect(fresh.ok).toBe(true);
		if (!fresh.ok) return;
		endPlanReview(fresh.token, false);
		expect((globalThis as any).__piPlanGrillComplete).toBe(true);
		endPlanReview(fresh.token, true);
		expect((globalThis as any).__piPlanGrillComplete).toBe(true);
		const again = beginPlanReview();
		expect(again.ok).toBe(true);
		if (!again.ok) return;
		endPlanReview(again.token, true);
		expect((globalThis as any).__piPlanGrillComplete).toBe(false);
	});

	it("does not gate non-PLAN reviews", () => {
		(globalThis as any).__piCurrentMode = "NORMAL";
		const ready = assertPlanGrillReady({ cwd, filePath: "notes.md", content: "# notes\n" });
		expect(ready.ok).toBe(true);
	});
});

describe("registered extension paths", () => {
	const cwd = join(tmpdir(), `grill-ext-${process.pid}`);
	let pi: ReturnType<typeof createFakePi>;

	beforeEach(() => {
		resetPlanGrill();
		mkdirSync(join(cwd, ".context"), { recursive: true });
		skillDir();
		pi = createFakePi();
		gate(pi as any);
		planViewer(pi as any);
		(globalThis as any).__piCurrentMode = "PLAN";
		(globalThis as any).__piAssertPlanGrillReady = assertPlanGrillReady;
		(globalThis as any).__piBeginPlanReview = beginPlanReview;
		(globalThis as any).__piEndPlanReview = endPlanReview;
	});
	afterEach(() => {
		resetPlanGrill();
		(globalThis as any).__piCurrentMode = undefined;
	});

	it("binds via grill_with_docs execute and blocks external plan tools on tool_call", async () => {
		const bytes = writePlan(cwd);
		const grill = pi.tools.get("grill_with_docs");
		const result = await grill.execute("id", {
			plan_file_path: ".context/todo.md",
			summary: "bind the gate",
			decisions: ["keep cwd path"],
			open_questions: [],
		}, undefined, undefined, { cwd });
		expect(result.details.complete).toBe(true);
		expect(result.content[0].text).toContain("Call show_plan");

		const submit = await pi.emit("tool_call", { toolName: "plannotator_submit_plan", input: { file_path: ".context/todo.md" } }, { cwd });
		expect(submit[0].block).toBe(true);
		const review = await pi.emit("tool_call", { toolName: "plannotator_review", input: { file_path: ".context/todo.md" } }, { cwd });
		expect(review[0].block).toBe(true);
		const show = await pi.emit("tool_call", { toolName: "show_plan", input: { file_path: ".context/todo.md" } }, { cwd });
		expect(show[0]).toBeUndefined();
	});

	it("binds Japanese checkpoint fields via grill_with_docs and rejects a different string", async () => {
		const summary = "Astra選択時だけメイン維持";
		const decisions = ["適用はAstraのみ。", "本体ソースで管理する。"];
		const content = `# Plan\n\n## Grill checkpoint\n\nSummary: ${summary}\n\nDecisions:\n\n- ${decisions[0]}\n- ${decisions[1]}\n\nOpen questions: なし。\n`;
		const planPath = join(cwd, ".context", "todo.md");
		try { unlinkSync(planPath); } catch {}
		writeFileSync(planPath, Buffer.from(content, "utf8"));
		const grill = pi.tools.get("grill_with_docs");
		const ok = await grill.execute("id", {
			plan_file_path: ".context/todo.md",
			summary,
			decisions,
			open_questions: [],
		}, undefined, undefined, { cwd });
		expect(ok.details.complete).toBe(true);
		const ready = assertPlanGrillReady({ cwd, filePath: ".context/todo.md" });
		expect(ready.ok).toBe(true);
		const denied = await grill.execute("id", {
			plan_file_path: ".context/todo.md",
			summary: "別の要約",
			decisions,
			open_questions: [],
		}, undefined, undefined, { cwd });
		expect(denied.details.complete).toBe(false);
		expect(denied.details.error).toBe("plan_grill_inline_mismatch");
	});

	it("patches unverified tool_result via return contract, not event.result", async () => {
		const bytes = writePlan(cwd);
		bind(cwd, bytes);
		const patched = await pi.emit("tool_result", {
			type: "tool_result",
			toolName: "show_plan",
			toolCallId: "1",
			input: {},
			content: [{ type: "text", text: "APPROVED" }],
			isError: false,
			details: { approved: true, action: "approved" },
		}, { cwd });
		expect(patched[0].details.approved).toBe(false);
		expect(patched[0].details.action).toBe("declined");
		expect(patched[0].details.error).toBe("plan_grill_unverified_result");
		const boolString = await pi.emit("tool_result", {
			type: "tool_result",
			toolName: "show_plan",
			toolCallId: "2",
			input: {},
			content: [{ type: "text", text: "no" }],
			isError: false,
			details: { approved: "true" },
		}, { cwd });
		expect(boolString[0]).toBeUndefined();
		const unknown = await pi.emit("tool_result", {
			type: "tool_result",
			toolName: "show_plan",
			toolCallId: "3",
			input: {},
			content: [{ type: "text", text: "unknown" }],
			isError: false,
			details: {},
		}, { cwd });
		expect(unknown[0]).toBeUndefined();
		const errored = await pi.emit("tool_result", {
			type: "tool_result",
			toolName: "show_plan",
			toolCallId: "4",
			input: {},
			content: [{ type: "text", text: "err" }],
			isError: true,
			details: { approved: true },
		}, { cwd });
		expect(errored[0]).toBeUndefined();
	});

	it("blocks show_plan without checkpoint and allows non-PLAN annotate-style review tools", async () => {
		writePlan(cwd);
		const blocked = await pi.emit("tool_call", { toolName: "show_plan", input: { file_path: ".context/todo.md" } }, { cwd });
		expect(blocked[0].block).toBe(true);
		(globalThis as any).__piCurrentMode = "NORMAL";
		const annotate = await pi.emit("tool_call", { toolName: "plannotator_submit_plan", input: { file_path: "notes.md" } }, { cwd });
		expect(annotate[0]).toBeUndefined();
		const review = await pi.emit("tool_call", { toolName: "show_plan", input: { file_path: "notes.md" } }, { cwd });
		expect(review[0]).toBeUndefined();
	});

	it("session switch/start/shutdown reset generation so old tokens cannot approve", async () => {
		const bytes = writePlan(cwd);
		const grill = pi.tools.get("grill_with_docs");
		await grill.execute("id", {
			plan_file_path: ".context/todo.md",
			summary: "bind the gate",
			decisions: ["keep cwd path"],
			open_questions: [],
		}, undefined, undefined, { cwd });
		const started = beginPlanReview();
		expect(started.ok).toBe(true);
		if (!started.ok) return;
		await pi.emit("session_switch", {}, { cwd });
		expect((globalThis as any).__piPlanGrillComplete).toBe(false);
		bind(cwd, bytes);
		endPlanReview(started.token, true);
		expect((globalThis as any).__piPlanGrillComplete).toBe(true);
		await pi.emit("session_start", {}, { cwd });
		expect((globalThis as any).__piPlanGrillComplete).toBe(false);
		await pi.emit("session_shutdown", {}, { cwd });
	});
});

describe("reviewPlanWithPlannotator PLAN gate", () => {
	const cwd = join(tmpdir(), `grill-client-${process.pid}`);
	beforeEach(() => {
		resetPlanGrill();
		mkdirSync(cwd, { recursive: true });
		skillDir();
		(globalThis as any).__piAssertPlanGrillReady = assertPlanGrillReady;
		(globalThis as any).__piBeginPlanReview = beginPlanReview;
		(globalThis as any).__piEndPlanReview = endPlanReview;
	});
	afterEach(() => {
		resetPlanGrill();
		(globalThis as any).__piCurrentMode = undefined;
	});

	it("does not start a review without a checkpoint", async () => {
		(globalThis as any).__piCurrentMode = "PLAN";
		writePlan(cwd);
		const events = new FakeEventBus();
		let started = false;
		events.on("plannotator:request", () => { started = true; });
		await expect(reviewPlanWithPlannotator(events, {
			planContent: "# Plan\n",
			planFilePath: ".context/todo.md",
			cwd,
		})).rejects.toBeInstanceOf(PlannotatorBridgeError);
		expect(started).toBe(false);
	});

	it("starts exactly one review for a valid checkpoint, deny keeps bound, abort is not approval", async () => {
		const bytes = writePlan(cwd);
		bind(cwd, bytes);
		const events = new FakeEventBus();
		events.on("plannotator:request", (data: any) => {
			data.respond({ status: "handled", result: { status: "pending", reviewId: "r1" } });
			queueMicrotask(() => {
				events.emit("plannotator:review-result", { reviewId: "r1", approved: true });
			});
		});
		const result = await reviewPlanWithPlannotator(events, {
			planContent: bytes.toString("utf8"),
			planFilePath: expectedPlanPath(cwd),
			planBytes: bytes,
			cwd,
		});
		expect(result.approved).toBe(true);
		expect((globalThis as any).__piPlanGrillComplete).toBe(false);
		expect(createHash("sha256").update(bytes).digest("hex")).toBe(hashPlanBytes(bytes));

		bind(cwd, bytes);
		const denyBus = new FakeEventBus();
		denyBus.on("plannotator:request", (data: any) => {
			data.respond({ status: "handled", result: { status: "pending", reviewId: "r2" } });
			queueMicrotask(() => {
				denyBus.emit("plannotator:review-result", { reviewId: "r2", approved: false, feedback: "no" });
			});
		});
		const denied = await reviewPlanWithPlannotator(denyBus, {
			planContent: bytes.toString("utf8"),
			planFilePath: expectedPlanPath(cwd),
			planBytes: bytes,
			cwd,
		});
		expect(denied.approved).toBe(false);
		expect((globalThis as any).__piPlanGrillComplete).toBe(true);

		const abortBus = new FakeEventBus();
		const ac = new AbortController();
		abortBus.on("plannotator:request", (data: any) => {
			data.respond({ status: "handled", result: { status: "pending", reviewId: "r3" } });
			ac.abort();
		});
		await expect(reviewPlanWithPlannotator(abortBus, {
			planContent: bytes.toString("utf8"),
			planFilePath: expectedPlanPath(cwd),
			planBytes: bytes,
			cwd,
			signal: ac.signal,
		})).rejects.toBeInstanceOf(PlannotatorBridgeError);
		expect((globalThis as any).__piPlanGrillComplete).toBe(true);
	});
});


describe("grill checkpoint section parse", () => {
	it("accepts user plan Summary/Decisions list and Open questions none", () => {
		const bytes = Buffer.from(`# Plan\n\nbody Summary: not this\n\n## Grill checkpoint\n\nSummary: bind the gate.\n\nDecisions:\n\n- keep cwd path\n- second call\n\nOpen questions: なし。\n`, "utf8");
		const parsed = parseGrillCheckpointFields(bytes);
		expect(parsed).toEqual({
			summary: "bind the gate.",
			decisions: ["keep cwd path", "second call"],
			openQuestions: [],
		});
	});

	it("ignores fenced headings with backticks and tildes", () => {
		const bytes = Buffer.from("# Plan\n\n```\n## Grill checkpoint\nSummary: fenced\n```\n\n~~~info\n## Grill checkpoint\nSummary: tilde\n~~~\n\n## Grill checkpoint\n\nSummary: real summary.\nDecisions: only this\n", "utf8");
		expect(hasUnfencedGrillHeading(bytes)).toBe(true);
		expect(parseGrillCheckpointFields(bytes)).toEqual({
			summary: "real summary.",
			decisions: ["only this"],
			openQuestions: [],
		});
	});

	it("decodes Japanese Summary/Decisions as UTF-8", () => {
		const bytes = Buffer.from("# Plan\n\n## Grill checkpoint\n\nSummary: Astra選択時だけメイン維持\n\nDecisions:\n\n- 適用はAstraのみ。\n- 本体ソースで管理する。\n\nOpen questions: なし。\n", "utf8");
		expect(parseGrillCheckpointFields(bytes)).toEqual({
			summary: "Astra選択時だけメイン維持",
			decisions: ["適用はAstraのみ。", "本体ソースで管理する。"],
			openQuestions: [],
		});
	});

	it("rejects invalid UTF-8 in checkpoint field values", () => {
		const bytes = Buffer.concat([
			Buffer.from("# Plan\n\n## Grill checkpoint\n\nSummary: ", "utf8"),
			Buffer.from([0xff, 0xfe]),
			Buffer.from("\nDecisions: keep cwd path\n", "utf8"),
		]);
		expect(parseGrillCheckpointFields(bytes)).toBeUndefined();
	});

	it("rejects tool args that appear only outside the checkpoint section", () => {
		const cwd = join(tmpdir(), `grill-outside-${process.pid}`);
		mkdirSync(join(cwd, ".context"), { recursive: true });
		const bytes = Buffer.from("# Plan\n\nSummary: bind the gate.\nDecisions: keep cwd path\n\n## Grill checkpoint\n\nSummary: other summary.\nDecisions: other decision\n", "utf8");
		writeFileSync(join(cwd, ".context", "todo.md"), bytes);
		bind(cwd, bytes, "bind the gate", ["keep cwd path"]);
		const ready = assertPlanGrillReady({ cwd, filePath: ".context/todo.md" });
		expect(ready.ok).toBe(false);
		if (!ready.ok) expect(ready.error).toBe("plan_grill_inline_mismatch");
	});
});

describe("TOCTOU fd read", () => {
	const cwd = join(tmpdir(), `grill-toctou-${process.pid}`);
	afterEach(() => {
		resetPlanGrill();
		(globalThis as any).__piCurrentMode = undefined;
	});

	it("rejects inode swap after open/read", () => {
		mkdirSync(join(cwd, ".context"), { recursive: true });
		skillDir();
		const bytes = writePlan(cwd);
		bind(cwd, bytes);
		const file = join(cwd, ".context", "todo.md");
		const real = {
			openSync: planGrillIo.openSync,
			fstatSync: planGrillIo.fstatSync,
			readSync: planGrillIo.readSync,
			closeSync: planGrillIo.closeSync,
			lstatSync: planGrillIo.lstatSync,
			realpathSync: planGrillIo.realpathSync,
		};
		let afterRead = false;
		planGrillIo.readSync = ((fd: number, buf: Buffer, offset: number, length: number, position: number) => {
			const n = real.readSync(fd, buf, offset, length, position);
			afterRead = true;
			return n;
		}) as typeof planGrillIo.readSync;
		planGrillIo.lstatSync = ((path: any) => {
			const st = real.lstatSync(path);
			if (afterRead && real.realpathSync(path) === real.realpathSync(file)) {
				return Object.assign(Object.create(Object.getPrototypeOf(st)), st, {
					ino: st.ino + 99,
					isFile: () => true,
					isSymbolicLink: () => false,
					isDirectory: () => false,
				});
			}
			return st;
		}) as typeof planGrillIo.lstatSync;
		try {
			const loaded = readCanonicalPlanBytes(cwd, ".context/todo.md");
			expect(loaded.ok).toBe(false);
			if (!loaded.ok) expect(loaded.error).toBe("plan_grill_toctou");
		} finally {
			Object.assign(planGrillIo, real);
		}
	});
});

describe("stale approval does not notify", () => {
	it("drops late approve after session switch before UI/tool result", async () => {
		const cwd = join(tmpdir(), `grill-stale-${process.pid}`);
		mkdirSync(join(cwd, ".context"), { recursive: true });
		skillDir();
		const events = new FakeEventBus();
		const pi = createFakePi(events);
		gate(pi as any);
		planViewer(pi as any);
		(globalThis as any).__piCurrentMode = "PLAN";
		(globalThis as any).__piAssertPlanGrillReady = assertPlanGrillReady;
		(globalThis as any).__piBeginPlanReview = beginPlanReview;
		(globalThis as any).__piEndPlanReview = endPlanReview;
		writePlan(cwd);
		await pi.tools.get("grill_with_docs").execute("id", {
			plan_file_path: ".context/todo.md",
			summary: "bind the gate",
			decisions: ["keep cwd path"],
			open_questions: [],
		}, undefined, undefined, { cwd });
		events.on("plannotator:request", (data: any) => {
			data.respond({ status: "handled", result: { status: "pending", reviewId: "late" } });
		});
		const running = pi.tools.get("show_plan").execute("id", { file_path: ".context/todo.md" }, undefined, undefined, { cwd });
		await new Promise((resolve) => setTimeout(resolve, 0));
		const generation = (globalThis as any).__piPlanGrillGeneration;
		await pi.emit("session_switch", {}, { cwd });
		expect((globalThis as any).__piPlanGrillComplete).toBe(false);
		expect((globalThis as any).__piPlanGrillGeneration).not.toBe(generation);
		events.emit("plannotator:review-result", { reviewId: "late", approved: true });
		const result = await running;
		expect(result.details?.action).not.toBe("approved");
		expect(pi.messages.filter((m) => m?.customType === "plan-approved")).toEqual([]);
		expect((globalThis as any).__piPlanGrillComplete).toBe(false);
	});
});
