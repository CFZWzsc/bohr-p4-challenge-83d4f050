---
name: biological-pathway-diagrammer
description: Use when biological entities and their regulatory interactions must be turned into a compartment-aware pathway diagram with typed edges and an auditable legend.
---

# 生物机制图与通路图

## 用途与适用条件

从机制描述或实体/关系表中抽取生物实体（基因、蛋白、复合物、细胞类型、亚细胞区室）与调控关系（激活、抑制、结合、修饰、转运），生成带区室分层、上下游方向、分支与反馈环的通路图结构规格，并把颜色、线宽、箭头样式与图例、数据编码逐项对齐。

适用条件：`/input/case.json`（或 `--case`）提供机制段落、实体表、相互作用表或通路描述，要求输出可编辑通路图与导出件。典型键：`entities`、`relations`/`interactions`、`compartments`、`encodings`、`legend`。

不适用：不做统计推断与显著性计算；不发明来源中没有的基因名、表达量或置信度；不判断机制本身是否成立。

## 输入

- `/input/case.json`：主输入。
- `/input/task.md`：存在时补充通路类型、区室要求与导出格式。
- 引用的本地文本/JSON/CSV 会被实际读取；缺失登记到 `errors`/`uncertainty`。
- 仅标准库；不联网、不写 `/input`。

## 处理流程

1. **读入材料**：case.json、task.md、引用文件，记录来源哈希。
2. **实体归一**：读取显式实体；缺失时按名词后缀与英文符号抽取。区分基因（italic 规范）与蛋白（roman 规范），识别复合物、细胞类型与区室。
3. **关系语义映射**：把“激活/促进/上调”映射为 activation，“抑制/阻断/下调”为 inhibition，“结合/互作”为 binding，“磷酸化/泛素化/降解”为 modification，“转运/分泌/易位”为 transport；记录原文证据。
4. **区室与拓扑**：按文本与显式字段给实体分配区室（胞外、膜、胞质、细胞核、线粒体等）；按关系方向计算上游—下游层级，识别分支与反馈环。
5. **图例与编码**：为每种关系类型生成线型、箭头、颜色图例；若存在数值编码（表达量、显著性、置信度），生成视觉通道映射并标注数据来源。
6. **一致性校验**：悬空端点、自环、基因/蛋白同名混用、区室缺失、方向缺失、反馈环、图例缺项、编码无数据来源。
7. **导出与绘图**：实际写出 `figure.svg`、`figure.png`、`figure.pdf` 与 `figure-spec.json`；逐项记录字节数/SHA-256、渲染器与 dpi，未导出则如实 `false`。
8. **契约落盘**：保留 `case_id` 与全部 `output_contract` 字段。

## 评分维度对应

- **实际效果**：实体类型正确、相互作用可区分、通路方向与区室位置成立。
- **完整性**：实体、边、分支/反馈环、图例、编码、导出六类要素齐备。
- **可核验性**：每条边带原文证据与来源；实体带类型与区室依据。
- **创新增益**：机制文本到图元/边的结构化映射、箭头语义判定、区室约束布局。
- **可靠体验**：命名歧义、缺方向、矛盾时显式标记并降级。

## 输出契约

`/app/output/result.json` 顶层保留 `case_id`、`output_contract` 全部字段、`status`、`result`、`evidence`、`uncertainty`、`errors`、`stats`、`skill`、`challenge_id`、`contract_notes`。未支持字段写 `null` 并记录原因。

主要交付段：`result.mechanism_spec.entities`、`result.mechanism_spec.edges`、`result.mechanism_spec.pathway_order`、`result.mechanism_spec.legend`、`result.consistency_checks`。

## 异常处理

| 情况 | 处理 | 输出表现 |
|---|---|---|
| 缺 case.json/非法 JSON | 结构化失败 | 退出码 `2`，`status=insufficient_input`/`failed` |
| 无实体或无关系 | 不编造网络 | `status=partial`/`insufficient_input` |
| 基因与蛋白同名 | 保留并标规范差异 | `gene_protein_same_symbol`，提示 italic/roman 区分 |
| 关系方向不明 | 保留无向边 | 标 `direction_missing`，不臆断上下游 |
| 受体区室未知 | 不硬放膜上 | 标 `compartment_unknown`，保留占位 |
| 数值编码无来源 | 不生成色阶 | 标 `encoding_without_source` |
| 存在反馈环 | 保留并按环标注 | `pathway_order.feedback_loops` |
| PNG/PDF 渲染工具缺失 | Pillow 缺失时用纯 Python 栅格兜底 | 记录 renderer/dpi；仍失败则 `performed=false` 并写明原因 |

## 限制

区室与方向主要来自显式字段和有限文本线索；跨句指代、通路数据库 ID 映射与亚细胞定位证据不在本 Skill 范围内。`figure.svg` 由确定性布局直接写出，PNG/PDF 由同一图元树导出。

## 最小调用示例（示例，非官方案例结果）

```bash
python scripts/run_skill.py --case /input/case.json --out /app/output/result.json
```

示例输入（示意）：`entities` 含受体 A（protein, membrane）与激酶 B（protein, cytoplasm），`relations` 一条 activation。示例输出（示意）：`status="success"`，`edges[0].arrowhead="solid_arrow"`，`pathway_order.layers` 为两层。仅为示例，不代表官方固定案例结果。


## Quickstart

在包根目录执行：

```bash
python scripts/run_skill.py --case examples/demo-case/case.json --out ./demo-output/result.json
```

- 演示案例：`examples/demo-case/case.json`（合成信号通路：5 个实体、4 条关系；纯合成，不代表真实通路）。
- 输出：`result.json`、`figure.svg`（区室横带 + 定向箭头 + 关系标签）与 `figure-spec.json`；每个节点/边带 `文件:pX.sY` 锚点，`exports`/`provenance_and_changes`/`compliance_checks`/`content_map`/`exceptions` 均为真实内容。

## 执行保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--output` 指定。
2. 再完成脚本无法自动完成的实质工作（译文、论述、图表、修订、结论等），把结果写回 `result.json` 对应字段。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 按契约取 `success`/`partial`/`insufficient_input`/`failed`（缺输入或证据不足时用 `insufficient_input`/`partial`）；无 `pending` 占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

### 真实图稿与预览（本 Cycle 必做）

- 脚本只输出规格（如 `editable_source.produced=false`）时，调用 Agent 必须依据规格真实写出可编辑 SVG 到 `/app/output/`：实体、区室、边、箭头、标签、图例均为可编辑元素。
- PNG（300 dpi）与 PDF 由同一图元树真实导出，并记录渲染器与 dpi；无 Pillow 时退化为纯 Python 栅格预览，并在 `result.json` 写明原因。
- 仅当文件真实落盘、可打开并核对后，才将 `editable_source.produced` 与 `export_plan[].performed` 置 `true`，并写入路径、字节数与 SHA-256；未执行的检查项如实写 `false` 与原因，不伪造渲染或检查结果。
