# 生物机制图与通路图 Skill

把 `case.json` 与来源材料里的实体、区室与调控关系画成一张分层可编辑的 SVG 通路图，
并同时导出 300 dpi 的 `figure.png` 与 `figure.pdf`。全部用 Python 标准库实现，离线、确定性。

## 使用

```bash
python scripts/run_skill.py --case examples/demo-case/case.json \
    --out /app/output/result.json --work /app/work
```

- 输入：`case.json`（`case_id`、`output_contract`、材料路径或正文）、`task.md`、来源材料。
- 输出：`result.json`（契约键：`case_id`/`status`/`editable_source`/`export_artifact`/
  `content_map`/`compliance_checks`/`exceptions`，另含 `evidence`/`uncertainty`/`stats`）、
  `figure.svg`、`figure-spec.json`、`figure.png`、`figure.pdf`。

## 设计要点

- **不编造**：实体、关系、区室只从材料原文抽取；每条边带 `data-source-anchor` 与 `data-quote`，
  未落到句子的候选实体写入 `exceptions`，不画。
- **方向语义**：激活/抑制/结合/修饰/转运分别用实线箭头、T 端、无向连线、虚线、空心箭头，
  图例逐项对应，颜色取自色盲友好色板。
- **可编辑**：所有文字为 `<text>`，图层 `layer-bands` / `layer-edges` / `layer-nodes` / `legend`
  语义化命名，节点 `node-Nx`、边 `edge-<id>` 可直接定位修改。
- **可核验**：`figure-spec.json` 记录节点坐标、边、图例、哈希；`compliance_checks` 逐项给出
  文件写入、锚点覆盖、箭头标记、图例覆盖、画布包含、PNG 非空白像素等检查结果。
- **确定性**：布局只依赖有序节点/边列表，无随机数与时间戳，双跑逐字节一致。

## 验证

```bash
python scripts/run_skill.py --case examples/demo-case/case.json --out /tmp/r1/result.json --work /tmp/r1
python scripts/run_skill.py --case examples/demo-case/case.json --out /tmp/r2/result.json --work /tmp/r2
# 两次产物 sha256 应完全一致
```
