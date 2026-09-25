# SD Pixel Processor 迁移计划 — 各向异性高光烘焙工具 Phase-2

> 修订日期：2026-09-25（静态审核修订）
> 状态：**原稿有阻断问题；已修订，仅放行执行者开展 Stage 0。** 本文未经实机验证，不代表 G2、完整迁移或生产验收通过。
> 审核重点：§4 API/参数所属层、§5.3 类型规则、§5.4 调试接口与 §6 配方；§7 为分阶段门禁，§8 为验收规则，§9 为风险清单。
> 执行者需同时持有：本文、`doc/PLAN.md`（总契约）、§2 列出的源码及冻结的资产/参数快照。未知项必须留痕，不作为既定事实。
> 本轮仅审核与修改本文，不运行实现、探针、测试或烘焙；后续代码与 SD 操作由专人执行。

---

## 1. 项目背景

### 1.1 Phase-1 当前链路与验证边界

本项目按 `doc/PLAN.md` 实现了一个 Python + moderngl（GLSL 330）离线烘焙工具，读取桌布资产的烘焙数据贴图，在纹理空间逐 texel 计算风格化卡通各向异性高光（位移切线 Kajiya–Kay 双层变体 + 卡通分段），导出 2048² PNG 光照颜色图。

**当前状态（区分历史报告、静态证据与尚未满足的门禁）**：

| 项 | 状态与证据边界 |
|---|---|
| 合成例 GPU/CPU 报告 | `validation/out/suite_report.json` 记录 72/72 通过；覆盖 `plane_n001/plane_tilted/plane_hole` 的导数/基底检查。是已有运行记录，不是本轮重跑，也不等于 PLAN G1/G2 全部用例已完成 |
| `--bake` 链路 | 现有源码和成品/报告存在；**当前报告为 `accepted_unverified=true`**，不能表述为实资产已无条件通过 |
| 交互预览（GLFW + ImGui 中文 UI） | 按交接记录可用；本轮只读源码，不执行验证 |
| 输入资产契约 | 已登记 10 张贴图，4 张参与主 pass；位置 scale/bias、空间以及 normalobj 轴向仍为未确认项，见报告 `blocking_errors` |
| 边界/padding 与 Unity | 不属于本次已验证交付；当前主链并未执行颜色延拓/padding，见 §8.3 |

GLSL 的表达子集适合机械映射为 SD 函数图，但**语法可表达不等于 C1–C9 全部通过**。采样、32F 全链路、坐标、宿主归一化、运行期所有候选安全性和参数校验仍要分别证明。

本次放行范围分两类：① 合成 fixture 的数值迁移可先推进；② 未确认实资产最多作为带假设的对照样本，不升级为生产认可。当前 `P=encodedP`（scale=1/bias=0）是现有实现假设；不能从位置 RGB 分布恢复真实轴向比例/单位，透视相机也必须使用同一已声明空间。基础契约未确认前，不能宣称 PLAN G0/G3 或完整 Phase-2 已通过。

### 1.2 新需求（Phase-2）

把同一计算链路迁移进 **Adobe Substance 3D Designer 的 Pixel Processor（PP）节点**：

- 用户在 SD 中把 4 张贴图**手动接入** PP 输入引脚；
- 光照方向 / 各向异性 / 高光 / 漫反射 / 曝光 / 观察模式等参数**暴露在 PP 节点属性面板**手动可调；
- PP 实时输出与现有 GLSL 链路同等结果的高光贴图，供用户在 SD/DCC 内直接验证与迭代。

**用户已确认的三项决策**（2026-09-25）：

| 决策点 | 结论 | 原因 |
|---|---|---|
| 枚举参数呈现 | int 滑块 0/1/2 + 注解说明 | 保留已确认的 UI 决策；不把“无法注册类型”泛化成“没有枚举/标签能力” |
| 交付形式 | Python 引导脚本（SD Python 编辑器执行），自动在当前 graph 搭建节点图 | 无需安装插件；可重复执行，但按 §7.1 先验证新副本，再经确认替换本脚本拥有的旧副本 |
| 调试输出 | 保留 DEBUG_MODE 1–9（coverage/dPdqx/Tuv/Buv/Ns/TAniso/所选层分段后高光/ndl/dPdqy） | 保持实际 GLSL RGBA 接口；DEBUG 7 不是 raw，详见 §5.4 |

### 1.3 明确的非目标

- 不修改 `D:\SD_Project\Plugins\` 下任何现有插件（只读参考）；
- 不做 `.sbsar` 导出配置与 sbscooker 流水线（后续独立任务）；
- 不改变 GLSL 侧工具的行为；`preview.py` / `aniso_bake.py` 保持原样；
- 不迁移 angle_map（角度控制图）与 thickness/curve/matid 等未启用贴图（契约 unverified，维持关闭）；
- 不做 Unity 回贴（PLAN 步骤 4，另行推进）。

---

## 2. 上下文关系

### 2.1 与 PLAN.md 的关系

| PLAN 条目 | 本计划对应 |
|---|---|
| §0 Phase-2「手工重建 Pixel Processor 节点图」 | 以脚本生成同一可编辑节点图；`GLSL Node` 只读参考，不进入依赖 |
| 步骤 3 / 门禁 G2「提前建立最小 PP 对照」 | Stage 0 的 0A–0E：API/采样/精度/安全数学/最小光照先验证；不能仅凭位置图直出宣布 G2 |
| 步骤 7「在已通过的 PP 探针上扩展」 | Stage 0 全部过关后再进入 Stage 1–4 |
| §6.2 一次输出编码 | Raw/色彩通路在 0C 先锁定，Stage 4 再验成品；PP1 数学数据不经 PP2 |
| §7 C1–C9 硬约束 | 目标不变；区分数值复刻与总契约达成。现有每texel差分尺度、缺少同岛限制/边界处理等差异明示，不以“迁移一致”自动豁免 |
| §10 数值验收 | §8 分别验证格式/有限性/alpha/数学/成品；不任意排除边界或0.5%超差像素 |
| §9 预留的 `.sbs` | 引导脚本之外仍交付通过门禁后保存的 `aniso_probe.sbs`、`aniso_lightmap.sbs` 与证据；保存重开验证，非仅运行时临时节点 |

### 2.2 与现有代码的关系（迁移源）

| 源文件 | 迁移内容 | 备注 |
|---|---|---|
| `shaders/aniso.frag`（219–355 主链） | PP1 全部计算 | 逐运算复刻，**不"修复"任何边界行为**（含 neighborValid 的 vec2 step 语义、末行/列失效） |
| `shaders/common.glsl` | safeNormalize / pickSign / pick3 / smoothSegment / hardSegment / segmented / linearToSRGB 的 SD 展开 | 见 §6 配方表 |
| `shaders/output.frag` | PP2（曝光/Reinhard/sRGB/填充） | 独立第二个 PP |
| `shaders/fullscreen.vert` | 不迁移 | PP 逐像素上下文等价于 `$pos` |
| `core/parameters.py` | 参数默认值/范围/校验 | SD 侧须有对应 schema/验证入口，不能用 slider 注解代替跨字段校验；见 §7.4–7.5 |
| `core/render_setup.py` | 参数→uniform/define 与宿主归一化 | light_dir/view_direction 的归一化也属于迁移语义；角度 UI 按完整精度转换，不能只照抄 shader |
| `gl/context.py:65-83` | defines 注入机制 | 验收用 DEBUG_MODE override 生成 GLSL dump，复用不改；每个模式立即保存读回，见 §8 |
| `out/bake_report.json` | 默认快照及未验证状态 | 规范 light_dir=(0.4,-0.6,0.7)、view_mode=normal_proxy 等；角度约−56.3°/44.1°只作显示；accepted_unverified 与 blocking_errors 也必须保留 |

**参与迁移的输入贴图（4+1 张）**：

| PP 输入序号（固定） | 贴图 | 格式 | 角色 |
|---|---|---|---|
| 0 | bake_position.png | 16-bit RGB | 位置场（差分方向核心输入） |
| 1 | bake_normalobj.png | 16-bit RGB | 按 *2−1 解码；契约登记单位向量编码 verified，但轴向/参考空间仍 unverified |
| 2 | mask1.png | 8-bit RGBA（R） | coverage，阈值 0.5（verified） |
| 3 | bake_ao.png | 8-bit（R） | AO，只压环境项（verified） |
| 4 | 受控中性细节法线占位 | Raw RGB 浮点 `(0.5,0.5,1)`（解码后 `(0,0,1)`） | 含 DETAIL 候选的图始终绑定此槽；真实细节图仅在基底/语义确认后替换，默认模式 off |

绑定按**语义清单**而非视觉上的从上到下顺序判断。0–4 的槽名/连接/采样索引须由 Stage 0 唯一标记图证明，并记录断线、重连和替换时的行为。运行期关闭 DETAIL 不等于该采样节点不会被求值；禁止引用不存在的 input4 后靠 ifelse 掩盖。

四张主输入全部按 Raw 数据处理；源文件 16 位不等于 SD Bitmap/上游节点输出仍保真。逐段确认导入、输入节点格式与尺寸继承、PP 采样及导出，不允许只把最终 PP 改为 32F 来掩盖上游降位/色彩转换。遮罩只取 R，不以 alpha 显示结果代替其数值。

### 2.3 与 SD 环境的关系

- **参考插件（只读）**：`D:\SD_Project\Plugins\renderer_sbsar\`（PP 创建/函数图/参数暴露的实战范式）、`glslNode\`（GLSL→SD 函数节点完整映射表）、`nodeTransition\`（API 陷阱记录）。
- **官方文档**：`C:\Program Files\Adobe\Adobe Substance 3D Designer\resources\documentation\pythonapi\html\`；关键官方示例：`resources\python\samples\sample_sbs_parameter_function.py`（函数图）、`sample_sbs_graph_inputs.py`（参数注解）、`sample_sbs_graph.py`（贴图接入）。
- **执行方式**：用户在 SD Python 编辑器执行 `sd/run_in_sd.py`；SD 已打开且含目标 graph。

---

## 3. 迁移目标架构

### 3.1 双 PP 串联

```
[bake_position]──┐
[bake_normalobj]─┤
[mask1]──────────┤   PP1: aniso.frag 核心链路        PP2: output.frag
[bake_ao]────────┤   输出 float4:                    输出 float4:
                 ├──►  RGB = 线性光照                 RGB = sRGB 成片
(可选 detail)────┘   A   = validity                 A   = 1.0
                          └── unique_filter_output ──► input ──► 用户导出（关色彩变换）
```

- 生产 PP1/PP2 均 `$format`=3（HDR 32F）并单独设 Absolute 继承；`$outputsize=int2(11,11)`、Absolute，表示 2048²。小型探针按 fixture manifest 同步设置输出尺寸与输入 texel；不得以父图继承意外改变基准。
- 分两个 PP 保持 core/output 双 pass 边界；PP2 只负责曝光/Reinhard/sRGB/无效背景填充，不包含颜色延拓/padding。调试输出从 PP1 原样截取。
- 图示表示数值架构，不预先保证原生 PP 面板能直接承载全部自定义参数。参数所属层/面板/多个实例隔离先过 0A；需要 wrapper 时按 §4.3 明确确认交付形式变化。
- 格式和继承设置必须读回并通过保真探针；PP 设置成功不证明 Bitmap 输入、上游节点、颜色管理和文件输出已经保真。

### 3.2 纯表达式 DAG；禁止中间状态，不禁止只读 get

保留**纯表达式 DAG + Python 局部 NodeRef 扇出**作为首选架构：中间量不使用 `set`/`sequence`，也不靠 `get` 读取某个先前写入的局部变量。**参数及 `$pos` 等上下文仍必须使用只读 `get_*`**；原稿“零 set/get”应理解为零可变局部状态，不能字面禁止参数读取。

| 维度 | 纯 DAG（选定） | 局部 set/get + sequence |
|---|---|---|
| 正确性 | 无局部写入顺序依赖；显式数据流 | 另需证明 sequence 求值顺序与变量作用域 |
| 可维护性 | 与 GLSL 局部表达式可机械对照 | 可缩短某些连线，但引入状态契约 |
| 成本 | 节点/深度/编译耗时待实测 | 不能未经测量就宣称固定多出 300 节点或必然更快 |

插件静态源码提供同一输出扇出的实例，但**不能据此保证引擎只求值一次、必然做 CSE 或任意深 DAG 都高效**。Stage 0/后续扩展记录节点数、最长依赖深度、首次编译和热更新耗时。只有测得明确瓶颈才另审架构调整，不自动退回状态链。

### 3.3 缓存策略（每个函数图独立）

| 缓存 | key 必含信息 | 范围 |
|---|---|---|
| 常量池 | 函数图标识、类型、维度、规范值 | 区分 bool/int/float；不能用 Python 中相等的 `True/1/1.0` 或 `False/0/0.0` 混用节点 |
| 广播池 | 函数图标识、源 NodeRef、目标维度 | 同源标量→f2/f3/f4 可复用 |
| 复合表达式 | 函数图标识、op、类型、全部输入 NodeRef 与常量 | cross3/planeFallback 可做同图内容寻址；不得在 PP1/PP2 之间共享节点 |
| safeNormalize | 默认不缓存；若以后缓存，key 必含 v/fallback/**minLen** | 阈值是语义输入，不能丢失 |
| specLayer / derivativeQ | 不把不同参数的调用合并 | 层间可共享完全相同的 mode/edge 子树；不同 spec/diffuse 参数不得误合并 |

重建后丢弃旧缓存，保留强引用的 NodeRef；不能把 SDK 包装对象的 Python `id()` 当成跨图、跨重建的持久标识。

### 3.4 编译期变体 → 运行期选择

GLSL 的 VIEW_MODE/ANISO_AXIS/SPEC_MODE/**DIFFUSE_MODE**/DETAIL_MODE/DETAIL_GREEN_SIGN/DEBUG_MODE/SPEC_LAYER_INDEX 转成明确的参数与纯值选择。**从编译期删除变成运行期候选，是需要验证的语义变化，不因主公式相同就自动安全。**

- 三选一用 §6 pick3；bool 和 float 掩码严格区分，int 模式显式转换。spec、diffuse 的 mode 与阈值不能误共用。
- 未选中的 directional 也不能 `normalize(0)`，DETAIL off 也不能引用未绑定 input4；全部候选先构造为有限值。源中裸 normalize 的位置（planeFallback、detail TBN 结果、directional）逐一登记前置条件/分母保护/有限 fallback，在 0D 单测，不能仅写一句“候选均有限”。
- 对源已定义的非退化合法域保持同值；新增保护的触发计数独立报告，不能擅自改变原有 core/debug alpha。若需要修改源的有效内域算法，停止并另审，不在迁移中静默修复。
- 调试级联必须按 **i=1→9** 构建：从 cand_0 开始，`out=SEL(gteq(debug_as_float,i-0.5),cand_i,out)`。参数限定整数 0–9；反向构建会被低编号覆盖。各 cand_i 的 RGBA 含义见 §5.4。
- 不依赖 ifelse 短路消除非法运算；也不预先保证所有候选都会实际算一遍或共享子图只算一次。这些是引擎求值/优化行为，成本按实际生成图测量。

### 3.5 节点预算

| 模块 | 估算 |
|---|---|
| 常量池 + 参数 get（~40 consts + ~39 gets） | 80 |
| q + 解码（含 planeFallback+safeNormalize） | 55 |
| derivativeQ ×2（含 neighborValid ×4） | 110 |
| buildBasis（含 planeFallback(N0)） | 80 |
| 细节法线（运行期可选） | 40 |
| Us/Vs/TAniso（cross3 缓存命中） | 65 |
| 视向三模式 + 半角 H + 光向 L | 42 |
| specLayer ×2（含 segmented ×2） | 约116（原稿单层约58，却把双层列为60，已纠正） |
| 漫反射/AO/合成 | 58 |
| 调试候选 + 级联 | 55 |
| PP2 输出 pass | 50 |
| **结构估算合计** | **约750，暂按700–1000量级预留；以实际发射统计为准** |

这些是结构估算，不是性能保证；类型修正、广播简化、阈值保护、缓存和参数作用域都会改变计数。**未找到可用于本项目的官方“2000节点硬上限”证据，删除据此计算的安全余量。**

按不同语义采样点计：position 中心+四邻居=5，mask 中心+四邻居=5，normalobj=1，AO=1，含 DETAIL 候选另加1，PP2再1。中心样本应显式复用 NodeRef；未去重或引擎展开可能更多。因此不能将“5次采样”或上述理论数量当实际 GPU 指令数，2048² 构建/编译/参数更新必须实测。

### 3.6 布局

**stage 分带 + 带内深度序**（不用全图重心序——600+ 节点全图排会把不同 stage 混进同一列）：

- 发射时打 stage 标签（shared=0, decode=1, derivX=2, derivY=3, basis=4, detail=5, aniso=6, view=7, half=8, spec1=9, spec2=10, combine=11, debug=12）；
- 坐标：`x = dag_depth × 220`；`y = band × 2000 + 带内行 × 160`；
- 12 带 × 2000 ≈ 24k px 高，与 aniso.frag 源码段落一一对应，按带导航排查最直接。

---

## 4. SD Python API 事实清单

> **[文档]**：本机官方 HTML/绑定定义；**[静态参照]**：插件源码中有调用，不证明本轮运行成功；**[历史实测]**：另有版本/操作/结果记录且仅对记录场景成立；**[待测]**：Stage 0 才能裁定。本次审核不新增任何实机验证结论。
>
> 下表 HTML 路径相对 `C:\Program Files\Adobe\Adobe Substance 3D Designer\resources\documentation\pythonapi\html\pythonapi\`；F=`modules/sbs_function.html`，C=`modules/sbs_compositing.html`。绑定源码位于 `resources/python/sd/api/`。

### 4.1 已有依据与其边界

| 环节 | 核实结果 | 等级/关键依据 |
|---|---|---|
| PP 创建与格式 | `graph.newNode('sbs::compositing::pixelprocessor')`；`colorswitch=True`；`$format` 接受 int/enum，3=HDR high precision 32F；`$outputsize=int2(11,11)` 为 2048² | [文档] C:4304–4325、6724–6726；**Absolute 继承须另外设置并读回确认**，非仅赋数值 |
| 输入引脚 | 基础 `input` 是 texture/VARIADIC；实例可产生多个引脚 | [文档] C:4412–4417；动态 pin id、序号稳定性仍待测 |
| 插件连接 helper | 筛选 `input*` 后取最后一个；没有检查是否为空，传入的 `dst_input_index` 没有参与选择 | [静态参照] `renderer_sbsar/sd_utils.py:82–96`；不能当作按索引连接的可靠接口 |
| 接线与函数图 | `newPropertyConnectionFromId`；取得 `perpixel` 属性后用 `getPropertyGraph`/`newPropertyGraph(...,'SDSBSFunctionGraph')` | [文档/静态参照] sdnode 文档、`sd_utils.py:34–41`；不对用户已有函数图无条件重建 |
| 采样节点 | `samplecol.pos:float2`、`__constant__:int2`、输出 float4；插件写 `int2(input_index,0)` | [文档] F:3878–3917；[静态参照] `node_builder.py:163–175`。**官方该条未解释两个常量分量；第二个 0 不能宣称为 mip0 或 Nearest** |
| tiling/寻址 | PP 存在独立 `$tiling` 属性 | [文档] C:4366–4372；实际 clamp/越界与 samplecol 的组合行为待测 |
| 位置上下文 | `get_float2('$pos')` 的静态用例存在；`$size` 为当前 PP 输出上下文，不可无条件代表任一输入尺寸 | [静态参照/待测] `node_builder.py:772–773`；原点、中心、实际值在 0B 锁定 |
| **参数所属层** | 官方示例及参考插件是在 **SDSBSCompGraph** 上 `newProperty`，不是 `fg.newProperty` | [文档/静态参照] `sample_sbs_graph_inputs.py:37–64`、`node_builder.py:844–879`。不能据此证明参数会出现在原生 PP 面板 |
| 节点级属性能力 | `SDSBSCompNode.newProperty(...)` 确实列在本机 API | [文档] `api/sd/api/sbs/sdsbscompnode.html:234–246`；PP 对具体类型、注解、面板及其 perpixel 名字解析的支持仍待测 |
| 参数读取/转换 | `get_float1` 访问 function/graph 浮点输入；int 用 `get_integer1`，再 `tofloat.value` 转 float | [文档] F:1451–1480、1646–1680、4699–4728；不得假定任意层同名参数可互通 |
| editor/label 注解 | `editor='slider'` 有 sbsar 实例范围问题的历史记录；label 注解也有记录 | [历史记录，未复测] `renderer_sbsar/doc/fix_rot_slider_range.md`；不泛化为原生 PP 面板必须如此，也不宣称 UI 只能显示 id |
| **lerp** | a、b 接同型 float1–4；**x 仅 float1** | [文档] F:2661–2700；原稿广播 x 的规则错误，已改 §5.3/§6 |
| 比较/选择 | 比较输出 bool；ifelse.condition 接 bool，两路同型 | [文档] F:2007–2041；bool 转数值掩码须显式 `SEL(cond,1.0,0.0)` |
| mul/mulscalar/pow/dot | 同型向量 mul 可用；mulscalar 的 scalar 是 float；pow 无需依赖混型；dot 输出 float | [文档] F:1155–1202、3234–3269、3323–3343、3699–3723 |
| sin/cos | 输入单位为**弧度** | [文档] F:1023、4178；度转弧度正确，不用 turns 或 FX-Map Pattern Rotation 替代 |
| 输出与布局 | 所用函数节点按定义的 `unique_filter_output` 接线；`fg.setOutputNode(node,True)`；`setPosition(float2(...))` | [文档/静态参照] 各节点定义、sdgraph/sdsbscompnode；构建器按实际类型与端口断言 |
| Undo 分组 | 绑定提供 `SDHistoryUtils.UndoGroup`；`__exit__` 会 commit，不会因异常自动 rollback | [文档] `sdhistoryutils.py:32–68`；没有由此获得暂停重算/提速保证 |

注意：参考插件的格式/参数设置代码存在捕获异常后继续的路径；“看见调用”不等于设置已生效。执行者须显式失败并记录实际读回值，禁止照搬吞异常的成功判定。

### 4.2 否定性结论必须限定版本与对象层

| # | 可采用的结论 | 不可推出的结论 |
|---|---|---|
| ① | 本机 SD API 采用 `getPropertyGraph`/`newPropertyGraph`，不混用其他 SDK 的函数图访问方法 | 不能把 pysbs/自动化工具包和 SD 内嵌 API 当同一接口 |
| ② | 本方案显式创建输入属性、注解与对应 get 节点，不依赖“一键暴露常量” | 不能因此跳过属性所属层、面板显示和名字解析验证 |
| ③ | 沿用用户确认的 int 滑块，不依赖自定义枚举类型注册；本机 `SDProperty` 未见直接 setLabel | 不能据此断言不存在 label/editor 注解或下拉呈现能力；已有类型枚举与注册新类型也不同 |
| ④ | 本机 F 文档列出的 85 个原生定义中未见 normalize/length/cross/step/clamp/sign/inversesqrt/smoothstep 同名原语，本版按 §6 展开 | 不是全部版本、库函数、可实例化函数图的能力全集；运行时能力以 `getNodeDefinitions()`/实际节点定义为准 |

### 4.3 仍须 Stage 0 实测的架构前提

- **参数面板与作用域**：分别验证 comp graph / PP node / perpixel function 的属性归属，至少 float/int/float3；两 PP 及两个迁移实例不能串读同名参数。若原生 PP 面板不支持目标形式，停止并提出“外层 comp graph 实例面板 + 内部双 PP”变体供确认，不能悄悄降级成只在根图面板调参。
- **samplecol、动态槽位、采样与坐标**：见 0B；常量第二分量和 `$tiling` 的实际语义须有证据，不按名字猜。
- **Raw/32F 导入导出**：见 0C；位深、RGB/alpha、负数/HDR、行序与色彩变换分别验证。
- **显式类型链与数值端点**：lerp.x 的文档类型已确定，不再列为“未知隐式提升”；0D 验证实现接线、bool/int 转换和安全域，而非用探针为错误类型规则兜底。
- **DAG 性能、可重复构建与持久化**：见 0A/0E；不从静态扇出代码或 UndoGroup 推导性能保证。

---

## 5. 计算链路与迁移决策对照

### 5.1 迁移链路（对照 aniso.frag:219–355）

先分别锁定 **输出 `$pos`→规范 q** 与 **规范 q→samplecol 坐标** 两个适配，不能预设 `q.y=1-$pos.y`。若目标版本两者均为左上原点，适配均为恒等。输入、PP1→PP2、文件导出行序都通过 0B/0C；q→网格 V 的负号独立于图像翻转，禁止凭成品镜像猜所有符号。

```
q = toCanonicalPos($pos)
coverage = S(0.5,SMP(2,q).r)
P = SMP(0,q).xyz                            # 当前源假设 scale=1/bias=0
N0raw = SMP(1,q).xyz*2-1
n0N = safeNormalize(N0raw,planeFallback(N0raw),1e-12)
N0 = n0N.xyz; nValid = n0N.w*coverage
xD/yD = derivativeQ(q,(1,0)/(0,1))
dPdu = xD.xyz; dPdv = -yD.xyz
[Tuv,tValid,Buv,bValid] = buildBasis(N0,dPdu,dPdv,xD.w,yD.w)
Ns = DETAIL off 的 N0 / 使用原始 Tuv,Buv,N0 的 detail 候选
usN = safeNormalize(Tuv-Ns*dot(Ns,Tuv),Tuv,1e-12)
Us = usN.xyz; h = pickSign(dot(cross3(N0,Tuv),dPdv))
Vs = h*cross3(Ns,Us); A = 按 ANISO_AXIS 选择 Us/Vs
TAniso = cos(theta)*A + sin(theta)*cross3(Ns,A)
Vn = pick3(受保护的单位 view_direction,
           safeNormalize(camera_position-P,(0,0,1),1e-12).xyz,
           Ns, view_mode)
hN = safeNormalize(L+Vn,(0,0,1),1e-12)
H = hN.xyz; hValid = hN.w
s1/s2 = specLayer(各层参数；共同 spec_mode/edge)
ndl = dot(Ns,L); facing = clamp(ndl*front_k,0,1)
specTotal = (s1.rgb+s2.rgb)*facing*(hValid*nValid)
diff = segmented(0.5*ndl+0.5,diffuse_mode,diffuse_edge0,diffuse_edge1,diffuse_threshold)
aoFactor = lerp(1,clamp(SMP(3,q).r,0,1),ao_strength)
aoDirect = lerp(1,aoFactor,ao_direct_light)
linear = ambient_color*ambient_intensity*aoFactor
       + light_color*light_intensity*aoDirect*(diffuse_color*diff+specTotal)
validity = coverage*nValid*tValid*bValid
```

DETAIL 候选保持源解码、绿色符号和强度中性值 `(0,0,1)`，不使用旋转后的 TAniso 解码普通 TS 法线；源 `applyDetailNormal` 的最终归一化也必须按 §3.4 闭合数值安全。

### 5.2 三处特殊处理

| GLSL 特性 | 位置 | SD 处理 |
|---|---|---|
| `inversesqrt` | common.glsl safeNormalize | `1/sqrt(max(len2,minLen²))`；实数公式等价不保证浮点位级相同，退化/阈值附近单测 |
| `#if` 编译期变体 | §3.4 列出的全部模式与符号/层选择 | pick3/ifelse；补齐宿主前置条件、只读参数与未选中候选安全性 |
| 多输出/局部量 | buildBasis 的 out 参数、derivativeQ 的 float4 返回 | Python NodeRef/元组组织数据流，不引入局部 set/get 状态 |

### 5.3 类型规则（发射器内建断言）

| 场景 | 规则 |
|---|---|
| f1 × f1 | `mul` |
| vecN × f1（任意顺序） | `mulscalar`：vec 接 `a`，标量接 `scalar` |
| vecN ± f1、vecN ÷ f1 | 标量广播到 vecN 再走同型运算；÷ 亦可 `mulscalar(v,1/s)`，先保护分母 |
| vecN × vecN | 同型原生 `mul` 支持逐分量相乘；不必拆分组装（本机官方定义已确认） |
| dot/pow/min/max | a、b 同型；本项目 dot 只用 f3×f3、pow 只用 f1×f1；这是子集选择，不是 API 上限 |
| **lerp** | **`a:fN、b:fN、x:f1 → fN`；x 必须是标量 float，禁止广播为 fN。** 官方 `sbs_function.html` 的 x 端口仅列 float |
| ifelse | `condition:bool`；ifpath/elsepath 同型；不依赖短路或惰性求值来保护非法运算 |
| 比较节点 | 本项目只接 f1；输出是 bool，不是 0/1 float |
| bool → f1 | `SEL(cond,C(1),C(0))`；不能把 bool 接进数值比较、mul 或 lerp.x |
| int 枚举 → f1 | int 属性 → `get_integer1` → `tofloat`（输入端口 **value**）→ 浮点比较；不让 `get_float1` 猜类型 |

C4 在 SD 中用纯值选择实现：`ifelse` 可作为 step/mix 的类型适配，但不能引入局部副作用或依赖未选中路径不执行。全部候选先保证有限。

### 5.4 调试与 alpha 是独立接口，不能合并

| DEBUG_MODE | PP1 RGB（保持现有源行为） | alpha |
|---|---|---|
| 0 | linear | coverage*nValid*tValid*bValid |
| 1 | `(coverage,0,0)` | core validity |
| 2 / 9 | `dPdqx/dPdqy*0.5+0.5` | 对应导数有效位 |
| 3 | `Tuv*0.5+0.5` | tValid |
| 4 | `Buv*0.5+0.5` | bValid |
| 5 | `Ns*0.5+0.5` | nValid |
| 6 | `TAniso*0.5+0.5` | usN.w*tValid*nValid |
| 7 | 由 SPEC_LAYER_INDEX 选择的 s1/s2：**分段后、层颜色/强度后，facing/最终合成前** | hValid |
| 8 | `(ndl*0.5+0.5,0,0)` | core validity |

- 源 DEBUG 7 的“未分段”注释与计算矛盾；以 `aniso.frag:211–215、339–345` 的实际代码为准。真正 raw 需独立验证小图/pass，不能改变原 1–9 的含义。V/H 等没有现成调试槽的量同理使用验证专用通路或解析 fixture。
- L+V=0 时 hValid=0，高光抑制，但几何 alpha 可以仍为 1；不能把有效表面填白。cameraPosition=P 使用源 perspective fallback，vpN.w 不进入最终 alpha。
- 源 mixedN.w、tiN.w、tAnisoValid 并非全部进入 core validity；不得“顺手增强”成所有有效位相乘。额外保护触发信息另做诊断，不偷改这些输出接口。
- 数学调试直接导出 PP1，保留 RGBA 和原映射；不经过 PP2 的曝光/Reinhard/sRGB/fill。若比较逆映射的原始向量，两侧都按同一公式逆变换，并登记阈值与量化预算。

---

## 6. 关键配方表（SD 节点级展开）

> `C(v)`=float1 常量；`C3/V3/V4`=同型常量/向量构造；`SEL(cond,a,b)`=ifelse，cond 为 bool；`CMP`=比较节点；`S(edge,x)`=下面的 float step；`SMP(idx,q)` 包含 §5.1 已锁定的规范 q→SD 采样坐标适配。所有示例是规格伪代码，实际发射严格按 §5.3 类型与端口规则。

### step / clamp

```
S(edge,x) = SEL(CMP('gteq', a=x, b=edge), C(1), C(0))
clamp(x,lo,hi) = min(max(x,lo),hi)   # 各操作数同型；需要时广播常量
```

等号取 1；CMP 输出 bool，S 输出 float。二者不能互换。

### safeNormalize(v, fallback, minLen=1e-12) → float4

```
eps2  = minLen * minLen             # minLen 是显式语义输入，有限且正
len2  = dot(v,v)
valid = S(eps2,len2)
prot  = max(len2,eps2)
inv   = 1 / sqrt(prot)
cand  = mulscalar(v,inv)
out3  = lerp(a=fallback,b=cand,x=valid)   # x 是 f1，绝不广播到 f3
return V4(out3,valid)
```

当前源调用 minLen=1e-12，对应 eps2=1e-24；若封装接受其他 minLen，就不能把 eps2 写死。输入/fallback 须有限，且 dot/平方不能溢出；“有限参数”本身不保证任意巨大数值运算不溢出。

### planeFallback(n) → float3

```
len2 = dot(n,n)
useY = S(len2*0.5,n.x*n.x)
ref  = V3(1-useY,useY,0)
c    = cross3(n,ref) + C3(0,0,1e-6)
cn   = safeNormalize(c,C3(0,0,1),1e-12)
return cn.xyz                         # cn.w 另存保护触发诊断，不改 core alpha
```

源 `aniso.frag:154–159` 最后是裸 `normalize(c)`。上面明确展开运行期候选的分母保护；在未触发保护的域上与源实数公式一致。**加 1e-6 不是对任意输入的无条件防零证明**（例如直接给函数 n=(0,1e-6,0) 可使 c=0），因此需要 0/近零/相消探针。保护是显式兼容性扩展，不声称源在退化域已经验证；cn.w=0 的样本单列，若改变源的有限有效内域结果，停止并另审，不能默默当作“逐运算相同”。

### cross3(a,b) → float3

```
rx = a.y*b.z - a.z*b.y
ry = a.z*b.x - a.x*b.z
rz = a.x*b.y - a.y*b.x
return V3(rx,ry,rz)
```

### pickSign(x) → float1

```
sgn = SEL(CMP('gteq',x,0), C(1), C(-1))
return SEL(CMP('gteq',abs(x),1e-6), sgn, C(1))
```

不要把 bool 再送入 `gteq(use,0.5)`。`|x|<1e-6` 返回 +1 与源一致；不是普通 sign(x)。

### pick3(m0,m1,m2,mode)

```
s05 = S(0.5,mode);  s15 = S(1.5,mode)
is1 = s05*(1-s15);  is2 = s15
return m0*(1-s05) + m1*is1 + m2*is2
```

向量与掩码相乘使用 mulscalar；mode 来自已验证的 int→float 链。所有候选先有限，零权重不能清除 NaN。

### smoothSegment / hardSegment / segmented

```
den = max(e1-e0,1e-5)
t = clamp((x-e0)/den,0,1)
smooth = t*t*(3-2*t)
hard = S(thr,x)
return pick3(clamp(x,0,1),smooth,hard,mode)
```

两层 spec 可共享同一 edge 子树，diffuse 用自己的参数。分母保护只保证运算域，不代替 `e0<e1` 等配置合法性检查。

### neighborValid / derivativeQ

```
inside(qn) = S(0,qn.x)*S(0,qn.y)
             *S(qn.x,1-texel_u)*S(qn.y,1-texel_v)
neighborValid(qn) = inside(qn)*S(0.5,SMP(2,qn).r)
qPlus/qMinus = q +/- dirQ*texel
Pc/Pp/Pm = SMP(0,q/qPlus/qMinus).xyz
vP/vM = neighborValid(qPlus/qMinus)
vsum = vP+vM; denom = max(vsum,1)
weighted = ((Pp-Pc)*vP + (Pc-Pm)*vM)/denom
valid = S(0.5,vsum)
return V4(weighted*valid,valid)
```

- 四个 inside 比较作用于两轴，使用**未做寻址裁切的** qn；采样器另按已验证的 Clamp 取候选。不要改成只检查当前差分轴，也不要把上界改成 1。
- 源返回每 texel 位移，**没有再除 `1/W` 或 `1/H`**；与总计划数学导数的尺度区别须记录。本迁移保持源调试幅度与阈值，不在 PP 单边“纠正”它。
- 源的末行/列失效及缺少 island ID 的限制保留为已知兼容行为，不据此宣称总计划的同岛邻域要求已满足。

### buildBasis 的阈值与有效位

```
TuCandidate = Pu - N0*dot(N0,Pu)
tuN = safeNormalize(TuCandidate,planeFallback(N0),1e-12)
Tuv = tuN.xyz
projLen2 = dot(TuCandidate,TuCandidate)
tValid = tuN.w*puValid*S(1e-16,projLen2)
handed = dot(cross3(N0,Tuv),Pv)
bValid = S(1e-12,abs(handed))*pvValid*tValid
h = pickSign(handed)
Buv = h*cross3(N0,Tuv)
```

`handed` 有效阈值 1e-12 与 pickSign 的 1e-6 不能合并。例如 handed=-1e-8 时可同时 bValid=1、h=+1；迁移不能擅自改为负号。

### 光向 L

```
az/el = 完整精度角度参数*(pi/180)
L = V3(cos(el)*cos(az),cos(el)*sin(az),sin(el))
```

SD sin/cos 为弧度。实数公式给出单位长度，float32 中仍须验证与宿主归一化基准的误差，不能据此保证阈值附近逐位相同。

### specLayer i

```
tiN = safeNormalize(TAniso+Ns*shift_i,TAniso,1e-12)
Ti = tiN.xyz
c = clamp(dot(Ti,H),-1,1)
sinTH = sqrt(max(0,1-c*c))
aniso = pow(sinTH,exponent_i)
iso = pow(clamp(dot(Ns,H),0,1),exponent_i)
raw = lerp(iso,aniso,anisoAmount)
shaped = segmented(raw,spec_mode,e0,e1,thr)
return V4(spec_i_color*(shaped*intensity_i),hValid)
```

这里 alpha 是 **hValid**，不是 tiN.w，也不是最终几何 validity。raw 与 shaped 分开；DEBUG_MODE 7 输出的是本函数结果而非 raw。

### linearToSRGB(c)（每通道）/ PP2

```
cm = max(c,0)
lo = cm*12.92
hi = 1.055*pow(cm,1/2.4)-0.055
encoded = SEL(CMP('gteq',cm,0.0031308),hi,lo)

c3 = max(lin.rgb,C3(0,0,0))*pow(2,exposure_ev)
ldr = c3/(C3(1,1,1)+c3)
srgb = V3(linearToSRGB(ldr.r),linearToSRGB(ldr.g),linearToSRGB(ldr.b))
rgb = SEL(CMP('gteq',lin.a,0.5),srgb,V3(fill,fill,fill))
out = V4(rgb,1)
```

bool 只连接 SEL.condition；若改用 lerp，权重必须先显式转 float1。fill 是编码后的背景值，保持源先曝光/Reinhard/sRGB、再按 alpha 选择 fill 的顺序；PP2 不承担 padding，也不用于数学调试导出。

---

## 7. 文件结构与实施阶段

### 7.1 计划交付文件（本轮只改本文，不创建以下实现）

```
sd/
├── run_in_sd.py          # SD Python 编辑器入口；受控创建/更新，不清理用户图
├── check_export.py       # 外部验收：RGBA/格式/参数/有效性/数值/成品逐项判定
├── dump_glsl_ref.py      # 外部基准工具：复用现有模块，不修改原烘焙/预览行为
├── README.md             # 环境、输入/参数、Raw 导出、q 映射、运行与失败恢复
├── aniso_probe.sbs       # 通过门禁后保存的小型探针包
├── aniso_lightmap.sbs    # 通过门禁后保存的可编辑迁移包（不是 sbsar）
├── validation/          # 合成 fixture、冻结基准 manifest、探针/对比报告
└── aniso_pp/
    ├── __init__.py
    ├── api.py            # 已验证 API 薄封装与能力检查
    ├── emitter.py        # 类型/作用域断言、缓存及运算展开
    ├── stages.py         # 数学 stage、调试打包与输出 pass
    ├── params.py         # 完整参数 schema、映射与校验
    └── builder.py        # 总装、owner 标识与安全重建
```

- 引导脚本替代人工建图操作，不替代 `.sbs` 与证据交付。保存后关闭/重新打开检查输入、参数和内部函数图仍可用；不得依赖参考插件或本机技能目录。
- 入口显式定位自身目录，`aniso_pp` 使用受控导入/重载；不要覆盖宿主 `sd` 模块。SD 进程内构图与外部 Python 基准/比较分开登记依赖，不假设 SD 内可 import 当前 moderngl/NumPy 环境。
- 用户手动接线与 builder 顺序必须闭合：先创建带固定输入占位及参数的骨架，再由用户替换指定连接，随后执行绑定验证；验证完成才进入该阶段计算/验收。另一种可行实现是预先选择输入后由 builder 接线，但不能同时要求“建图后手接”又假设建图时已有真实输入。
- **默认增量安全构建**：只在明确选定的 compositing graph 创建带持久 owner/版本标识的新副本；维护本脚本拥有的节点/resource 清单。禁止按模糊名称、位置或“当前 graph 所有节点”清旧；已有用户节点、连接与包文件不属于清理范围。
- 新副本验证成功后才允许用户确认替换本脚本旧副本；保存备份并说明参数/接线如何保留。异常时只清理本轮创建对象，旧图仍可用。Undo 分组须用已核实 API，**分组不等于事务回滚**，也不代替保存备份。新增/替换/取消与异常恢复在 Stage 0 演练。

### 7.2 Stage 0：拆成可判定的小探针，禁止只做位置图直出

| 子门禁 | 必测内容 | 通过证据 |
|---|---|---|
| **0A API/交付骨架** | 当前 graph 类型检查；创建 PP/函数图/输出；至少一个 float/int/float3 参数出现在预期面板，改值真实影响输出；保存重开；安全重建；类型与 pin 断言 | SD/API/engine 版本、属性/端口/格式/继承模式、UI 与持久化结果；若原生 PP 面板不能承载约定参数，在此停止并审定 wrapper 方案，不到 Stage 4 才改架构 |
| **0B 输入绑定与采样** | 0–4 号槽分别接唯一标记图；替换/断开/重连不会静默重排；非对称四角+横纵梯度；像素中心/半像素/±1 texel/越界采样；q 与采样地址分离验证 | 固定 idx→pin→语义映射；显式过滤/寻址/mip 设置；Nearest/Clamp 等价证据。所有数据输入保持 Raw，不启用 sRGB 解码/自动法线转换/隐式 resize |
| **0C 精度与导出** | RGB16 低位 fixture（相邻 uint16 只差 1，三通道不同）、负值/HDR/alpha 测试块，经 Bitmap/输入节点→PP1→PP2/数值导出→外部解码 | 保留低位；无 8-bit/half 中途降位；PNG16 回读样本按规定精确往返；32F 浮点通路及 alpha 保真。只设 PP `$format`=32F 不算通过 |
| **0D 安全数学与最小光照** | bool→float、int→float、向量组装/广播、lerp/pow；step 等号；可参数化 safeNormalize；零/近零向量；非 Z 法线的 0/±90/180° 旋转与镜像手性；L=-V；单层连续高光；输出编码块 | 独立已知答案 fixture + GLSL 对照，遵守 §8；区分运算公式错误和输入/导出错误 |
| **0E DAG 可执行性** | 代表性的深度/扇出、运行期选择的未选中候选、图构建/首次编译/参数热更新 | 无错误/NaN，保存节点数、最长路径和耗时；没有性能数据不得宣称“2048² 正常实时负载” |

`0A–0E` 全部给出证据才放行完整 Stage 1。可以按子门禁迭代小图，失败就停在该问题，不先搭完约 700 节点再反推原因。Stage 0 的通过不等于资产 G0、Unity 或生产 G3 通过。

### 7.3 后续阶段（每阶段通过才进下一阶段）

| Stage | 内容 | 执行者/用户操作 | 验收 |
|---|---|---|---|
| **1 解码+差分** | coverage/N0、derivativeQ×2、neighborValid；按输入 manifest 固定尺寸与 texel | 验证绑定后计算并导出 | DEBUG 1/2/9、N0 与各有效标记；中心/单边/缺邻居/末行列 fixture；§8 全图有效性与内域数值同时通过 |
| **2 基底+方向** | buildBasis、受控 detail、Us/Vs/A/TAniso、V/H 与归一化宿主语义 | 各模式参数化对照；运行期候选独立探针 | DEBUG 3/4/5/6 加专用 V/H/validity 探针，不能只测默认 normal_proxy |
| **3 高光+合成** | 双层、连续/平滑/硬分段、facing/wrap/AO/linear | 单层独立开关及关键交互配置 | DEBUG 7/8、原始高光专用探针、linear/alpha；全部正常与退化测试无 NaN/Inf，且满足 §8 |
| **4 输出+完整面板** | PP2、完整参数 schema/校验与面板布局；参数能力已在 0A 验证 | 同参数 raw/PNG 导出与交互性能记录 | 数学+有效性+成品验收；两种不同 HDR 高光经输出曲线后仍可区分；未知资产和未做的 padding/Unity 明示排除 |
| **5 收尾** | `.sbs`、README、manifest、探针/比较/性能报告与限制清单 | 保存重开，交接复查 | 无隐含插件依赖、结果可复现；提交/推送只按用户另行授权，不自动执行 |


### 7.4 参数清单（下表 41 项；schema 以实际注册/映射表为准）

默认值从冻结的 `out/bake_report.json` 快照取得；角度的展示近似不得写回数值基准。原稿约 37 项与实际表不符，构建报告须输出真实计数、类型、所属 PP/函数图、默认值、GLSL uniform/define 映射，不能靠估数漏注册参数。

| 分组 | 参数（id / 范围 / 默认） |
|---|---|
| 01_光照方向 | p_light_azimuth_deg(度；完整精度由 light_dir 推导，显示约 −56.3)、p_light_elevation_deg(度；完整精度推导，显示约 44.1)、p_light_intensity(建议 UI 0–4，1)、p_light_color(f3，1,1,1)、p_ambient_color(f3，0.06,0.07,0.09)、p_ambient_intensity(建议 UI 0–4，1) |
| 02_各向异性 | p_aniso_angle_deg(建议 UI ±180，0)、p_aniso_axis(int 0=u/1=v，0)、p_aniso_amount(0–1，1) |
| 03_高光 | p_shift1(±4，0)、p_shift2(±4，0.35)、p_exponent1(1–256，48)、p_exponent2(1–256，8)、p_spec1_color(f3，1,1,1)、p_spec1_intensity(建议 UI 0–4，1)、p_spec2_color(f3，1,1,1)、p_spec2_intensity(建议 UI 0–4，0.6)、p_spec_mode(int 0/1/2=continuous/smooth/hard，1)、p_spec_edge0(0–1，0.35)、p_spec_edge1(0–1，0.55)、p_spec_threshold(0–1，0.5)、p_front_k(有限正数，建议 UI 0.01–4，1) |
| 04_漫反射_曝光 | p_diffuse_mode(int 0/1/2，1)、p_diffuse_color(f3，1,1,1)、p_diffuse_edge0(0–1，0.30)、p_diffuse_edge1(0–1，0.50)、p_diffuse_threshold(0–1，0.5)、p_ao_strength(0–1，1)、p_ao_direct_light(0–1，0)、p_exposure_ev(−10–10，0，与现有校验器一致)、p_validity_fill(0–1，1；属于 PP2) |
| 05_观察模式 | p_view_mode(int 0=directional/1=perspective/2=normal_proxy，2)、p_view_direction(f3，0,0,1)、p_camera_position(f3，0,0,1) |
| 06_调试与系统 | p_debug_mode(int 0–9，0)、p_spec_layer_index(int 0–1，0)、p_detail_mode(int 0/1，0；真实资产未解锁时固定 off)、p_detail_strength(本迁移支持 0–1，0)、p_detail_green_sign(仅 −1/+1，1，不是含 0 的连续滑块)、p_texel_u、p_texel_v（由输入 manifest 派生，生产 1/2048） |

### 7.5 参数、输入尺寸与宿主预处理契约

- `params.py` 保存完整类型/默认值/范围/单位/分组/映射/验证器，而不是只有 slider 注解。`min/max/clamp` 的显示属性不能替代跨字段校验：`spec_edge0<spec_edge1`、`diffuse_edge0<diffuse_edge1`、有限数、合法枚举、非零方向、DETAIL 所需数据契约均要检查。
- 沿用现有 `validate_params` 对合法配置的判定；运行期始终计算的候选另做域保护。非法快照必须由 SD 导出/外部验收入口拒收并指明字段；直接绕过入口导出的文件不算已验证。面板编辑的跨字段错误须有可见诊断，不得靠 `max(edge1-edge0,eps)` 静默将错参变成另一种效果。若新增最小边距等更严格规则，列明支持子集并与总契约一致。
- int 枚举按 int 读入，再经显式已验证的 int→float 转换用于 0.5/1.5 比较；bool 只做 condition，不隐式参与加减乘除或 lerp 权重。绿色通道符号可用 int 0/1 UI 映射到 −1/+1，快照仍保存规范符号。
- 光色、环境色、两层 spec 色、diffuse 色均是线性 RGB。SD 颜色编辑器/色彩管理对参数的行为必须有非灰色探针；如果 UI 使用 sRGB，显式只解码一次。建议 UI 范围不等于源参数合法域；硬缩小范围必须声明为迁移支持子集。
- `core/render_setup.py` 会以 float32 归一化 light_dir/view_direction 并拒绝长度 `<1e-8`；SD 必须补上同等宿主语义，不能直接把用户任意长度的 view_direction 喂给 H。球坐标光向用完整精度角度生成，再校验单位长度。
- **接受 p_texel 参数化，但它是受约束的系统数据，不是艺术滑块。** 它必须来自位置图实际 W/H；四张主输入的尺寸/UV 对齐，PP1/PP2 输出尺寸一致。生产基准固定 2048²；小型 fixture 从同一 manifest 同时设置 W/H、texel 和输出 log2 尺寸。未知或不一致尺寸拒收，禁止隐式 resize 后仍宣称同输入。
- `$size` 属于当前 PP 输出上下文，不能无条件当输入尺寸。用户替换输入后必须重新验证绑定、尺寸、Raw 状态和哈希；技术参数与 manifest 一并保存。
- PP2 的 exposure/validity_fill 不应误注册为 PP1 内部孤立参数；两 PP 的宿主参数作用域和关联方式在 0A 决定并留证。保留 1–9 调试语义，不用 PP2 色调映射调试数据。

---

## 8. 验收方法

### 8.1 先锁定基准与文件通路

- `dump_glsl_ref.py` 复用现有加载、`build_uniforms`、`build_defines` 和 RenderContext；按模式覆盖 define，立即拷贝/保存每个 pass 的 float32 读回，不能把同一可复用 FBO 当成多份历史结果。每份 dump 登记实际 RGB/alpha 含义、是否经过调试可视化映射、尺寸、行序和模式。
- 基准包保存输入哈希、shader/宿主映射源码哈希、完整参数及有效 uniform/define、引擎版本、资产契约快照。旧 `bake_report.json` 是默认值来源，不是所有后续调参结果的真值；不同参数必须生成对应基准。不得覆盖现有成品来生成测试参考。
- **PNG16 是 16-bit 无符号整数格式，不是浮点格式。** 原始负向量/HDR 线性光照默认使用经探针验证的 **RGBA float32 EXR（FLOAT 通道，不是 HALF）**，或另一条已证明保真且记录了读取方法的 32F 通路。不能只凭扩展名或 PP 的 `$format` 宣称端到端 32F。
- PNG16 仅可用于已知 `[0,1]` 数据，或有逐通道显式 scale/bias、范围证明与无饱和检查的编码。比较时先逆变换，再登记量化误差；若 `x=b+s*u16/65535`，单次最近舍入误差上界为 `|s|/(2*65535)`，还须计入链路其他量化。没有范围证明的 HDR 不准借 PNG16 验收。
- 数值导出禁用显示变换、曝光、sRGB 转换、通道重排及 alpha 预乘。Stage 0 用负值、HDR、仅低位不同的样本、`A=0` 但 `RGB!=0` 的块验证整条写出/读回路径；缺 alpha、半精度降位或隐式裁切均阻断数学验收。

### 8.2 数学层、成品层与有效性分别判定

1. **有限性**：所有测试的全部 RGBA（包括未选中候选的独立探针、退化区和背景）NaN/Inf 数为 0；文件不存在、尺寸/通道不匹配或比较域为空，必须失败，不能得到“零误差通过”。
2. **有效性**：先对 coverage、derivative/frame validity 与 core validity 分别比较，报告全图 false-valid/false-invalid 数。对确定的 0/1 fixture 必须完全一致。禁止先取两侧有效域交集而把 SD 丢失的像素排除掉；有效 fallback 也不能冒充有效几何。
3. **数学层**：在预先锁定的参考有效内域比较 float32 数据，初始要求 `max|Δ|≤1e-4`、`RMSE≤1e-5`；同时检查向量单位长度、正交性、方向与手性。通过 16 位编码的样本按 §8.1 明示量化预算，不无理由放宽。
4. **成品层**：PP2 编码仅一次，PNG8 原始样本与同参数 GLSL 成品对照；有效内域每通道误差目标 **≤2 LSB**。报告最大误差、RMSE、达标比例及超差位置；原稿“99.5% 达标即可通过”删除，不能让任意 0.5% 大错像素被自动豁免。
5. **硬阈值例外**：直接构造 `x<threshold / x==threshold / x>threshold` 验证 `>=`。完整链路的临界像素如受浮点差异影响，另列原始量与阈值距离并调查，不能拿它解释不受控的大面积差异。任何放宽都要有样本、原因和审核记录。

### 8.3 比较域、模式覆盖与范围限制

- 参考内域由 GLSL `DEBUG_MODE=0` 的 core validity 及预先登记的 coverage/边界规则确定；调试模式自己的 alpha 单独按其真实含义验收，不能一律当 core validity。
- 本轮是**现有双 pass 行为的迁移**。静态核查 `aniso_bake.py:500–511` 只统计有效性后导出，没有调用有效域颜色延拓/padding；`padding_width=8` 的配置存在不等于边界处理已实现。因此不凭空排除“8 texel padding 带”，也不宣称迁移已满足 PLAN §6.1/G3。未来边界修复必须作为独立规格、独立对照再加入。
- 需分别覆盖：3 种 view、2 种主轴、spec/diffuse 各 3 种模式、两层高光独立变化、0/±90/180° 与非 Z 法线旋转、anisoAmount=0/1、AO=0/1、曝光上下界、L=-V、零/近退化向量、coverage 孔洞与各图像边界。采用单因素及关键交互用例，不要求盲目穷举全部笛卡尔积；默认配置一次通过不能代替这些测试。
- DETAIL_MODE 在真实基底/贴图语义未确认时只做受控合成 fixture，生产默认 off；perspective 的实资产结果只有在 P/相机空间与解码契约确认后才有几何意义。
- 两侧参数采用同一份完整精度快照；不能用面板显示的 `−56.3°/44.1°` 近似角度代替报告中的精确 `light_dir=(0.4,−0.6,0.7)` 再要求 1e-4 对齐。SD 从规范向量计算完整精度角度，保存最终规范方向；方向与视向都须覆盖 `core/render_setup.py` 的归一化处理。

### 8.4 分工与放行含义

- 执行者：开发脚本、生成基准、SD 探针、运行比较、保留版本与结果；用户按交接约定在 SD 接线/导出及做目视确认。
- 审核者：静态核查计划和证据、修订文档、裁定门禁；**本轮不运行代码、测试、Designer 或烘焙。**
- 数值迁移通过只证明声明范围内的行为对齐，不自动补齐资产 G0、完整 G1、边界/padding、Unity 或生产 G3。

---

## 9. 风险清单

| # | 风险 | 影响 | 门禁/规避 |
|---|---|---|---|
| 1 | lerp.x 接向量、bool 当 float、int 直接按 float 读取 | 发射失败或类型错配 | §5.3 类型断言；lerp.x 保持 f1；bool→SEL→f1，int→get_integer1→tofloat；0A/0D |
| 2 | comp graph 参数暴露被误当作原生 PP 面板能力 | 核心交互交付不成立 | 0A 先验证所属层、面板与名字解析；wrapper 变体需明确确认 |
| 3 | 动态输入索引重排、input4 空引用、采样常量含义猜错 | 采错图/候选非法 | 0B 哨兵图、固定占位和重接测试；记录所有设置，不凭 `int2(...,0)` 宣称 Nearest/mip0 |
| 4 | q 原点、采样地址、文件行序、网格 V 符号混在一个 FLIP_Y 中 | 镜像或手性错误 | 分别适配并测试；四角+横纵梯度+导数，不只看最终图朝向 |
| 5 | Bitmap/上游节点降位、half EXR、PNG16 负数/HDR 裁切、alpha 预乘 | 数学不保真或假通过 | 0C 全链路数据探针；§8 文件格式/通道/量化预算 |
| 6 | texel 与输入/输出尺寸不一致 | 差分与有效域错误 | manifest 同源生成技术参数、绑定后重验、拒绝隐式 resize |
| 7 | 运行期未选中分支非法、滑块不能覆盖跨字段校验 | NaN/Inf、错参静默变形 | 0D 候选单测、全图有限性、参数拒收及可见诊断；不以 mask 或 eps 代替校验 |
| 8 | debug7 被当 raw、alpha 全部改为统一 validity | 对照错位、正常表面被填白 | §5.4 RGBA 映射表和退化用例；先比较有效标记再比较 RGB |
| 9 | 先删旧图、UndoGroup 被当事务回滚 | 用户图/参数/接线损失 | §7.1 owner 清单、新副本先验证、确认后替换、异常恢复与保存重开 |
| 10 | 不带类型/图作用域的缓存、未经实测的深 DAG 性能保证 | 错类型/跨图引用/卡顿 | §3.3 类型化缓存；0E 与各阶段实测节点数/深度/编译及热更新时间 |
| 11 | 默认角度取显示近似、UI 色值与线性参数混用、视向漏归一化 | 假差异或高光位置错误 | 完整精度快照、有效 uniform 对照、非灰色色彩块及单位方向探针 |
| 12 | 用 72 个旧测试/带 unverified 成品替代资产与生产验收 | 结论越界 | 明示 §1/§8 范围；原样迁移不补齐同岛/padding/Unity，不宣布 G0/G3 完成 |

---

## 10. 本轮审核结论与放行条件

**原稿不能无条件通过。修订后保留双 PP、纯表达式 DAG、int 滑块、引导脚本和 1–9 调试接口；只允许执行者先开展 Stage 0 的去风险验证。**

### 10.1 五项设计裁决

1. **纯 DAG：保留。** 禁止的是可变中间状态，不是只读参数 get；编译复用与性能必须测量，不能未经证据退回 set/get，也不能用“低于2000上限”宣称安全。
2. **step：`x>=edge` 正确。** 比较产生 bool，再显式转 float 0/1；lerp.x 必须保持 float 标量，原稿广播规则已修正。
3. **p_texel：有条件接受。** 它是与真实输入尺寸绑定的系统参数，而非自由艺术滑块；替换输入必须重新验证。
4. **Stage 0：原范围不足，已扩展为 0A–0E。** 原生 PP 面板/作用域、采样与全链路32F、最小安全数学/旋转/单层高光必须先成立，不能留到完整图或 Stage 4 才发现结构性问题。
5. **否定性 API 与既有完成状态：降级到证据实际支持的范围。** 本机原生节点列表不等于所有 SD 能力；历史通过记录不等于当前版本重跑、完整 G1、资产 G0 或生产 G3。

### 10.2 执行者下一步必须提交的证据

- 0A–0E 每项的 SD/engine 版本、最小图/fixture、设置快照、实际输出与判断；失败项保留原始报错及定位，不靠改阈值绕过。
- 明确参数最终出现在哪个面板、输入槽映射、samplecol/tiling 组合语义、Raw/32F 导出读回路径及必要的坐标适配。
- 非退化合法域的数值/alpha 对齐；新增保护、未验证资产以及缺少的同岛/padding/Unity 条件单列，不能与迁移通过混报。
- 若必须引入 wrapper、改变源算法、缩小支持域或放宽验收，先记录并提交确认，再进入后续阶段。

**本轮工作边界：只审查并修订 `doc/SD_MIGRATION_PLAN.md`；未修改实现代码，未执行 Python/GLSL/SD/Unity、探针、测试、烘焙或 Git 提交。Stage 0 由专人按此文执行，本次不代为开始。**
