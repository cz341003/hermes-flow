---
name: 迁移经验归纳
description: 把本轮迁移的失败、回环与修复提炼成可复用经验卡，去重合并后写入经验库供后续批次召回。
version: 1.0.0
id: experience-distill
phases: [fix]
tags: [vue2, vue3, memory, experience, distill, knowledge]
---

# 迁移经验归纳

每一轮修复都是知识资产。本技能把「某个文件为什么失败、什么条件下会再犯、怎么改才对」写成结构化经验卡，去重合并后写入经验库，让后续批次在转换前就能看到坑。

## Procedure

1. 收集输入：本 Run 的 batch 事件、`quality.json` 缺陷、`verify.json` 失败、`fix` 修复 diff、人工门驳回理由。只处理本轮真实发生过的失败，不臆造。
2. 对每条失败做根因归纳，回答六个问题：坑类型是什么、触发条件是什么、错误表现是什么、根因是什么、解法是什么、适用版本范围是什么。
3. 生成经验卡，字段固定：
   ```json
   {
     "category": "syntax|api|build|flow",
     "trigger": "filters 中的 formatter 被删除后模板仍调用 formatDate",
     "solution": "把 formatter 抽成 setup 内的 formatDate 函数或 computed，并在模板改调用名",
     "phase": "transform",
     "stack": {"vue": "2.6->3.5", "ui": "antdv 1.x->4.x", "build": "webpack->vite"},
     "versions": "vue>=3.2, antdv>=4.0",
     "files": ["src/views/UserList.vue"],
     "confidence": 0.9,
     "source_run": "run-20261018-xxxx"
   }
   ```
4. 坑类型判定：`syntax`（filters/mixins/v-model/this.$xxx）、`api`（router/pinia/antdv/ztree 事件名差异）、`build`（alias/env/less/依赖版本）、`flow`（批次过大、上下文截断、拆分策略）。
5. 去重：对 `trigger` 做归一化（小写、去标点、去具体文件名/行号、保留动词与关键词），用 token Jaccard 或嵌入相似度比较，`>= 0.82` 视为同一条；命中已有卡则合并 `files`、累加 `hits`，并更新更通用的 `solution`。
6. 写入经验库：调用 `flow_experience_add`（category、trigger、solution、phase、stack、versions），或用 `flow_experience_search` 先查重再写；禁止直接写 SQLite。
7. 标注技能锚点：把经验卡映射到对应技能（如 `filters` -> `vue3-transform`，`ztree` -> `vue3-antdv`），并给出「应补进技能 Pitfalls 的一句话」建议，供人工评审。
8. 输出本轮沉淀摘要：新增 N 条、合并 M 条、Top 3 高频坑、建议更新的技能。

## Pitfalls

- 不要把一次性环境问题写成通用经验（例如「本机 8080 端口被占」），否则会污染后续批次的召回结果。
- 不要把「模型没看懂」当根因；根因必须落到代码模式、版本差异或配置缺失。
- 经验卡不写版本范围就无法判断适用性，Vue3.2 与 3.5、antdv 4.0 与 4.2 的 API 可能不同。
- 同义经验重复写入会让召回列表被同一坑刷屏；必须先 `flow_experience_search` 再写。
- 经验描述不能只写「报错了」；`trigger` 要能让下一个人一眼判断「我的场景是否命中」。
- 不要记录密钥、内网地址、用户数据；`files` 只写相对路径。
- 不要把具体文件名写进 `trigger` 的核心语义，否则换一个项目就无法复用；文件名放 `files` 字段。

## Verification

- 每条经验卡都通过 schema 校验：`category` 在四类内，`trigger`/`solution` 非空，`phase` 属于六阶段，`versions` 非空。
- 去重后没有语义重复的卡；合并时 `hits` 已累加、`files` 已去重。
- `flow_experience_search` 能用关键词召回本轮写入的卡，且排序合理。
- 摘要给出新增/合并数量与 Top 3 高频坑，并列出建议更新的技能名。
- 经验卡中没有敏感信息与绝对路径。
