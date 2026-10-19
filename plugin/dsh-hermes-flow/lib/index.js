import { defineTool } from "@deepseek-ai/dsh-tools";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { homedir } from "node:os";

export const name = "hermes-flow";
export const inject = ["tools"];

class Sidecar {
  constructor() {
    this.child = null;
    this.seq = 0;
    this.pending = new Map();
  }

  ensure() {
    if (this.child && !this.child.killed) return;
    const here = dirname(fileURLToPath(import.meta.url));
    const script = resolve(here, "../sidecar/rpc.py");
    const python = process.env.HERMES_FLOW_PYTHON || "python";
    const pluginRoot = process.env.HERMES_FLOW_PLUGIN_ROOT || "E:\\deepSeek\\plugin\\hermes_flow";
    const dataDir = process.env.HERMES_FLOW_DATA_DIR || resolve(homedir(), ".dsh", "plugin-data", "hermes_flow");
    this.child = spawn(python, [script], {
      cwd: resolve(here, ".."),
      env: {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        HERMES_FLOW_PLUGIN_ROOT: pluginRoot,
        HERMES_FLOW_DATA_DIR: dataDir,
      },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.child.stderr.on("data", (d) => {
      const text = String(d).trim();
      if (text) console.error("[hermes-flow sidecar]", text);
    });
    this.child.on("exit", (code) => {
      this.child = null;
      for (const [, p] of this.pending) p.reject(new Error(`sidecar exited (${code})`));
      this.pending.clear();
    });
    createInterface({ input: this.child.stdout }).on("line", (line) => {
      let msg;
      try { msg = JSON.parse(line); } catch { return; }
      const p = this.pending.get(msg.id);
      if (!p) return;
      this.pending.delete(msg.id);
      if (msg.ok) p.resolve(msg.result);
      else p.reject(new Error(msg.error || "sidecar error"));
    });
  }

  call(method, params = {}, timeoutMs = 300_000) {
    this.ensure();
    const id = ++this.seq;
    return new Promise((resolvePromise, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`sidecar timeout: ${method}`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (v) => { clearTimeout(timer); resolvePromise(v); },
        reject: (e) => { clearTimeout(timer); reject(e); },
      });
      this.child.stdin.write(JSON.stringify({ id, method, params }) + "\n");
    });
  }
}

function makeTool(sidecar, name, description, parameters, method, timeoutMs) {
  return defineTool({
    name,
    description,
    parameters,
    output: {
      schema: { type: "string" },
      render: (_args, value) => [{ type: "text", text: String(value) }],
    },
    async execute(args) {
      const result = await sidecar.call(method, args, timeoutMs);
      return JSON.stringify(result, null, 2);
    },
  });
}

export function apply(ctx) {
  const sidecar = new Sidecar();
  const tools = [
    makeTool(sidecar, "hermes_flow_status", "HERMES Flow 运行时状态、Run、数据目录。", {}, "status"),
    makeTool(sidecar, "hermes_flow_agents", "列出 HERMES Flow 专家。", {}, "agents"),
    makeTool(sidecar, "hermes_flow_skills", "列出 HERMES Flow 技能。", {}, "skills"),
    makeTool(sidecar, "hermes_flow_workflows", "列出 HERMES Flow 工作流。", {}, "workflows"),
    makeTool(sidecar, "hermes_flow_scan_project",
      "扫描 Vue 项目文件，排除 node_modules/dist/coverage/.git，返回 files JSON。",
      { project_root: { type: "string", required: true, description: "项目绝对路径" } },
      "scan_project"),
    makeTool(sidecar, "hermes_flow_run_start",
      "创建 Run；files_json 为空时自动扫描 project_root。",
      {
        workflow_id: { type: "string", required: true, description: "工作流 id，默认 vue3-migrate-6phase" },
        project_root: { type: "string", description: "项目绝对路径" },
        files_json: { type: "string", description: "文件数组 JSON 字符串，可省略" },
        title: { type: "string" },
      }, "run_start"),
    makeTool(sidecar, "hermes_flow_batch_plan",
      "为 transform 节点规划批次，返回 group_id。",
      {
        run_id: { type: "string", required: true },
        node_id: { type: "string", required: true },
        policy_json: { type: "string", description: "BatchPolicy JSON，例如 {\"max_files_per_batch\":5}" },
      }, "batch_plan"),
    makeTool(sidecar, "hermes_flow_batch_status", "查看批次组状态。",
      { group_id: { type: "string", required: true } }, "batch_status"),
    makeTool(sidecar, "hermes_flow_quality_collect",
      "真实 build/typecheck/Chrome 路由质量采集；可能耗时 10–60s。",
      {
        project_root: { type: "string", required: true },
        browser: { type: "boolean", description: "是否做 Chrome 路由验证" },
        timeout: { type: "number" },
      }, "quality_collect", 360_000),
    makeTool(sidecar, "hermes_flow_quality_gate",
      "聚合质量门：batch_scores + build/browser。",
      {
        project_root: { type: "string", required: true },
        batch_scores_json: { type: "string", description: "分数数组 JSON，如 [97,96]" },
        coverage: { type: "number" },
        browser: { type: "boolean" },
      }, "quality_gate", 360_000),
    makeTool(sidecar, "hermes_flow_backend", "查看状态内核 / LoopX 后端。", {}, "backend"),
    makeTool(sidecar, "hermes_flow_experience_search", "搜索迁移经验。",
      { query: { type: "string" }, limit: { type: "number" } }, "experience_search"),
    makeTool(sidecar, "hermes_flow_audit", "查看最近越界审计证据。", {}, "audit"),
  ];
  for (const tool of tools) ctx.tools.register(tool);
}
