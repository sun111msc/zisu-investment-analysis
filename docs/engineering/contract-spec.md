# 数值契约规范

## 为什么需要契约

金融分析里的错误大多不是「算错」，而是**口径错误**。三类高频问题：

**单位混用。** 营收「57.5」是元、万元还是亿元？毛利率「89.8」是百分数还是小数？
一个把 0.898 当 89.8 用的模型，输出的所有结论都错，而数字本身看起来毫无异常。

**时点错配。** 用年度报告的数据去解释当期的估值倍数，
但没有任何字段记录这个数据是什么时候的 —— 三个月后回看，无从判断。

**来源丢失。** 一个数字在报告里流转五轮之后，已经没人知道它来自哪里，
也无法复现。想核对时只能重做一遍。

契约层的目的不是「更严格」，而是**让这三类错误在产生的那一刻就暴露**，
而不是等到结论里变成一个看起来合理的错误数字。

## 七属性

```python
@dataclass(frozen=True)
class TypedValue:
    value: float | None       # 数值本体；None 表示缺失
    unit: Unit                # 量纲
    semantic: str             # 语义标签
    as_of: date               # 时点
    source: str               # 来源标识
    currency: str | None = None       # 币种
    frequency: Frequency = Frequency.POINT
    missing_reason: str | None = None # 缺失时必须填写
```

| 属性 | 取值 | 作用 |
|---|---|---|
| `value` | float 或 None | `None` 是**合法状态**，代表「缺失」。刻意不允许用 0 代替 |
| `unit` | `CNY` / `SHARES` / `PERCENT` / `RATIO` / `RATIO_TTM` / `COUNT` | 量纲参与算术传播，不同量纲相加直接报错 |
| `semantic` | `revenue` / `pe_ttm` / `gross_margin` / … | 决定该数值能否被某类数据源提供 |
| `as_of` | ISO 日期 | 时效校验的输入 |
| `source` | 已登记的数据源 ID | 与登记门禁联动，未登记源产出的数值无法溯源 |
| `currency` | `CNY` / `HKD` / `USD` / `EUR` | 跨市场比较的前提 |
| `frequency` | `point` / `annual` / `quarterly` / `ttm` / `daily` | 防止把 TTM 当年度值用 |

## 缺失是合法状态

```python
v = TypedValue.missing(
    unit=Unit.CNY,
    semantic="accounts_receivable",
    as_of=date(2026, 6, 30),
    source="financials.statements.primary",
    reason="该科目未在报告期披露",
    currency="CNY",
)
```

两条强制约束：

1. **构造缺失值必须给出原因。** `value=None` 且 `missing_reason` 为空会抛
   `MissingValueError`。
2. **缺失值不参与运算。** 任何算术操作遇到缺失值会抛 `MissingValueError`，
   而不是把 `None` 当 0。

加总时，任一分项缺失则整体缺失：

```python
total = sum_values([seg_a, seg_b, seg_c])   # seg_b 缺失 → total 也是缺失
```

这条规则挡住了「缺项按零计」这种会在报告里制造假精确的处理 ——
最终体现在 `GATE-41`。

## 量纲参与算术

```python
net_income.add(revenue)     # 都是 CNY，可以相加
gross_margin.add(revenue)   # PERCENT + CNY → UnitMismatchError
net_income.over(revenue)    # CNY / CNY → RATIO
ratio.to_percent()          # RATIO → PERCENT
cash_cny.to_currency(1.08, "USD")
```

刻意**不做**隐式换算。量纲或币种不一致时直接报错，
因为「自动帮你转换」正是静默错误的来源。

## 校验码

`TypedValue.validate()` 返回违反清单：

| 码 | 严重性 | 条件 |
|---|---|---|
| `C001` | ERROR | 语义标签为空 |
| `C002` | ERROR | 来源为空 |
| `C003` | ERROR | 时点字段非法 |
| `C004` | ERROR | 货币金额缺少币种 |
| `C005` | ERROR | 未知币种 |
| `C006` | WARNING | 百分比量级可疑（>1000），疑似百分数与小数混用 |
| `C007` | ERROR | `*_share` 语义的比值不在 [0,1] |
| `C008` | WARNING | TTM 数值的时点不在月度/年度节点 |

只有 `ERROR` 会让 `GATE-02` 失败。`WARNING` 会出现在契约层但不阻断分析 ——
这一区分很重要，因为把所有异常都设为阻断会让系统无法使用。

## 序列化

```python
v.as_dict()
# {'value': 100.0, 'unit': 'CNY', 'currency': 'CNY', 'frequency': 'annual',
#  'semantic': 'revenue', 'as_of': '2026-06-30',
#  'source': 'financials.statements.primary', 'missing_reason': None}
```

七个属性全部落盘，因此任何一次分析的历史产出都可以在新版本代码下重新校验。

## 与数据源门禁的联动

契约里的 `source` 字段不是自由文本 —— 它必须对应注册表中已登记的数据源 ID。
未登记的源在 `GATE-01` 就会被拦截，因此**不可能出现无法溯源的数值**（`GATE-42` 兜底校验）。

这两个设计是配套的：契约提供「记录来源」的能力，登记门禁提供「来源必须合法」的约束。
只有前者，来源可以是编的；只有后者，来源可能丢失。两者结合才闭环。
