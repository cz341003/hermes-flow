/* ============================================================
   HERMES UI mockup — interactions
   ============================================================ */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  var PAGES = {
    workbench: { title: '工作台', mode: 'LIVE' },
    agents: { title: '专家', mode: 'BUILD' },
    skills: { title: '技能', mode: 'BUILD' },
    flow: { title: '工作流编排', mode: 'BUILD' },
    monitor: { title: '运行监控', mode: 'LIVE' },
    memory: { title: '记忆中心', mode: 'GOVERN' },
    quality: { title: '质量门控', mode: 'GOVERN' },
    settings: { title: '设置', mode: 'SYSTEM' }
  };

  var state = {
    page: 'workbench',
    paused: false,
    logPaused: false,
    skillsLoaded: false,
    reviewing: false,
    countdown: 8,
    recovered: false,
    palIndex: 0,
    palItems: []
  };

  /* ---------------- toast ---------------- */
  var TOAST_ICONS = {
    ok: 'i-check-circle', warn: 'i-alert', err: 'i-alert-circle', info: 'i-info', acc: 'i-info'
  };
  function toast(type, title, desc) {
    var host = $('#toasts');
    if (!host) return;
    var el = document.createElement('div');
    el.className = 'toast ' + (type || 'info');
    el.innerHTML =
      '<svg class="t-ico"><use href="#' + (TOAST_ICONS[type] || 'i-info') + '"/></svg>' +
      '<div><div class="t-title"></div>' + (desc ? '<div class="t-desc"></div>' : '') + '</div>' +
      '<button class="t-close" aria-label="关闭提示"><svg width="12" height="12"><use href="#i-x"/></svg></button>';
    el.querySelector('.t-title').textContent = title;
    if (desc) el.querySelector('.t-desc').textContent = desc;
    host.appendChild(el);
    var kill = function () {
      el.classList.add('out');
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
    };
    el.querySelector('.t-close').addEventListener('click', kill);
    setTimeout(kill, 3800);
  }

  /* ---------------- routing ---------------- */
  function animateBars(root) {
    $$('.bar > i', root || document).forEach(function (i) {
      if (i.dataset.w === '1') return;
      var w = i.style.width;
      if (!w) return;
      i.dataset.w = '1';
      i.style.transition = 'none';
      i.style.width = '0%';
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          i.style.transition = '';
          i.style.width = w;
        });
      });
    });
  }

  function go(page, opts) {
    if (!PAGES[page]) return;
    opts = opts || {};
    state.page = page;
    $$('.page').forEach(function (p) { p.classList.remove('active'); });
    var target = $('#page-' + page);
    if (target) target.classList.add('active');

    $$('.nav-item').forEach(function (n) {
      var on = n.dataset.page === page;
      n.classList.toggle('active', on);
      if (on) n.setAttribute('aria-current', 'page');
      else n.removeAttribute('aria-current');
    });

    var crumb = $('#crumbPage');
    if (crumb) crumb.textContent = PAGES[page].title;
    var mode = $('#crumbMode');
    if (mode) mode.textContent = PAGES[page].mode;
    document.title = 'HERMES · ' + PAGES[page].title;

    if (!opts.silent) {
      try { history.replaceState(null, '', '#' + page); } catch (e) { location.hash = page; }
    }

    if (target) {
      animateBars(target);
      target.scrollIntoView({ block: 'start' });
    }
    var view = $('#view');
    if (view) view.scrollTop = 0;

    if (page === 'skills') initSkills();
    if (page === 'monitor') startMonitor();
  }

  /* ---------------- nav & global click ---------------- */
  document.addEventListener('click', function (e) {
    var nav = e.target.closest('.nav-item');
    if (nav && nav.dataset.page) {
      e.preventDefault();
      go(nav.dataset.page);
      return;
    }

    var openDrawerEl = e.target.closest('[data-open-drawer]');
    if (openDrawerEl) {
      e.preventDefault();
      openDrawer(openDrawerEl.dataset.openDrawer);
      return;
    }

    var brow = e.target.closest('.batch-row');
    if (brow) {
      brow.classList.toggle('open');
      return;
    }

    var sw = e.target.closest('[data-switch]');
    if (sw) {
      var on = sw.getAttribute('aria-checked') === 'true';
      sw.setAttribute('aria-checked', on ? 'false' : 'true');
      sw.focus();
      return;
    }

    var actionEl = e.target.closest('[data-action]');
    if (actionEl) {
      handleAction(actionEl.dataset.action, actionEl);
    }
  });

  function handleAction(action, el) {
    switch (action) {
      case 'toast-navigator':
        go(el.dataset.target);
        break;
      case 'toast-ok':
        toast('ok', el.dataset.toast || '操作成功');
        break;
      case 'toast-warn':
        toast('warn', el.dataset.toast || '需要注意');
        break;
      case 'toast-info':
        toast('info', el.dataset.toast || '操作完成');
        break;
      case 'toast-exc':
        toast('warn', '3 个活跃异常', '429 限流自动退避 · 上下文截断已自愈 · TreeSelect.vue 构建失败待处理');
        break;
      case 'pause-run':
        togglePause(el);
        break;
      case 'resume-run':
        el.classList.add('loading');
        toast('acc', '断点续跑已排队', '将从批次 #16 检查点恢复 · 已跳过 1 个已完成批');
        setTimeout(function () { el.classList.remove('loading'); }, 1200);
        break;
      case 'recover':
        recoverExc(el);
        break;
      case 'retry-agent':
        retryAgent(el);
        break;
      case 'review':
        review();
        break;
      case 'toggle-log':
        state.logPaused = !state.logPaused;
        el.innerHTML = '<svg><use href="#' + (state.logPaused ? 'i-play' : 'i-pause') + '"/></svg>';
        toast('info', state.logPaused ? '日志流已暂停' : '日志流已恢复');
        break;
      default:
        break;
    }
  }

  function togglePause(el) {
    state.paused = !state.paused;
    var label = el.querySelector('span');
    if (label) label.textContent = state.paused ? '继续' : '暂停';
    if (el.id === 'monitorPauseBtn') {
      el.innerHTML = state.paused
        ? '<svg><use href="#i-play"/></svg><span>继续</span>'
        : '<svg><use href="#i-pause"/></svg><span>暂停</span>';
    } else {
      var svg = el.querySelector('svg use');
      if (svg) svg.setAttribute('href', state.paused ? '#i-play' : '#i-pause');
    }
    toast(state.paused ? 'warn' : 'ok', state.paused ? '运行已暂停' : '运行已继续', state.paused ? '已完成节点结果保留，可随时继续' : '从暂停点继续执行');
  }

  /* ---------------- expert drawer ---------------- */
  var AGENTS = {
    transform: {
      name: '代码转化专家', glyph: '转', tone: '', status: '运行中', stCls: 'run', statusKey: 'running',
      sub: 'transform · v2.3.1 · agent-04', skills: 5, rate: '97.4', runs: '412', avg: '38', loop: '6.2', batch: true,
      prompt: '你是 Vue2 → Vue3 迁移专家。\n\n职责：逐文件将 Options API 改写为 <script setup>，保持业务行为不变，保留中文注释与原文件结构。\n硬约束：不得重写无关代码；不得删除业务分支；每次交付必须附带 diff 摘要与自检清单。\n输出：patch.diff + 改动说明 + 风险点。'
    },
    structure: {
      name: '结构分析专家', glyph: '析', tone: 'grey', status: '空闲', stCls: 'idle', statusKey: 'idle',
      sub: 'structure · v1.8.0 · agent-01', skills: 3, rate: '99.1', runs: '268', avg: '9', loop: '0.8',
      prompt: '你是前端架构分析专家。\n\n职责：解析 SFC 结构、路由与组件依赖，生成迁移风险清单与批次切分建议。\n输出：risk-report.json（高风险 / 中风险 / 低风险）+ 依赖图 + 建议批次。'
    },
    deps: {
      name: '依赖分析专家', glyph: '依', tone: 'blue', status: '已完成', stCls: 'ok', statusKey: 'done',
      sub: 'deps · v1.6.2 · agent-02', skills: 3, rate: '95.8', runs: '196', avg: '24', loop: '3.1',
      prompt: '你是依赖治理专家。\n\n职责：比对 package.json 与锁文件，给出 Vuex→Pinia、Ant Design Vue 1.x→4.x、Webpack→Vite 的升级路径与版本矩阵。\n输出：migration-plan.md + 版本矩阵表。'
    },
    quality: {
      name: '质量分析专家', glyph: '质', tone: 'green', status: '运行中', stCls: 'run', statusKey: 'running',
      sub: 'quality · v2.0.4 · agent-03', skills: 3, rate: '93.6', runs: '524', avg: '7', loop: '5.4',
      prompt: '你是质量门控专家。\n\n职责：聚合 AST / 构建 / 类型 / 浏览器 / 行为五信号，按权重输出 0-100 评分并给出可解释的失分原因。\n硬约束：任一信号 < 60 直接判负；评分必须可复现。'
    },
    browser: {
      name: '浏览器验证专家', glyph: '验', tone: 'amber', status: '空闲', stCls: 'idle', statusKey: 'idle',
      sub: 'browser · v1.9.0 · agent-05', skills: 3, rate: '96.2', runs: '301', avg: '31', loop: '4.7',
      prompt: '你是 E2E 验证专家。\n\n职责：用 Playwright 打开迁移后页面，采集 DOM 快照、交互行为与控制台错误，与基线逐项比对。\n输出：12 张截图 + DOM diff + console 报告。'
    },
    fix: {
      name: '修复专家', glyph: '修', tone: 'red', status: '失败', stCls: 'err', statusKey: 'failed',
      sub: 'fix · v1.4.7 · agent-06', skills: 3, rate: '81.2', runs: '147', avg: '46', loop: '18.9',
      prompt: '你是回环修复专家。\n\n职责：读取低分信号与证据，定位最小修复面，禁止重写无关代码；每次修复必须产出 diff 与验证证据。\n硬约束：单文件改动 ≤ 60 行；必须解释失分信号与修复的因果关系。'
    },
    pinia: {
      name: 'Pinia 迁移专家', glyph: '迁', tone: 'blue', status: '空闲', stCls: 'idle', statusKey: 'idle',
      sub: 'state · v1.5.0 · agent-08', skills: 3, rate: '94.7', runs: '212', avg: '26', loop: '4.1',
      prompt: '你是状态层迁移专家。\n\n职责：将 Vuex module 改写为 Pinia store（setup store 优先），保持 getter / action 语义与调用方零改动。\n输出：store 迁移 diff + 数据流校验结果 + 类型补全清单。'
    },
    memory: {
      name: '记忆归纳专家', glyph: '记', tone: 'grey', status: '空闲', stCls: 'idle', statusKey: 'idle',
      sub: 'memory · v1.2.0 · agent-07', skills: 3, rate: '98.0', runs: '88', avg: '12', loop: '1.2',
      prompt: '你是经验归纳专家。\n\n职责：把本次运行中的踩坑压缩为可复用的经验卡片，标注坑类型、触发条件、解法与适用范围。\n输出：experience.jsonl（去重合并后写入记忆库）。'
    }
  };

  function openDrawer(key) {
    var a = AGENTS[key];
    if (!a) return;
    $('#dAva').textContent = a.glyph;
    $('#dAva').className = 'ava ' + a.tone;
    $('#dName').textContent = a.name;
    $('#dSub').textContent = a.sub;
    $('#dStatus').className = 'st ' + a.stCls;
    $('#dStatus').innerHTML = '<span class="dt"></span>' + a.status;
    $('#dStatusText').textContent = a.statusKey;
    $('#dSkillCount').textContent = a.skills + ' 个技能';
    $('#dRate').innerHTML = a.rate + '<small>%</small>';
    $('#dRuns').textContent = a.runs;
    $('#dAvg').innerHTML = a.avg + '<small>s</small>';
    $('#dLoop').innerHTML = a.loop + '<small>%</small>';
    $('#dPrompt').textContent = a.prompt;
    var loopSec = $('#dLoopSec');
    if (loopSec) loopSec.style.display = a.batch ? '' : 'none';

    var drawer = $('#drawer');
    drawer.classList.add('on');
    drawer.setAttribute('aria-hidden', 'false');
    $('#scrim').classList.add('on');
    setTimeout(function () { $('#drawerClose').focus(); }, 60);
  }

  function closeDrawer() {
    $('#drawer').classList.remove('on');
    $('#drawer').setAttribute('aria-hidden', 'true');
    $('#scrim').classList.remove('on');
  }

  $('#drawerClose').addEventListener('click', closeDrawer);
  $('#scrim').addEventListener('click', closeDrawer);

  /* ---------------- agents: filter / view / retry ---------------- */
  var agentFilter = 'all';
  function filterAgents() {
    var q = ($('#agentSearch').value || '').trim().toLowerCase();
    var shown = 0;
    $$('#agentGrid .agent-card').forEach(function (card) {
      var stMatch = agentFilter === 'all' || card.dataset.state === agentFilter;
      var keys = (card.dataset.keys || '') + ' ' + (card.dataset.agent || '');
      var qMatch = !q || keys.toLowerCase().indexOf(q) !== -1;
      var ok = stMatch && qMatch;
      card.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    var add = $('#agentGrid .agent-add');
    if (add) add.style.display = agentFilter === 'all' && !q ? '' : 'none';
    var empty = $('#agentEmpty');
    if (empty) empty.style.display = shown === 0 ? '' : 'none';
    var wrap = $('#agentsWrap');
    if (wrap) wrap.classList.toggle('agents-list', wrap.dataset.view === 'list');
  }

  if ($('#agentSearch')) $('#agentSearch').addEventListener('input', filterAgents);
  $$('#agentFilters .chip').forEach(function (c) {
    c.addEventListener('click', function () {
      $$('#agentFilters .chip').forEach(function (x) { x.classList.remove('active'); });
      c.classList.add('active');
      agentFilter = c.dataset.filter;
      filterAgents();
    });
  });
  $$('#agentView button').forEach(function (b) {
    b.addEventListener('click', function () {
      $$('#agentView button').forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      var wrap = $('#agentsWrap');
      wrap.dataset.view = b.dataset.view;
      wrap.classList.toggle('agents-list', b.dataset.view === 'list');
      var grid = $('#agentGrid');
      if (grid) grid.style.display = b.dataset.view === 'list' ? 'none' : '';
    });
  });
  var resetAgents = $('#agentReset');
  if (resetAgents) resetAgents.addEventListener('click', function () {
    $('#agentSearch').value = '';
    agentFilter = 'all';
    $$('#agentFilters .chip').forEach(function (x) { x.classList.toggle('active', x.dataset.filter === 'all'); });
    filterAgents();
  });
  if ($('#agentGrid')) {
    $('#agentGrid').addEventListener('click', function (e) {
      if (e.target.closest('[data-action],[data-open-drawer]')) return;
      var card = e.target.closest('.agent-card');
      if (card) openDrawer(card.dataset.agent);
    });
    $('#agentGrid').addEventListener('keydown', function (e) {
      var card = e.target.closest('.agent-card');
      if (card && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        openDrawer(card.dataset.agent);
      }
    });
  }
  function retryAgent(btn) {
    btn.classList.add('loading');
    btn.innerHTML = '<span class="spinner"></span>';
    toast('info', '已重新派单给修复专家', 'TreeSelect.vue 回环第 3 轮 · 预计 40s');
    setTimeout(function () {
      var card = btn.closest('.agent-card');
      btn.classList.remove('loading');
      btn.innerHTML = '<svg><use href="#i-check"/></svg>';
      if (card) {
        card.classList.remove('failed');
        card.dataset.state = 'running';
        var chip = card.querySelector('.ac-top .st');
        if (chip) { chip.className = 'st run'; chip.innerHTML = '<span class="dt"></span>运行中'; }
      }
      toast('ok', '修复专家已进入运行', '等待质量门控重新评分');
    }, 1500);
  }

  /* ---------------- skills ---------------- */
  function initSkills() {
    animateBars($('#page-skills'));
  }
  function reloadSkills() {
    var table = $('#skillsTable');
    var skel = $('#skillSkeleton');
    if (!table || !skel) return;
    table.style.visibility = 'hidden';
    skel.style.display = '';
    setTimeout(function () {
      skel.style.display = 'none';
      table.style.visibility = '';
      animateBars($('#page-skills'));
      toast('info', '技能库已重新加载', '12 个技能 · 9 个已绑定 · 读取耗时 0.7s');
    }, 900);
  }
  if ($('#skillsReload')) $('#skillsReload').addEventListener('click', reloadSkills);
  function filterSkills() {
    var q = ($('#skillSearch').value || '').trim().toLowerCase();
    var shown = 0;
    $$('#skillsBody tr').forEach(function (tr) {
      var stageOk = skillStage === 'all' || tr.dataset.stage === skillStage;
      var qOk = !q || (tr.dataset.keys || '').toLowerCase().indexOf(q) !== -1;
      var ok = stageOk && qOk;
      tr.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    var empty = $('#skillEmpty');
    if (empty) empty.style.display = shown === 0 ? '' : 'none';
    var count = $('#skillCount');
    if (count) count.textContent = shown;
  }
  var skillStage = 'all';
  if ($('#skillSearch')) $('#skillSearch').addEventListener('input', filterSkills);
  $$('#skillFilters .chip').forEach(function (c) {
    c.addEventListener('click', function () {
      $$('#skillFilters .chip').forEach(function (x) { x.classList.remove('active'); });
      c.classList.add('active');
      skillStage = c.dataset.stage;
      filterSkills();
    });
  });
  var skillReset = $('#skillReset');
  if (skillReset) skillReset.addEventListener('click', function () {
    $('#skillSearch').value = '';
    skillStage = 'all';
    $$('#skillFilters .chip').forEach(function (x) { x.classList.toggle('active', x.dataset.stage === 'all'); });
    filterSkills();
  });

  /* ---------------- memory ---------------- */
  var memCat = 'all';
  function filterMemory() {
    var q = ($('#memSearch').value || '').trim().toLowerCase();
    var shown = 0;
    $$('#memGrid .mem-card').forEach(function (card) {
      var catOk = memCat === 'all' || card.dataset.cat === memCat;
      var qOk = !q || (card.dataset.keys || '').toLowerCase().indexOf(q) !== -1;
      var ok = catOk && qOk;
      card.style.display = ok ? '' : 'none';
      if (ok) shown++;
    });
    var empty = $('#memEmpty');
    if (empty) empty.style.display = shown === 0 ? '' : 'none';
  }
  if ($('#memSearch')) $('#memSearch').addEventListener('input', filterMemory);
  $$('#memFilters .chip').forEach(function (c) {
    c.addEventListener('click', function () {
      $$('#memFilters .chip').forEach(function (x) { x.classList.remove('active'); });
      c.classList.add('active');
      memCat = c.dataset.cat;
      filterMemory();
    });
  });
  var memReset = $('#memReset');
  if (memReset) memReset.addEventListener('click', function () {
    $('#memSearch').value = '';
    memCat = 'all';
    $$('#memFilters .chip').forEach(function (x) { x.classList.toggle('active', x.dataset.cat === 'all'); });
    filterMemory();
  });

  /* ---------------- flow: node select & props ---------------- */
  var NODES = {
    structure: { name: '结构分析', kind: 'agent', sub: 'structure · 结构分析专家 · 依赖图解析', field: '结构分析' },
    deps: { name: '依赖分析', kind: 'agent', sub: 'deps · 依赖分析专家 · 版本矩阵', field: '依赖分析' },
    config: { name: '配置迁移', kind: 'agent', sub: 'agent · 并行分支 · 依赖分析专家', field: '配置迁移' },
    transform: { name: '代码转化', kind: 'batch', sub: 'transform-batch · 批次 18/43 · 7 文件/批', field: '代码转化' },
    gate: { name: '质量门控', kind: 'gate', sub: 'quality-gate · 进入条件 score ≥ 85', field: '质量门控' },
    verify: { name: '浏览器验证', kind: 'agent', sub: 'browser · 浏览器验证专家 · Playwright', field: '浏览器验证' },
    fix: { name: '修复回环', kind: 'loop', sub: 'loop · 修复专家 · 上限 3 轮', field: '修复回环' },
    human: { name: '人工复核', kind: 'human', sub: 'human · 迁移负责人 · 超限升级', field: '人工复核' }
  };
  var selectedNode = 'transform';
  $$('#canvasInner .node').forEach(function (node) {
    node.addEventListener('click', function () {
      $$('#canvasInner .node').forEach(function (n) {
        n.classList.remove('sel');
        n.setAttribute('aria-pressed', 'false');
      });
      node.classList.add('sel');
      node.setAttribute('aria-pressed', 'true');
      selectedNode = node.dataset.node;
      var d = NODES[selectedNode];
      if (!d) return;
      var stChip = d.kind === 'gate' ? '<span class="st warn" style="height:18px"><span class="dt"></span>gate</span>'
        : d.kind === 'loop' ? '<span class="st warn" style="height:18px"><span class="dt"></span>loop</span>'
          : d.kind === 'human' ? '<span class="st info" style="height:18px"><span class="dt"></span>human</span>'
            : '<span class="st ok" style="height:18px"><span class="dt"></span>agent</span>';
      $('#propName').innerHTML = d.name + ' ' + stChip;
      $('#propSub').textContent = d.sub;
      $('#propFieldName').value = d.field;
      var bp = $('#batchProps'); if (bp) bp.style.display = (selectedNode === 'transform') ? '' : 'none';
      var gp = $('#gateProps'); if (gp) gp.style.display = (selectedNode === 'gate') ? 'flex' : 'none';
    });
  });
  $$('[data-prop-tab]').forEach(function (tab) {
    tab.addEventListener('click', function () {
      $$('[data-prop-tab]').forEach(function (t) { t.classList.remove('active'); });
      tab.classList.add('active');
      var map = { attr: '#propAttr', io: '#propIO', runs: '#propRuns' };
      Object.keys(map).forEach(function (k) {
        var el = $(map[k]);
        if (el) el.style.display = (k === tab.dataset.propTab) ? '' : 'none';
      });
    });
  });
  if ($('#propFieldName')) {
    $('#propFieldName').addEventListener('input', function () {
      var node = $('#canvasInner .node[data-node="' + selectedNode + '"]');
      if (node) {
        var nm = node.querySelector('.nd-name');
        if (nm) nm.textContent = this.value || NODES[selectedNode].name;
      }
    });
  }
  if ($('#templateSelect')) {
    $('#templateSelect').addEventListener('change', function () {
      toast('info', '已切换模板：' + this.value, '画布将按模板重建（演示环境不重建）');
    });
  }

  /* ---------------- evidence tabs ---------------- */
  $$('[data-ev-tab]').forEach(function (tab) {
    tab.addEventListener('click', function () {
      $$('[data-ev-tab]').forEach(function (t) { t.classList.remove('active'); });
      tab.classList.add('active');
      ['build', 'diff', 'shot', 'batch'].forEach(function (k) {
        var pane = $('#ev-' + k);
        if (pane) pane.classList.toggle('on', k === tab.dataset.evTab);
      });
    });
  });
  $$('[data-ev-jump]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var target = btn.dataset.evJump;
      var tab = $('[data-ev-tab="' + target + '"]');
      if (tab) tab.click();
    });
  });

  /* ---------------- monitor animations ---------------- */
  var monitorStarted = false;
  var elapsedSec = 1 * 3600 + 12 * 60 + 48;
  var pct = 61.4;
  var logLines = [
    ['17:23:12', 'turn', '<b>质量分析专家</b> 五信号聚合完成 4/5 · 行为一致性待定'],
    ['17:23:26', 'gate', '门控预计算 score 86.2 · behavior 待定时不写入结果'],
    ['17:23:41', 'turn', '<b>浏览器验证专家</b> 准备基线快照 · 12 个交互点'],
    ['17:23:58', 'ckpt', 'checkpoint 即将写入 · 批次 #18 · 间隔 30s'],
    ['17:24:10', 'mem', '命中经验「ztree→a-tree 事件名差异」×2 · 已注入修复上下文'],
    ['17:24:22', 'retry', '模型通道延迟 1.8s · 自动切备用 · 无重试'],
    ['17:24:35', 'verify', 'vue-tsc 增量检查 · 0 error · 2 warning'],
    ['17:24:48', 'turn', '<b>修复专家</b> 输出最小修复面 · 2 文件 / 41 行'],
    ['17:25:02', 'gate', 'Queue drain · 批次 #18 · 剩余 1 文件'],
    ['17:25:16', 'ckpt', '检查点写入完成 · 断点可续跑'],
    ['17:25:30', 'turn', '<b>结构分析专家</b> 预读批次 #19 · 7 文件'],
    ['17:25:44', 'verify', 'Playwright Chromium 复用实例 · 节省 1.2s']
  ];
  var logIdx = 0;
  function startMonitor() {
    if (monitorStarted) return;
    monitorStarted = true;
    animateBars($('#page-monitor'));
    setInterval(function () {
      if (state.paused) return;
      elapsedSec++;
      var el = $('#monElapsed');
      if (el) {
        var h = Math.floor(elapsedSec / 3600);
        var m = Math.floor((elapsedSec % 3600) / 60);
        var s = elapsedSec % 60;
        el.textContent = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
      }
      pct = Math.min(63.9, pct + 0.03);
      var bar = $('#monBar'); if (bar) bar.style.width = pct.toFixed(1) + '%';
      var pctEl = $('#monPct'); if (pctEl) pctEl.innerHTML = pct.toFixed(1) + '<small>%</small>';
      $$('[data-timer]').forEach(function (t) {
        var v = parseFloat(t.dataset.timer) + 0.4;
        t.dataset.timer = v.toFixed(1);
        t.textContent = v.toFixed(1) + 's';
      });
      tickCountdown();
    }, 1000);
    setInterval(function () {
      if (state.paused || state.logPaused) return;
      var term = $('#logTerm');
      if (!term) return;
      var line = logLines[logIdx % logLines.length];
      logIdx++;
      var div = document.createElement('div');
      div.className = 'tl';
      div.innerHTML = '<span class="ts">' + line[0] + '</span><span class="lv ' + line[1] + '">' + line[1] + '</span><span class="msg">' + line[2] + '</span>';
      var cursor = term.querySelector('.cursor');
      term.insertBefore(div, term.firstChild);
      if (cursor) term.appendChild(cursor);
      while (term.querySelectorAll('.tl').length > 26) {
        var last = term.querySelectorAll('.tl');
        term.removeChild(last[last.length - 1]);
      }
    }, 2600);
  }
  function tickCountdown() {
    if (state.recovered) return;
    state.countdown--;
    if (state.countdown < 0) state.countdown = 0;
    var cd = $('#excCountdown');
    if (cd) cd.textContent = state.countdown + 's';
    var cb = $('#excCbar');
    if (cb) cb.style.width = Math.round(state.countdown / 8 * 100) + '%';
    if (state.countdown === 0) autoRecover();
  }
  function autoRecover() {
    var row = $('#excRateLimit');
    if (!row || state.recovered) return;
    state.recovered = true;
    row.classList.add('recovered');
    var ico = row.querySelector('.exc-ico');
    if (ico) { ico.className = 'exc-ico ok'; ico.innerHTML = '<svg><use href="#i-check"/></svg>'; }
    var title = row.querySelector('.exc-title');
    if (title) title.innerHTML = '429 限流 <span class="mono">model-router</span> · 已恢复';
    var desc = row.querySelector('.exc-desc');
    if (desc) desc.textContent = '退避结束，重试成功 · attempt 3/5 · 耗时 8.2s';
    var side = row.querySelector('.exc-side');
    if (side) side.innerHTML = '<span class="st ok" style="height:17px;font-size:9px"><span class="dt"></span>已恢复</span>';
    bumpExcBadge(-1);
    toast('ok', '429 限流已自动恢复', '退避 8s 后重试成功，运行继续');
  }
  function recoverExc(btn) {
    var row = btn.closest('.exc');
    if (!row || btn.classList.contains('loading')) return;
    btn.classList.add('loading');
    btn.innerHTML = '<span class="spinner"></span>';
    var isRate = row.id === 'excRateLimit';
    setTimeout(function () {
      row.classList.add('recovered');
      var ico = row.querySelector('.exc-ico');
      if (ico) { ico.className = 'exc-ico ok'; ico.innerHTML = '<svg><use href="#i-check"/></svg>'; }
      var title = row.querySelector('.exc-title');
      if (title) title.innerHTML = (isRate ? '429 限流' : '任务超时') + ' <span class="mono">' + (isRate ? 'model-router' : 'TreeSelect.vue') + '</span> · 已恢复';
      var desc = row.querySelector('.exc-desc');
      if (desc) desc.textContent = isRate ? '手动恢复：通道已切备用，QPS 恢复至 12/20' : '已切换浏览器实例并放行重试 · attempt 2/2';
      var side = row.querySelector('.exc-side');
      if (side) side.innerHTML = '<span class="st ok" style="height:17px;font-size:9px"><span class="dt"></span>已恢复</span>';
      if (isRate) { state.countdown = 0; state.recovered = true; }
      bumpExcBadge(-1);
      toast('ok', isRate ? '限流异常已恢复' : '超时任务已恢复', '运行继续 · 已写入异常处置记录');
    }, 1400);
  }
  function bumpExcBadge(delta) {
    var b = $('#navExcBadge');
    if (!b) return;
    var n = Math.max(0, parseInt(b.textContent, 10) + delta);
    b.textContent = n;
  }

  /* ---------------- workbench animation ---------------- */
  var wbStarted = false;
  var wbPct = 61.4;
  function startWorkbench() {
    if (wbStarted) return;
    wbStarted = true;
    setInterval(function () {
      if (state.paused) return;
      wbPct = Math.min(63.2, wbPct + 0.02);
      var bar = $('#wbBar'); if (bar) bar.style.width = wbPct.toFixed(1) + '%';
      var pctEl = $('#wbPct'); if (pctEl) pctEl.innerHTML = wbPct.toFixed(1) + '<small>%</small>';
    }, 2200);
  }

  /* ---------------- quality review demo ---------------- */
  function review() {
    if (state.reviewing) return;
    state.reviewing = true;
    var head = $('#reviewBtn');
    var row = $('#reviewRowBtn');
    var headHtml = head ? head.innerHTML : '';
    if (head) { head.classList.add('loading'); head.innerHTML = '<span class="spinner"></span><span>审查中…</span>'; }
    if (row) { row.classList.add('loading'); row.innerHTML = '<span class="spinner"></span>'; }

    var st = $('#loopStatus');
    if (st) st.innerHTML = '<span class="dt"></span>审查中';
    var stSub = $('#loopSub');
    if (stSub) stSub.textContent = '五信号重新采集…';

    toast('info', '重新审查已启动', '质量分析专家重跑五信号 · 预计 2.6s');

    setTimeout(function () {
      if (head) { head.classList.remove('loading'); head.innerHTML = headHtml; }
      if (row) { row.classList.remove('loading'); row.innerHTML = '重新审查'; }

      var score = $('#loopScore');
      if (score) { score.textContent = '69'; score.style.color = 'var(--warn)'; }
      var round = $('#loopRound');
      if (round) round.textContent = '3';
      var sub = $('#loopSub');
      if (sub) sub.textContent = 'behavior 81 · build 62 · 第 3 轮';
      if (st) st.innerHTML = '<span class="dt"></span>回环中';

            var radar = $('.radar-plot');
      if (radar) {
        radar.style.transformOrigin = '105px 98px';
        radar.style.transition = 'transform .5s ease';
        radar.style.transform = 'scale(.96)';
        setTimeout(function () { radar.style.transform = ''; }, 500);
      }
      var audit = $('#auditLog');
      if (audit) {
        var line = document.createElement('div');
        line.className = 'al-row';
        line.innerHTML = '<span class="al-time">17:23</span><span class="al-txt">TreeSelect.vue 69 &lt; 70 → 回环 #3（重新审查）</span>';
        audit.insertBefore(line, audit.firstChild);
      }
      toast('warn', '重新审查完成 · 69 分', '仍低于 70，进入第 3 轮回环；超过上限将升级人工门');
      state.reviewing = false;
    }, 2600);
  }

  /* ---------------- settings ---------------- */
  $$('[data-kernel]').forEach(function (opt) {
    opt.addEventListener('click', function () {
      $$('[data-kernel]').forEach(function (o) {
        o.classList.remove('on');
        o.setAttribute('aria-pressed', 'false');
      });
      opt.classList.add('on');
      opt.setAttribute('aria-pressed', 'true');
      if (opt.dataset.kernel === 'loopx') {
        toast('warn', 'LoopX Kernel 2.0.0a1 为实验内核', '当前未启用；保存后将在批次边界切换，建议先跑小批次验证');
      } else {
        toast('ok', '已选择自研 SQLite Kernel', '默认生产内核 · 支持断点续跑与回环调度');
      }
    });
  });
  var threshold = $('#thresholdVal');
  if (threshold) {
    var range = $('.set-card input[type="range"]');
    if (range) {
      range.addEventListener('input', function () {
        threshold.textContent = this.value;
        $('.gate-threshold .gt-num').textContent = '85';
      });
    }
  }
  $$('.stepper').forEach(function (sp) {
    var sv = sp.querySelector('.sv');
    if (!sv) return;
    $$('button', sp).forEach(function (btn) {
      btn.addEventListener('click', function () {
        var n = parseInt(sv.textContent, 10) || 0;
        n += btn.textContent.trim() === '+' ? 1 : -1;
        n = Math.max(0, Math.min(8, n));
        sv.textContent = n;
        if (sv.id === 'concurrencyVal') toast('info', '并发调整为 ' + n, '保存后生效 · 受配额与槽位限制');
      });
    });
  });
  var saveBtn = $('#saveSettings');
  if (saveBtn) {
    saveBtn.addEventListener('click', function () {
      saveBtn.classList.add('loading');
      setTimeout(function () { saveBtn.classList.remove('loading'); }, 600);
    });
  }

  /* ---------------- command palette ---------------- */
  var PAL = [
    { g: '页面', label: '工作台', kind: 'PAGE', icon: 'i-grid', meta: '运行总览', run: function () { go('workbench'); } },
    { g: '页面', label: '运行监控', kind: 'PAGE', icon: 'i-pulse', meta: 'LIVE', run: function () { go('monitor'); } },
    { g: '页面', label: '专家', kind: 'PAGE', icon: 'i-bot', meta: '8 registered', run: function () { go('agents'); } },
    { g: '页面', label: '技能', kind: 'PAGE', icon: 'i-layers', meta: '12 skills', run: function () { go('skills'); } },
    { g: '页面', label: '工作流编排', kind: 'PAGE', icon: 'i-flow', meta: 'v3', run: function () { go('flow'); } },
    { g: '页面', label: '记忆中心', kind: 'PAGE', icon: 'i-memory', meta: '128', run: function () { go('memory'); } },
    { g: '页面', label: '质量门控', kind: 'PAGE', icon: 'i-shield', meta: '91.0%', run: function () { go('quality'); } },
    { g: '页面', label: '设置', kind: 'PAGE', icon: 'i-sliders', meta: 'kernel / quota', run: function () { go('settings'); } },
    { g: '专家', label: '代码转化专家', kind: 'AGENT', icon: 'i-bot', meta: 'running', run: function () { go('agents'); openDrawer('transform'); } },
    { g: '专家', label: '质量分析专家', kind: 'AGENT', icon: 'i-bot', meta: '5 signals', run: function () { go('agents'); openDrawer('quality'); } },
    { g: '专家', label: '修复专家', kind: 'AGENT', icon: 'i-bot', meta: 'failed', run: function () { go('agents'); openDrawer('fix'); } },
    { g: '动作', label: '重新审查 TreeSelect.vue', kind: 'ACTION', icon: 'i-refresh', meta: 'quality', run: function () { go('quality'); setTimeout(review, 420); } },
    { g: '动作', label: '断点续跑当前运行', kind: 'ACTION', icon: 'i-corner', meta: 'run', run: function () { go('monitor'); toast('acc', '断点续跑已排队', '从批次 #16 检查点恢复'); } },
    { g: '动作', label: '新建专家 / 导入提示词', kind: 'ACTION', icon: 'i-plus', meta: 'agents', run: function () { go('agents'); toast('info', '新建专家：粘贴角色提示词即可创建'); } },
    { g: '动作', label: '切换内核 SQLite ⇄ LoopX', kind: 'ACTION', icon: 'i-cpu', meta: 'settings', run: function () { go('settings'); } }
  ];

  function renderPalette(q) {
    q = (q || '').trim().toLowerCase();
    var list = $('#palList');
    if (!list) return;
    var items = PAL.filter(function (it) {
      return !q || (it.label + ' ' + it.g + ' ' + it.meta).toLowerCase().indexOf(q) !== -1;
    });
    state.palItems = items;
    state.palIndex = 0;
    if (!items.length) {
      list.innerHTML = '<div class="empty" style="padding:26px"><div class="e-ico"><svg><use href="#i-search"/></svg></div><h4>没有匹配命令</h4><p>试试「专家」「审查」「内核」或页面名。</p></div>';
      return;
    }
    var html = '';
    var groups = {};
    items.forEach(function (it, idx) {
      if (!groups[it.g]) { groups[it.g] = []; }
      groups[it.g].push(idx);
    });
    Object.keys(groups).forEach(function (g) {
      html += '<div class="pal-group">' + g + '</div>';
      groups[g].forEach(function (idx) {
        var it = items[idx];
        html += '<div class="pal-item' + (idx === 0 ? ' sel' : '') + '" data-pal="' + idx + '" role="option">' +
          '<svg><use href="#' + it.icon + '"/></svg>' +
          '<span>' + it.label + '</span>' +
          '<span class="pal-kind">' + it.kind + '</span>' +
          '<span class="pal-meta">' + it.meta + '</span></div>';
      });
    });
    list.innerHTML = html;
    $$('.pal-item', list).forEach(function (el) {
      el.addEventListener('click', function () {
        var idx = parseInt(el.dataset.pal, 10);
        closePalette();
        state.palItems[idx].run();
      });
    });
  }

  function openPalette() {
    var wrap = $('#paletteWrap');
    if (!wrap) return;
    wrap.classList.add('on');
    var input = $('#palInput');
    input.value = '';
    renderPalette('');
    setTimeout(function () { input.focus(); }, 30);
  }
  function closePalette() {
    var wrap = $('#paletteWrap');
    if (wrap) wrap.classList.remove('on');
  }
  function movePalette(delta) {
    var items = $$('.pal-item', $('#palList'));
    if (!items.length) return;
    state.palIndex = (state.palIndex + delta + items.length) % items.length;
    items.forEach(function (el, i) { el.classList.toggle('sel', i === state.palIndex); });
    var cur = items[state.palIndex];
    if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'nearest' });
  }

  if ($('#searchBtn')) $('#searchBtn').addEventListener('click', openPalette);
  $$('[data-open-palette]').forEach(function (b) { b.addEventListener('click', openPalette); });
  if ($('#palInput')) {
    $('#palInput').addEventListener('input', function () { renderPalette(this.value); });
  }
  var palWrap = $('#paletteWrap');
  if (palWrap) {
    palWrap.addEventListener('click', function (e) {
      if (e.target === palWrap) closePalette();
    });
  }

  document.addEventListener('keydown', function (e) {
    var mod = e.ctrlKey || e.metaKey;
    if (mod && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      if (palWrap && palWrap.classList.contains('on')) closePalette();
      else openPalette();
      return;
    }
    var palOn = palWrap && palWrap.classList.contains('on');
    if (palOn) {
      if (e.key === 'Escape') { closePalette(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); movePalette(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); movePalette(-1); }
      else if (e.key === 'Enter') {
        e.preventDefault();
        var it = state.palItems[state.palIndex];
        if (it) { closePalette(); it.run(); }
      }
      return;
    }
    if (e.key === 'Escape') {
      if ($('#drawer').classList.contains('on')) closeDrawer();
    }
    if (e.key === 'Enter' && document.activeElement && document.activeElement.matches('[data-switch]')) {
      e.preventDefault();
      document.activeElement.click();
    }
  });

  /* ---------------- boot ---------------- */
  function boot() {
    var hash = (location.hash || '').replace('#', '');
    var page = PAGES[hash] ? hash : 'workbench';
    go(page, { silent: true });
    if (page === 'monitor') startMonitor();
    if (page === 'workbench') startWorkbench();
    if (page === 'skills') initSkills();
    $$('.switch').forEach(function (s) {
      if (!s.hasAttribute('tabindex')) s.setAttribute('tabindex', '0');
    });
    // subtle initial reveal of first-level panels
    var active = $('.page.active');
    if (active) animateBars(active);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
