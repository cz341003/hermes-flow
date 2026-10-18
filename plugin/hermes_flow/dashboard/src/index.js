/* HERMES Flow Dashboard v2 — expert / skills / workflows / runs / quality / memory / settings.
 * React is provided by the host SDK; this bundle ships no React.
 */
(function () {
  "use strict";
  var sdk = window.__HERMES_PLUGIN_SDK__ || {};
  var React = sdk.React;
  var hooks = sdk.hooks || React || {};
  var h = React && React.createElement;
  var API = "/api/plugins/hermes_flow";

  function css(name) { return "hf2-" + name; }
  function fmt(ts) {
    if (!ts) return "-";
    try { return new Date(ts * (ts < 1e12 ? 1000 : 1)).toLocaleString(); } catch (e) { return String(ts); }
  }
  function jsonText(v) { try { return JSON.stringify(v, null, 2); } catch (e) { return String(v); } }
  function token() {
    if (window.__HERMES_SESSION_TOKEN__) return window.__HERMES_SESSION_TOKEN__;
    try { return (document.cookie.match(/hermes[_-]?session[_-]?token=([^;]+)/i) || [])[1] || ""; } catch (e) { return ""; }
  }
  function api(path, opts) {
    opts = opts || {};
    var headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    var t = token();
    if (t) headers["X-Hermes-Session-Token"] = t;
    return fetch(API + path, Object.assign({}, opts, { headers: headers })).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = { raw: text }; }
        if (!res.ok) {
          var msg = (data && (data.detail || data.error)) || (res.status + " " + res.statusText);
          throw new Error(typeof msg === "string" ? msg : jsonText(msg));
        }
        if (data && data.ok === false) throw new Error(data.error || "request failed");
        return data && Object.prototype.hasOwnProperty.call(data, "data") ? data.data : data;
      });
    });
  }

  function layoutPositions(def) {
    var pos = {};
    var nodes = (def && def.nodes) || [];
    nodes.forEach(function (n, i) {
      var meta = n.meta || {};
      var x = typeof meta.x === "number" ? meta.x : 16 + (i % 4) * 190;
      var y = typeof meta.y === "number" ? meta.y : 14 + Math.floor(i / 4) * 86;
      pos[n.id] = { x: x, y: y };
    });
    return pos;
  }

  function Badge(props) {
    var tone = props.tone || "idle";
    return h("span", { className: css("badge") + " " + css("badge-" + tone) }, props.children);
  }
  function Stat(props) {
    return h("div", { className: css("stat") },
      h("div", { className: css("stat-k") }, props.label),
      h("div", { className: css("stat-v") }, props.value == null ? "—" : String(props.value)),
      props.foot ? h("div", { className: css("stat-f") }, props.foot) : null);
  }
  function Panel(props) {
    return h("section", { className: css("panel") },
      h("div", { className: css("panel-hd") },
        h("div", null, h("div", { className: css("panel-title") }, props.title),
          props.sub ? h("div", { className: css("panel-sub") }, props.sub) : null),
        props.right || null),
      h("div", { className: css("panel-bd") }, props.children));
  }
  function Empty(props) { return h("div", { className: css("empty") }, props.children || "暂无数据"); }
  function AgentCard(props) {
    var a = props.agent || {};
    var active = props.active || [];
    var skills = (a.skills || []).map(function (sk) {
      return h("span", { key: sk, className: css("chip") }, sk);
    });
    var rows = active.map(function (x) {
      return h("div", { key: x.group_id }, h("b", null, x.node_id), " · " + x.done + "/" + x.total + " 批 · " + x.status);
    });
    return h("article", { className: css("agent") },
      h("div", { className: css("agent-hd") },
        h("div", { className: css("avatar") }, (a.name || "?").slice(0, 1)),
        h("div", null,
          h("div", { className: css("agent-name") }, a.name),
          h("div", { className: css("muted") }, a.id + " · " + (a.model || "-"))),
        active.length ? h(Badge, { tone: "ok" }, "活跃") : h(Badge, { tone: "idle" }, "空闲")),
      h("p", { className: css("agent-role") }, a.role || a.description || ""),
      h("div", { className: css("chips") }, skills),
      h("div", { className: css("agent-ft") },
        h("span", null, "批次 " + ((a.loop_policy || {}).max_files_per_batch || 1) + " 文件/批"),
        h("span", null, "轮次 " + (a.max_turns || "-"))),
      active.length ? h("div", { className: css("active-line") }, rows) : null);
  }  function ErrorBanner(props) {
    if (!props.error) return null;
    return h("div", { className: css("banner") }, h("b", null, "请求失败："), " " + props.error,
      h("button", { className: css("btn") + " " + css("btn-sm"), onClick: props.onRetry }, "重试"));
  }

  function App() {
    var useState = hooks.useState, useEffect = hooks.useEffect, useCallback = hooks.useCallback;
    var tabState = useState("experts"), tab = tabState[0], setTab = tabState[1];
    var dataState = useState({ status: null, agents: [], skills: [], workflows: [], runs: [], agentStatus: [], quality: [], audit: [], drivers: [], settings: null });
    var data = dataState[0], setData = dataState[1];
    var errState = useState(""), error = errState[0], setError = errState[1];
    var busyState = useState(""), busy = busyState[0], setBusy = busyState[1];
    var runIdState = useState(""), runId = runIdState[0], setRunId = runIdState[1];
    var runState = useState(null), run = runState[0], setRun = runState[1];
    var batchState = useState(null), selectedBatch = batchState[0], setSelectedBatch = batchState[1];
    var batchItemsState = useState([]), batchItems = batchItemsState[0], setBatchItems = batchItemsState[1];
    var skillState = useState(null), skill = skillState[0], setSkill = skillState[1];
    var wfState = useState(null), wfDetail = wfState[0], setWfDetail = wfState[1];
    var wfJsonState = useState(""), wfJson = wfJsonState[0], setWfJson = wfJsonState[1];
    var wfPosState = useState({}), wfPos = wfPosState[0], setWfPos = wfPosState[1];
    var wfSelState = useState(null), wfSel = wfSelState[0], setWfSel = wfSelState[1];
    var wfMsgState = useState(""), wfMsg = wfMsgState[0], setWfMsg = wfMsgState[1];
    var eventsState = useState([]), events = eventsState[0], setEvents = eventsState[1];
    var qualityResultState = useState(null), qualityResult = qualityResultState[0], setQualityResult = qualityResultState[1];
    var qJobState = useState(null), qJob = qJobState[0], setQJob = qJobState[1];
    var qProjectState = useState(""), qProject = qProjectState[0], setQProject = qProjectState[1];
    var qBrowserState = useState(true), qBrowser = qBrowserState[0], setQBrowser = qBrowserState[1];
    var memRowsState = useState([]), memRows = memRowsState[0], setMemRows = memRowsState[1];
    var memQueryState = useState(""), memQuery = memQueryState[0], setMemQuery = memQueryState[1];
    var memFormState = useState({ category: "antdv", trigger: "", solution: "", phase: "transform" });
    var memForm = memFormState[0], setMemForm = memFormState[1];
    var agentFormState = useState({ name: "", role: "", description: "", skills: "", model: "" });
    var agentForm = agentFormState[0], setAgentForm = agentFormState[1];
    var agentMsgState = useState(""), agentMsg = agentMsgState[0], setAgentMsg = agentMsgState[1];
    var skillFormState = useState({ name: "", description: "", phases: "transform", tags: "", body: "## Procedure\n1. \n\n## Pitfalls\n- \n\n## Verification\n- " });
    var skillForm = skillFormState[0], setSkillForm = skillFormState[1];
    var skillMsgState = useState(""), skillMsg = skillMsgState[0], setSkillMsg = skillMsgState[1];
    var wfNewState = useState({ id: "", name: "", description: "" });
    var wfNew = wfNewState[0], setWfNew = wfNewState[1];
    var runFormState = useState({ workflow_id: "vue3-migrate-6phase", title: "迁移 Run", project_root: "", files: '[{"path":"src/App.vue","size":800}]' });
    var runForm = runFormState[0], setRunForm = runFormState[1];

    var refresh = useCallback(function () {
      var jobs = [
        api("/status").catch(function () { return null; }),
        api("/agents").catch(function (e) { setError(e.message); return { agents: [] }; }),
        api("/skills").catch(function () { return { skills: [] }; }),
        api("/workflows").catch(function () { return { workflows: [] }; }),
        api("/runs").catch(function () { return { runs: [] }; }),
        api("/agent-status").catch(function () { return { agents: [] }; }),
        api("/quality?limit=10").catch(function () { return { items: [] }; }),
        api("/audit?limit=10").catch(function () { return { items: [] }; }),
        api("/drivers").catch(function () { return { locks: [] }; }),
        api("/settings").catch(function () { return null; })
      ];
      return Promise.all(jobs).then(function (r) {
        setData({
          status: r[0], agents: (r[1] || {}).agents || [], skills: (r[2] || {}).skills || [],
          workflows: (r[3] || {}).workflows || [], runs: (r[4] || {}).runs || [],
          agentStatus: (r[5] || {}).agents || [], quality: (r[6] || {}).items || [],
          audit: (r[7] || {}).items || [], drivers: (r[8] || {}).locks || [], settings: r[9]
        });
      });
    }, []);

    useEffect(function () { refresh(); var t = setInterval(refresh, 5000); return function () { clearInterval(t); }; }, [refresh]);

    useEffect(function () {
      if (!runId && data.runs.length) setRunId(data.runs[0].id);
      if (!qProject && run && run.project_root) setQProject(run.project_root);
    }, [runId, data.runs, run, qProject]);

    useEffect(function () {
      if (!runId) { setRun(null); setEvents([]); return; }
      api("/runs/" + encodeURIComponent(runId)).then(setRun).catch(function (e) { setError(e.message); });
    }, [runId]);

    useEffect(function () {
      if (!runId) return undefined;
      var active = true;
      var cursor = 0;
      setEvents([]);
      function tick() {
        api("/runs/" + encodeURIComponent(runId) + "/events?after=" + cursor).then(function (d) {
          if (!active || !d) return;
          if (d.events && d.events.length) {
            cursor = d.last_seq || cursor;
            setEvents(function (prev) { return prev.concat(d.events).slice(-200); });
          }
        }).catch(function () { /* 断线保持 cursor，下一 tick 继续补齐 */ });
      }
      tick();
      var timer = setInterval(tick, 2500);
      return function () { active = false; clearInterval(timer); };
    }, [runId]);

    useEffect(function () {
      if (!selectedBatch) { setBatchItems([]); return; }
      api("/batches/" + encodeURIComponent(selectedBatch) + "/items")
        .then(function (d) { setBatchItems((d && d.items) || []); })
        .catch(function (e) { setError(e.message); });
    }, [selectedBatch]);

    function act(label, fn) {
      setBusy(label); setError("");
      fn().then(function () { return refresh(); }).catch(function (e) { setError(e.message); })
        .then(function () { setBusy(""); });
    }
    function goRun(id) { setRunId(id); setTab("runs"); }
    function loadSkill(id) {
      setSkill({ loading: true, id: id });
      api("/skills/" + encodeURIComponent(id)).then(setSkill).catch(function (e) { setError(e.message); });
    }
    function loadWorkflow(id) {
      api("/workflows/" + encodeURIComponent(id)).then(function (w) {
        setWfDetail(w);
        setWfJson(w && w.definition ? JSON.stringify(w.definition, null, 2) : "");
        setWfPos(layoutPositions(w && w.definition));
        setWfSel(null);
        setWfMsg("");
      }).catch(function (e) { setError(e.message); });
    }
    function updateWfDef(mutator) {
      var def;
      try { def = JSON.parse(wfJson); } catch (e) { setWfMsg("JSON 无效: " + e.message); return; }
      mutator(def);
      setWfJson(JSON.stringify(def, null, 2));
      setWfPos(layoutPositions(def));
    }
    function addWfNode() {
      updateWfDef(function (def) {
        def.nodes = def.nodes || [];
        var i = 1, ids = {};
        (def.nodes || []).forEach(function (n) { ids[n.id] = 1; });
        while (ids["node-" + i]) i++;
        def.nodes.push({ id: "node-" + i, name: "新节点 " + i, phase: "transform",
                         agent: "code-transformer", meta: { x: 20, y: 20 + def.nodes.length * 70 } });
      });
      setWfMsg("已添加节点（记得保存）");
    }
    function deleteWfNode() {
      if (!wfSel) return;
      updateWfDef(function (def) {
        def.nodes = (def.nodes || []).filter(function (n) { return n.id !== wfSel; });
        def.edges = (def.edges || []).filter(function (e) { return e.source !== wfSel && e.target !== wfSel; });
      });
      setWfSel(null);
      setWfMsg("已删除节点（记得保存）");
    }
    function dropWfNode(e) {
      e.preventDefault();
      var nid = e.dataTransfer.getData("text/plain");
      if (!nid) return;
      var rect = e.currentTarget.getBoundingClientRect();
      var x = Math.max(4, Math.round(e.clientX - rect.left - 70));
      var y = Math.max(4, Math.round(e.clientY - rect.top - 24));
      setWfPos(Object.assign({}, wfPos, (function () { var p = {}; p[nid] = { x: x, y: y }; return p; })()));
      updateWfDef(function (def) {
        (def.nodes || []).forEach(function (n) {
          if (n.id === nid) n.meta = Object.assign({}, n.meta || {}, { x: x, y: y });
        });
      });
    }
    function saveWorkflow() {
      var definition;
      try { definition = JSON.parse(wfJson); } catch (e) { setWfMsg("JSON 无效: " + e.message); return; }
      act("save-workflow", function () {
        return api("/workflows", { method: "POST", body: JSON.stringify({ definition: definition }) })
          .then(function (w) { setWfMsg("已保存 v" + ((w && w.version) || "") + " · " + ((w && w.id) || "")); setWfDetail(w); loadWorkflow(w.id); });
      });
    }
    function gate(action) {
      if (!runId) return;
      act("gate-" + action, function () {
        return api("/runs/" + encodeURIComponent(runId) + "/gate", { method: "POST", body: JSON.stringify({ action: action, reason: "" }) })
          .then(function () { return refresh(); });
      });
    }
    function rerunNode(nodeId) {
      if (!runId) return;
      act("rerun-" + nodeId, function () {
        return api("/runs/" + encodeURIComponent(runId) + "/nodes/" + encodeURIComponent(nodeId) + "/rerun", { method: "POST" })
          .then(function () { return refresh(); });
      });
    }
    function createRun() {
      var files;
      try { files = JSON.parse(runForm.files); } catch (e) { setError("file list JSON 无效: " + e.message); return; }
      act("create-run", function () {
        return api("/runs", { method: "POST", body: JSON.stringify({
          workflow_id: runForm.workflow_id, project_root: runForm.project_root,
          title: runForm.title, files: files
        }) }).then(function (created) { if (created && created.id) goRun(created.id); });
      });
    }
    function runAction(action) {
      if (!runId) return;
      act("run-" + action, function () { return api("/runs/" + encodeURIComponent(runId) + "/" + action, { method: "POST" }); });
    }
    function collectQuality() {
      if (!qProject.trim()) { setError("请填写 project_root"); return; }
      setBusy("quality"); setError(""); setQualityResult(null); setQJob(null);
      api("/quality/collect", { method: "POST", body: JSON.stringify({
        project_root: qProject, build: true, typecheck: true, browser: !!qBrowser,
        timeout: 300, background: true
      }) }).then(function (d) {
        if (d && d.job_id) { setQJob(d.job_id); return; }
        setQualityResult(d); setBusy("");
      }).catch(function (e) { setError(e.message); setBusy(""); });
    }
    function searchMemory() {
      api("/memory/experiences?limit=50" + (memQuery ? "&query=" + encodeURIComponent(memQuery) : ""))
        .then(function (d) { setMemRows((d && d.experiences) || []); }).catch(function (e) { setError(e.message); });
    }
    function addMemory() {
      act("memory", function () {
        return api("/memory/experiences", { method: "POST", body: JSON.stringify(memForm) })
          .then(function () { setMemForm({ category: memForm.category, trigger: "", solution: "", phase: memForm.phase }); searchMemory(); });
      });
    }
    function createExpert() {
      if (!agentForm.name.trim() || !agentForm.role.trim()) { setError("专家名称与 role 必填"); return; }
      act("expert-create", function () {
        return api("/agents", { method: "POST", body: JSON.stringify({
          name: agentForm.name.trim(), role: agentForm.role.trim(),
          description: agentForm.description.trim(),
          skills: agentForm.skills.split(",").map(function (s) { return s.trim(); }).filter(Boolean),
          model: agentForm.model.trim(), toolsets: [], loop_policy: {}
        }) }).then(function (a) {
          setAgentForm({ name: "", role: "", description: "", skills: "", model: "" });
          setAgentMsg("已新增专家 " + (a && a.id ? a.id : ""));
        });
      });
    }
    function createSkill() {
      if (!skillForm.name.trim() || !skillForm.description.trim()) { setError("技能名称与 description 必填"); return; }
      act("skill-create", function () {
        return api("/skills", { method: "POST", body: JSON.stringify({
          name: skillForm.name.trim(), description: skillForm.description.trim(),
          body: skillForm.body,
          phases: skillForm.phases.split(",").map(function (s) { return s.trim(); }).filter(Boolean),
          tags: skillForm.tags.split(",").map(function (s) { return s.trim(); }).filter(Boolean)
        }) }).then(function (sk) {
          setSkillForm({ name: "", description: "", phases: "transform", tags: "", body: "## Procedure\n1. \n\n## Pitfalls\n- \n\n## Verification\n- " });
          setSkillMsg("已新增技能 " + (sk && sk.id ? sk.id : ""));
          if (sk && sk.id) loadSkill(sk.id);
        });
      });
    }
    function createWorkflowFromCurrent() {
      var base;
      try { base = wfJson ? JSON.parse(wfJson) : (wfDetail && wfDetail.definition); }
      catch (e) { setWfMsg("当前 JSON 无效，无法复制"); return; }
      if (!base) { setWfMsg("先选择一个模板作为基础"); return; }
      var id = (wfNew.id || "").trim();
      var name = (wfNew.name || "").trim();
      if (!id || !name) { setWfMsg("新工作流 id 与名称必填"); return; }
      var copy = JSON.parse(JSON.stringify(base));
      copy.id = id; copy.name = name; copy.version = "1.0.0";
      if ((wfNew.description || "").trim()) copy.description = wfNew.description.trim();
      act("wf-create", function () {
        return api("/workflows", { method: "POST", body: JSON.stringify({ definition: copy }) })
          .then(function (w) {
            setWfNew({ id: "", name: "", description: "" });
            loadWorkflow(w.id);
            setWfMsg("已创建工作流 " + w.id + "（可继续拖拽/JSON 编辑）");
          });
      });
    }

    var tabs = [["experts", "专家"], ["skills", "技能"], ["workflows", "工作流"], ["runs", "运行 / 批次"], ["quality", "质量"], ["memory", "记忆"], ["settings", "设置"]];
    var s = data.status || {};
    var counts = { agents: data.agents.length, skills: data.skills.length, workflows: data.workflows.length, runs: data.runs.length };
    var activeRun = run || data.runs.filter(function (r) { return ["running", "paused", "gated"].indexOf(r.status) >= 0; })[0];
    var activeStats = data.agentStatus.filter(function (a) { return a.active && a.active.length; });
    useEffect(function () {
      if (!qJob) return undefined;
      var active = true;
      var timer = setInterval(function () {
        api("/quality/jobs/" + encodeURIComponent(qJob)).then(function (j) {
          if (!active) return;
          if (j.status === "done") {
            setQualityResult(j.result || {});
            setQJob(null); setBusy(""); refresh();
          } else if (j.status === "error") {
            setError(j.error || "质量任务失败"); setQJob(null); setBusy("");
          }
        }).catch(function (e) { if (active) { setError(e.message); setQJob(null); setBusy(""); } });
      }, 1500);
      return function () { active = false; clearInterval(timer); };
    }, [qJob]);

    var qRoutes = (qualityResult && qualityResult.browser && qualityResult.browser.routes) || [];
    var wfDef = null;
    try { wfDef = wfJson ? JSON.parse(wfJson) : null; } catch (e) { wfDef = null; }

    return h("div", { className: css("root") },
      h("header", { className: css("head") },
        h("div", { className: css("brand") },
          h("div", { className: css("logo") }, "HF"),
          h("div", null,
            h("div", { className: css("title") }, "HERMES FLOW"),
            h("div", { className: css("sub") }, "MIGRATION CONTROL PLANE · v0.3.0"))),
        h("div", { className: css("head-right") },
          h(Badge, { tone: "ok" }, "在线"),
          h("span", { className: css("muted") }, activeRun ? ("当前 Run " + activeRun.id + " · " + (activeRun.status || "")) : "无活跃 Run"),
          h("button", { className: css("btn"), onClick: refresh, disabled: !!busy }, "刷新"))),

      h(ErrorBanner, { error: error, onRetry: refresh }),

      h("div", { className: css("stats") },
        h(Stat, { label: "专家", value: counts.agents, foot: activeStats.length + " 个有活跃批次" }),
        h(Stat, { label: "技能", value: counts.skills, foot: "已自动加载" }),
        h(Stat, { label: "工作流", value: counts.workflows, foot: "模板" }),
        h(Stat, { label: "Run", value: counts.runs, foot: (activeRun ? "当前 " + activeRun.status : "全部结束") })),

      h("nav", { className: css("tabs") }, tabs.map(function (t) {
        return h("button", { key: t[0], className: css("tab") + (tab === t[0] ? " on" : ""),
          onClick: function () { setTab(t[0]); } }, t[1]);
      })),

      tab === "experts" ? h("div", { className: css("grid2") },
        h(Panel, { title: "专家注册表", sub: "角色 / 技能 / 批次循环策略，运行态来自 agent-status" },
          h("div", null,
            h("details", { className: css("editor") },
              h("summary", null, "＋ 新增专家（写入 plugin-data/hermes_flow/agents/）"),
              h("div", { className: css("form") },
                h("input", { value: agentForm.name, placeholder: "专家名称（如：样式迁移专家）", onChange: function (e) { setAgentForm(Object.assign({}, agentForm, { name: e.target.value })); } }),
                h("textarea", { rows: 3, value: agentForm.role, placeholder: "role：职责 / 输入 / 输出 / 禁止事项（≥20 字）", onChange: function (e) { setAgentForm(Object.assign({}, agentForm, { role: e.target.value })); } }),
                h("input", { value: agentForm.description, placeholder: "description（可选）", onChange: function (e) { setAgentForm(Object.assign({}, agentForm, { description: e.target.value })); } }),
                h("input", { value: agentForm.skills, placeholder: "技能 id，逗号分隔（如 vue3-transform,antdv）", onChange: function (e) { setAgentForm(Object.assign({}, agentForm, { skills: e.target.value })); } }),
                h("input", { value: agentForm.model, placeholder: "model（可选，留空继承默认）", onChange: function (e) { setAgentForm(Object.assign({}, agentForm, { model: e.target.value })); } }),
                h("div", { className: css("btn-row") },
                  h("button", { className: css("btn") + " " + css("primary"), onClick: createExpert, disabled: !!busy }, busy === "expert-create" ? "保存中…" : "保存专家"),
                  agentMsg ? h("span", { className: css("muted") }, agentMsg) : null))),
            data.agents.length ? h("div", { className: css("cards") }, data.agents.map(function (a) {
              var active = (data.agentStatus.filter(function (x) { return x.id === a.id; })[0] || {}).active || [];
              return h(AgentCard, { key: a.id, agent: a, active: active });
            })) : h(Empty))),
        h(Panel, { title: "驱动与审计", sub: "driver 锁 / 最近写入边界违规" },
          h("h4", { className: css("mini-title") }, "活跃 driver"),
          data.drivers.length ? data.drivers.map(function (d) {
            return h("div", { className: css("row") }, h("code", null, d.group_id), h("span", null, "PID " + (d.pid || "-") + " · " + d.age + "s"));
          }) : h(Empty, null, "无活跃 driver"),
          h("h4", { className: css("mini-title") }, "最近越界违规"),
          data.audit.length ? data.audit.slice(0, 5).map(function (a) {
            return h("div", { className: css("row"), key: a.name }, h("code", null, a.name), h("span", null, (a.violations || []).length + " 项 · 已回滚 " + (a.restored || []).length));
          }) : h(Empty, null, "无越界记录"))) :

      tab === "skills" ? h("div", { className: css("grid2") },
        h(Panel, { title: "技能库", sub: "SKILL.md 唯一事实源；点击查看正文" },
          h("div", null,
            h("details", { className: css("editor") },
              h("summary", null, "＋ 新增技能（写入 plugin-data/hermes_flow/skills/<id>/SKILL.md）"),
              h("div", { className: css("form") },
                h("input", { value: skillForm.name, placeholder: "技能名称（如：Vue3 语法升级）", onChange: function (e) { setSkillForm(Object.assign({}, skillForm, { name: e.target.value })); } }),
                h("input", { value: skillForm.description, placeholder: "description（≤120 字）", onChange: function (e) { setSkillForm(Object.assign({}, skillForm, { description: e.target.value })); } }),
                h("input", { value: skillForm.phases, placeholder: "phases，逗号分隔（如 transform,quality）", onChange: function (e) { setSkillForm(Object.assign({}, skillForm, { phases: e.target.value })); } }),
                h("input", { value: skillForm.tags, placeholder: "tags，逗号分隔（如 vue3,antdv）", onChange: function (e) { setSkillForm(Object.assign({}, skillForm, { tags: e.target.value })); } }),
                h("textarea", { rows: 7, value: skillForm.body, placeholder: "正文必须含 Procedure / Pitfalls / Verification", onChange: function (e) { setSkillForm(Object.assign({}, skillForm, { body: e.target.value })); } }),
                h("div", { className: css("btn-row") },
                  h("button", { className: css("btn") + " " + css("primary"), onClick: createSkill, disabled: !!busy }, busy === "skill-create" ? "保存中…" : "保存技能"),
                  skillMsg ? h("span", { className: css("muted") }, skillMsg) : null))),
            h("div", { className: css("list") }, data.skills.map(function (sk) {
              return h("button", { key: sk.id, className: css("list-item") + (skill && skill.id === sk.id ? " " + css("selected") : ""), onClick: function () { loadSkill(sk.id); } },
                h("div", null, h("b", null, sk.name), h("div", { className: css("muted") }, sk.id + " · " + (sk.phases || []).join(", "))),
                h("span", { className: css("chip") }, (sk.tags || []).slice(0, 2).join(" ")));
            })))),
        h(Panel, { title: skill ? skill.name || skill.id : "技能详情", sub: skill ? skill.id : "选择左侧技能" },
          skill && skill.content ? h("pre", { className: css("pre") }, skill.content) : h(Empty, null, skill && skill.loading ? "加载中…" : "选择左侧技能查看 SKILL.md"))) :

      tab === "workflows" ? h("div", { className: css("grid2") },
        h(Panel, { title: "工作流模板", sub: "DAG DSL；点击查看节点" },
          h("div", null,
            h("details", { className: css("editor") },
              h("summary", null, "＋ 新建工作流（复制当前模板为起点）"),
              h("div", { className: css("form") },
                h("input", { value: wfNew.id, placeholder: "新工作流 id（如 my-vue3-flow）", onChange: function (e) { setWfNew(Object.assign({}, wfNew, { id: e.target.value })); } }),
                h("input", { value: wfNew.name, placeholder: "名称（如：自定义迁移流程）", onChange: function (e) { setWfNew(Object.assign({}, wfNew, { name: e.target.value })); } }),
                h("input", { value: wfNew.description, placeholder: "description（可选）", onChange: function (e) { setWfNew(Object.assign({}, wfNew, { description: e.target.value })); } }),
                h("div", { className: css("btn-row") },
                  h("button", { className: css("btn") + " " + css("primary"), onClick: createWorkflowFromCurrent, disabled: !!busy }, busy === "wf-create" ? "创建中…" : "创建工作流"),
                  wfMsg ? h("span", { className: css("muted") }, wfMsg) : null))),
            h("div", { className: css("cards") }, data.workflows.map(function (w) {
              return h("article", { key: w.id, className: css("card") + (wfDetail && wfDetail.id === w.id ? " " + css("selected") : ""), onClick: function () { loadWorkflow(w.id); } },
                h("b", null, w.name), h("div", { className: css("muted") }, w.id + " · v" + (w.version || "-")),
                h("p", null, w.description || ""));
            })))),
        h(Panel, { title: wfDetail ? wfDetail.name : "工作流详情", sub: "拖拽 DAG / 编辑 / 创建 Run",
          right: h("button", { className: css("btn"), onClick: function () { setTab("runs"); } }, "去运行页") },
          wfDetail && wfDetail.definition ? h("div", null,
            h("div", { className: css("dag-toolbar") },
              h("span", { className: css("muted") }, "拖拽节点调整布局；图保存在节点 meta.x/y"),
              h("button", { className: css("btn") + " " + css("btn-sm"), onClick: addWfNode }, "添加节点"),
              h("button", { className: css("btn") + " " + css("btn-sm") + " " + css("danger"), onClick: deleteWfNode, disabled: !wfSel }, "删除选中")),
            h("div", { className: css("dag-canvas"), onDragOver: function (e) { e.preventDefault(); }, onDrop: dropWfNode },
              h("svg", { className: css("dag-lines"), width: "100%", height: "100%" },
                ((wfDef && wfDef.edges) || []).map(function (e) {
                  var a = wfPos[e.source] || { x: 16, y: 14 }, b = wfPos[e.target] || { x: 16, y: 14 };
                  return h("line", { key: e.source + ">" + e.target, x1: a.x + 70, y1: a.y + 26, x2: b.x + 70, y2: b.y + 26, stroke: "#3d5a66", strokeWidth: 1.5 });
                })),
              ((wfDef && wfDef.nodes) || []).map(function (n) {
                var p = wfPos[n.id] || { x: 16, y: 14 };
                return h("div", {
                  key: n.id, draggable: true,
                  className: css("dag-node") + (wfSel === n.id ? " " + css("selected") : ""),
                  style: { left: p.x + "px", top: p.y + "px" },
                  onDragStart: function (e) { e.dataTransfer.setData("text/plain", n.id); setWfSel(n.id); },
                  onClick: function () { setWfSel(n.id); }
                }, h("b", null, n.name || n.id), h("span", null, n.phase || n.type || ""), h("em", null, n.agent || ""));
              })),
            h("div", { className: css("edges") }, h("b", null, "Edges: "),
              ((wfDef && wfDef.edges) || []).map(function (e) { return h("span", { key: e.source + e.target }, e.source + " → " + e.target + "  "); })),
            h("details", { className: css("editor") },
              h("summary", null, "编辑 JSON（DAG DSL）"),
              h("textarea", { rows: 10, value: wfJson, onChange: function (e) { setWfJson(e.target.value); } }),
              h("div", { className: css("btn-row") },
                h("button", { className: css("btn") + " " + css("primary"), onClick: saveWorkflow, disabled: !!busy }, busy === "save-workflow" ? "保存中…" : "保存工作流"),
                wfMsg ? h("span", { className: css("muted") }, wfMsg) : null)),
            h("div", { className: css("form") },
              h("input", { value: runForm.project_root, placeholder: "project_root（绝对路径）", onChange: function (e) { setRunForm(Object.assign({}, runForm, { project_root: e.target.value })); } }),
              h("textarea", { rows: 3, value: runForm.files, onChange: function (e) { setRunForm(Object.assign({}, runForm, { files: e.target.value })); } }),
              h("button", { className: css("btn") + " " + css("primary"), onClick: createRun, disabled: !!busy }, busy === "create-run" ? "创建中…" : "创建 Run"))) : h(Empty, null, "选择左侧工作流查看 DAG"))) :

      tab === "runs" ? h("div", { className: css("runs") },
        h(Panel, { title: "Run 列表", sub: "选择查看节点 / 批次 / driver" },
          h("div", { className: css("list") }, data.runs.map(function (r) {
            return h("button", { key: r.id, className: css("list-item") + (r.id === runId ? " " + css("selected") : ""), onClick: function () { setRunId(r.id); } },
              h("div", null, h("b", null, r.title || r.id), h("div", { className: css("muted") }, r.id + " · " + (r.workflow_id || ""))),
              h(Badge, { tone: r.status === "done" ? "ok" : (r.status === "gated" ? "warn" : (r.status === "running" ? "run" : "idle")) }, r.status || "-"));
          }))),
        h(Panel, { title: run ? "Run " + run.id : "Run 详情", sub: run ? (run.workflow_name || run.workflow_id) + " · " + (run.status || "") : "选择左侧 Run",
          right: run ? h("div", { className: css("btn-row") },
            run.status === "gated" ? h("button", { className: css("btn") + " " + css("primary"), onClick: function () { gate("approve"); } }, "批准") : null,
            run.status === "gated" ? h("button", { className: css("btn") + " " + css("danger"), onClick: function () { gate("reject"); } }, "驳回") : null,
            h("button", { className: css("btn"), onClick: function () { runAction("pause"); } }, "暂停"),
            h("button", { className: css("btn"), onClick: function () { runAction("resume"); } }, "继续"),
            h("button", { className: css("btn") + " " + css("danger"), onClick: function () { runAction("cancel"); } }, "取消")) : null },
          run ? h("div", null,
            h("div", { className: css("kv") },
              h("span", null, "project_root: " + (run.project_root || "-")),
              h("span", null, "files: " + ((run.files || []).length)),
              h("span", null, "created: " + fmt(run.created_at))),
            run.workflow && run.workflow.nodes ? h("div", { className: css("dag") }, run.workflow.nodes.map(function (n) {
              var nodeState = (run.node_states || {})[n.id] || "";
              return h("div", { className: css("node") + (nodeState ? " " + css("node-" + String(nodeState).replace(/[^a-z]/gi, "")) : ""), key: n.id },
                h("b", null, n.name || n.id), h("span", null, n.type || ""), h("em", null, nodeState || "未开始"));
            })) : null,
            Object.keys(run.batches || {}).map(function (nodeId) {
              var g = run.batches[nodeId];
              return h("div", { key: nodeId, className: css("group") },
                h("div", { className: css("group-hd") },
                  h("b", null, nodeId), h("span", null, g.done_batches + "/" + g.total_batches + " 批 · 运行 " + (g.running || []).length + " · 失败 " + (g.failed || []).length),
                  (g.failed || []).length ? h("button", { className: css("btn") + " " + css("btn-sm"), onClick: function () { rerunNode(nodeId); } }, "重跑失败") : null),
                h("table", { className: css("table") },
                  h("thead", null, h("tr", null, ["批次", "状态", "尝试", "分数", "判定"].map(function (x) { return h("th", { key: x }, x); }))),
                  h("tbody", null, (g.batches || []).map(function (b) {
                    return h("tr", { key: b.id, className: b.id === selectedBatch ? css("selected-row") : "", onClick: function () { setSelectedBatch(b.id); } },
                      h("td", null, h("code", null, b.id)), h("td", null, h(Badge, { tone: b.status === "done" ? "ok" : (b.status === "failed" ? "bad" : (b.status === "running" ? "run" : "idle")) }, b.status)),
                      h("td", null, b.attempt), h("td", null, b.score == null ? "-" : b.score), h("td", null, b.verdict || "-"));
                  }))),
                selectedBatch && (g.batches || []).some(function (b) { return b.id === selectedBatch; }) ?
                  h(React.Fragment, null,
                    h("div", { className: css("items") }, h("b", null, "文件明细 "), selectedBatch),
                    h("table", { className: css("table") }, h("thead", null, h("tr", null, ["文件", "状态", "哈希"].map(function (x) { return h("th", { key: x }, x); }))),
                      h("tbody", null, batchItems.map(function (i) { return h("tr", { key: i.id }, h("td", null, h("code", null, i.file_path)), h("td", null, i.status), h("td", null, i.applied_hash || "-")); })))) : null);
            }),
            h("div", { className: css("events") },
              h("div", { className: css("mini-title") }, "事件流（持久化 seq，断线后按 cursor 补齐）"),
              events.length ? events.slice(-40).reverse().map(function (ev) {
                return h("div", { className: css("event"), key: ev.seq },
                  h("span", { className: css("event-seq") }, "#" + ev.seq),
                  h("b", null, ev.type),
                  h("span", { className: css("event-data") }, jsonText(ev.data || {}).replace(/\s+/g, " ").slice(0, 220)));
              }) : h(Empty, null, "暂无事件（开始 driver 后出现）"))
          )
          : h(Empty))) :

      tab === "quality" ? h("div", { className: css("grid2") },
        h(Panel, { title: "真实质量门", sub: "build / typecheck / Chrome CDP 路由验证" },
          h("div", { className: css("form") },
            h("input", { value: qProject, placeholder: "project_root（有 dist 的 Vite 项目）", onChange: function (e) { setQProject(e.target.value); } }),
            h("label", { className: css("check") }, h("input", { type: "checkbox", checked: qBrowser, onChange: function (e) { setQBrowser(e.target.checked); } }), " 浏览器路由验证"),
            h("button", { className: css("btn") + " " + css("primary"), onClick: collectQuality, disabled: busy === "quality" }, busy === "quality" ? "后台采集中…" : "运行质量采集")),
          qualityResult ? h("div", null,
            h("div", { className: css("kv") }, h("span", null, "build: " + ((qualityResult.build || {}).ok ? "✅" : "❌")),
              h("span", null, "browser: " + ((qualityResult.browser || {}).ok ? "✅" : (qualityResult.browser && qualityResult.browser.ran ? "❌" : "跳过"))),
              h("span", null, "总耗时 " + qualityResult.duration + "s")),
            qRoutes.length ? h("table", { className: css("table") }, h("thead", null, h("tr", null, ["路由", "结果", "节点", "console", "page"].map(function (x) { return h("th", { key: x }, x); }))),
              h("tbody", null, qRoutes.map(function (r) { return h("tr", { key: r.route }, h("td", null, r.route), h("td", null, r.ok ? "✅" : "❌"), h("td", null, r.appNodes), h("td", null, (r.consoleErrors || []).length), h("td", null, (r.pageErrors || []).length)); }))) : null,
            h("pre", { className: css("pre") }, jsonText({ gate: qualityResult.gate, build: { ok: (qualityResult.build || {}).ok, exit: (qualityResult.build || {}).exit_code }, browser: { ok: (qualityResult.browser || {}).ok } }))) : null),
        h(Panel, { title: "最近质量证据", sub: "plugin-data/quality" },
          data.quality.length ? h("table", { className: css("table") }, h("thead", null, h("tr", null, ["文件", "build", "browser", "路由", "时间"].map(function (x) { return h("th", { key: x }, x); }))),
            h("tbody", null, data.quality.map(function (q) { return h("tr", { key: q.name }, h("td", null, h("code", null, q.name)), h("td", null, q.build ? "✅" : "❌"), h("td", null, q.browser ? "✅" : "—"), h("td", null, q.browser_routes || 0), h("td", null, fmt(q.mtime))); }))) : h(Empty))) :

      tab === "memory" ? h("div", { className: css("grid2") },
        h(Panel, { title: "经验库", sub: "SQLite 沉淀/召回；关键词搜索" },
          h("div", { className: css("form-inline") },
            h("input", { value: memQuery, placeholder: "搜索 trigger/solution", onChange: function (e) { setMemQuery(e.target.value); } }),
            h("button", { className: css("btn"), onClick: searchMemory }, "搜索")),
          memRows.length ? h("div", { className: css("list") }, memRows.map(function (m) {
            return h("div", { className: css("memory"), key: m.id }, h("b", null, m.category + " · " + m.trigger),
              h("p", null, m.solution), h("span", { className: css("muted") }, "hit " + (m.times_hit || 0) + " · " + fmt(m.created_at)));
          })) : h(Empty, null, "无经验记录；可在右侧新增")),
        h(Panel, { title: "新增经验", sub: "会被下次召回" },
          h("div", { className: css("form") },
            h("input", { value: memForm.category, placeholder: "category", onChange: function (e) { setMemForm(Object.assign({}, memForm, { category: e.target.value })); } }),
            h("input", { value: memForm.trigger, placeholder: "trigger", onChange: function (e) { setMemForm(Object.assign({}, memForm, { trigger: e.target.value })); } }),
            h("textarea", { rows: 3, value: memForm.solution, placeholder: "solution", onChange: function (e) { setMemForm(Object.assign({}, memForm, { solution: e.target.value })); } }),
            h("input", { value: memForm.phase, placeholder: "phase", onChange: function (e) { setMemForm(Object.assign({}, memForm, { phase: e.target.value })); } }),
            h("button", { className: css("btn") + " " + css("primary"), onClick: addMemory, disabled: !!busy }, "保存经验")))) :

      h("div", { className: css("grid2") },
        h(Panel, { title: "设置 / 运行时", sub: "数据目录、阈值、driver 限制" },
          data.settings ? h("pre", { className: css("pre") }, jsonText(data.settings)) : h(Empty)),
        h(Panel, { title: "Dashboard API", sub: "所有页面均走真实数据" },
          h("div", { className: css("links") },
            ["/status", "/agents", "/skills", "/workflows", "/runs", "/agent-status", "/quality", "/audit", "/drivers", "/settings", "/memory/experiences"].map(function (p) {
              return h("code", { key: p }, API + p);
            })),
          h("p", { className: css("muted") }, "数据每 5s 轮询；写操作请使用 agent 工具或上方按钮。"))),

      h("footer", { className: css("foot") },
        h("span", null, "HERMES Flow v0.3.0 · Dashboard v2"),
        h("span", null, "34 tools · " + counts.agents + " experts · " + counts.skills + " skills")));
  }

  function fallback() {
    var root = document.getElementById("root") || document.body;
    if (root) root.innerHTML = '<div style="padding:24px;color:#e6edf3;font:14px Segoe UI">HERMES Flow 需要 Hermes Dashboard SDK；当前未检测到 window.__HERMES_PLUGIN_SDK__。</div>';
  }

  if (!React || !h || !hooks.useState) { fallback(); return; }
  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("hermes_flow", App);
  } else {
    fallback();
  }
})();
