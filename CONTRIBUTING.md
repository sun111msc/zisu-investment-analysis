# 贡献指南 / Contributing

感谢参与。本项目对贡献的核心要求只有一条：**任何进入分析链路的数值，必须可追溯。**

## 开发环境

```bash
git clone https://github.com/sun111msc/zisu-investment-analysis.git
cd zisu-investment-analysis
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
make check
```

## 四条不可协商的规则

| # | 规则 | 理由 |
|---|---|---|
| 1 | **禁止引入未登记数据源** | 数据源必须先在 `datasources/registry.py` 登记，未登记的源在闸门层直接拒绝 |
| 2 | **禁止用零值填充缺失数据** | 缺失必须显式标记为 `MISSING`，由三态输出机制处理 |
| 3 | **禁止裸 float 进入分析链路** | 所有数值须包装为 `TypedValue`（七属性契约） |
| 4 | **禁止绕过闸门** | 闸门不可被 `--skip-gate` 之类开关关闭；如需放行，必须在 ADR 中记录并修改规则本身 |

## 提交前检查

```bash
make check    # = lint + test + eval
```

- `ruff` 无告警
- `pytest` 全绿
- `evals` 基线不劣化（新增规则须在 `evals/injections.py` 补一条对应注入）

## 新增一道闸门

1. 在 `src/zisu/gates/rules.py` 实现规则函数，签名固定：
   ```python
   def gate_xxx(ctx: GateContext) -> GateResult: ...
   ```
2. 在 `GATE_CATALOG` 中登记编号、阶段、触发条件
3. 更新 `docs/engineering/gate-catalog.md`（**必须**，文档与代码同源）
4. 在 `tests/unit/test_gates.py` 增加正反两例（通过 / 拦截）
5. 在 `evals/injections.py` 增加一个能触发该闸门的注入样本

## 新增一篇 ADR

架构决策记录格式：`docs/engineering/adr/NNNN-kebab-title.md`

```markdown
# NNNN. 决策标题

- 状态：提议 / 已采纳 / 已废弃
- 日期：YYYY-MM-DD
- 影响：高 / 中 / 低

## 背景

## 决策

## 备选方案

## 后果

## 否决记录（如适用）
```

**记录「否决了什么、为什么否决」与记录「采纳了什么」同等重要。**

## Commit 约定

```
<type>(<scope>): <subject>

type: feat | fix | docs | test | refactor | chore | eval
scope: contracts | gates | pipeline | datasources | valuation | forensic | docs | evals
```

例：`feat(gates): 增加 GATE 44 数值契约七属性校验`

## 不要提交

- 真实持仓、账户、资金、交易指令
- 任何个人身份信息
- 平台特有的本地路径或私有配置
- 未脱敏的分析结论或标的池

## 行为准则

技术讨论对事不对人。评审关注可追溯性与可复现性，而非结论是否「正确」。
