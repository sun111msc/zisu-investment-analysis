# 评测体系

这个目录回答一个别处都没回答的问题：**这套系统有多准？**

绝大多数 Agent 项目的 README 只能证明「能跑」，不能证明「跑得对」。
本目录把「对不对」变成可重复执行的数字。

## 四个指标

| 指标 | 定义 | 为什么重要 |
|---|---|---|
| **State Accuracy** | 实际三态与预期一致的比例 | 系统对「该不该出结论」的判断是否正确 |
| **Gate Agreement** | `must_pass` / `must_fail` 清单的命中比例 | 每道闸门是否在它该响的时候响 |
| **Hallucination Catch Rate** | 注入型样本中，被成功拦截的比例 | ⭐ 最有信息量的指标：错误数据能不能被挡住 |
| **Mean Pass Rate** | 各样本间闸门通过率的均值 | 整体健康状况，用于检测基线漂移 |

其中 **Hallucination Catch Rate** 是核心。做法是**故障注入**：
拿一个本来能通过的样本，往里面塞一类典型错误，看系统是否拦下。

## 八类注入

注入定义在 `injections.py`，每个注入同时声明**期望拦截它的闸门** ——
断言因此是可证伪的：漏拦会被 `hallucination_catch_rate` 直接暴露。

| 注入 | 模拟的真实事故 | 期望拦截闸门 |
|---|---|---|
| `unauthorized_source` | 用通用网页检索去拿估值数据（越权语义） | GATE-01（R002） |
| `unregistered_source` | 用了一个没登记的数据源 | GATE-01（R001） |
| `zero_fill` | 查不到的数据用 0 代替 | GATE-41 |
| `single_line` | 跳过业务拆解直接给结论 | GATE-11 |
| `weak_bear` | 空头论证敷衍了事 | GATE-16 |
| `no_market_cap` | 缺市值仍给出估值结论 | GATE-50 |
| `shallow_chain` | 产业链退化成行业口号 | GATE-12 |
| `zero_peers` | 清空可比样本仍下结论 | GATE-51 |

## 运行

```bash
make eval
# 或
PYTHONPATH=src python evals/run_eval.py --out evals/reports/latest.md
```

## 基线

`baselines.json` 记录当前基线。CI 在 PR 上跑评测，任何指标低于基线即失败 ——
这样新规则的引入必须证明自己，而不是悄悄降低标准。
