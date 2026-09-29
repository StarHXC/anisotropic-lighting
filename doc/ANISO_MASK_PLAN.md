# aniso_mask — 缎面风格各向异性高光 Mask 设计与交接计划

## Context

当前项目已完成 SD 迁移，Git 基线为 `2b113a3`（v6.2：双面翻转门控修正）。现有 `sd/aniso_lightmap.sbs` 是35参数的彩色光照节点，包含双层KK高光、颜色、环境/漫反射、AO及曝光；用户只需要高光分布Mask与少量形状控制。

**用户已确认：**

1. 输出已计算的灰度高光分布，不是给UE渲染器的Anisotropy/Tangent材质控制贴图。
2. 首版不增加局部方向图，使用少量全局滑块。
3. 主要外观是**缎面布料主高光**，不是夸张的头发式带状高光。
4. 后续新建 `E:\AI_Project\Anisotropic Lighting\sd\aniso_mask.sbs`，不能覆盖现有 `aniso_lightmap.sbs`。
5. 本轮仅做Markdown设计，不修改实现、不生成SBS、不运行SD/桥/测试。所有实现与验证由执行者负责。

**推荐路线：3个形状控制＋2个光照定位控制，独立灰度输出。** 放弃上一版“固定KK主层后取灰度”的方案；复用现有几何/坐标/采样基础，新增缎面风格的宏观椭圆高光形状函数。

## 1. 参考依据与适用边界

### 1.1 Cathy Shih 的实际交互设计（已核对源码）

只读核对了[仓库README](https://github.com/cathyhlshih/UnityURPAnisoHighlightHairShader/tree/2823efb6983c3b72ad46745185a61218122216c9)、[Shader Graph JSON及连线](https://github.com/cathyhlshih/UnityURPAnisoHighlightHairShader/blob/2823efb6983c3b72ad46745185a61218122216c9/UnityURPAnisoHighlightHair/UnityURPAnisoHighlightHair.shadergraph)。参考提交：`2823efb6983c3b72ad46745185a61218122216c9`，Unity 2022.3.16f1 / URP与Shader Graph 14.0.9。没有执行Unity或shader。

Graph暴露8个自定义属性，不含URP内建渲染开关：

| 属性 | 类型/默认 | 真实职责 |
|---|---|---|
| AnisoDir | Texture2D | 空间方向分布，经方向变换/归一化链影响高光 |
| Specular(R)Gloss(G)Null(B) | Texture2D | R乘高光强度；G×128接Power指数，控制锐度 |
| AnisoOffset | 数值，[-0.5,0.5]，默认0 | 加在方向与H的点积后，再乘180°、转弧度、sin、max、Power；不是本项目 normalize(T+shift*N) 的等价参数 |
| Fresnel | 数值，默认约0.28 | 视角相关反射权重，不是高光长宽比 |
| Cutoff | 数值，[0,1]，默认0.5 | 头发卡片透明裁切，不是高光阈值 |
| Diffuse | Texture2D | 底色/alpha |
| Normal | Texture2D | 普通表面法线 |
| Main Color | Color，默认白 | 染色 |

对方是**少量标量＋贴图承载空间复杂度**，不是用两个全局滑块替代所有造型。其README演示移动灯光和染色，方向与强度/锐度主要交给贴图。因此可以借鉴“控制职责分离”，但用户已选择无局部方向图，不能原样复制交互并宣称等价；其偏移公式也不能与当前KK的shift混同。

### 1.2 为什么缎面参考应优先于头发

缎面是织物组织/表面表现，不等于某一种纤维。头发与布料都含纤维，但织物外观还取决于经纬组织、纱线/股线几何、粗糙度与观察/照明方向。

| 参考 | 已核实内容 | 本项目采用/不采用 |
|---|---|---|
| [Irawan & Marschner, Specular Reflection from Woven Cloth, 2012](https://www.cs.cornell.edu/~srm/publications/TOG12-cloth.html) | 官方摘要以纤维特征、纱线几何、织法描述织物反射与纹理，并进行测量对照 | 作为织物外观依据；不搬整套纱线模型 |
| [Montazeri等, A Practical Ply-Based Appearance Model of Woven Fabrics, 2020](https://projects.shuangz.com/practical_cloth-sa20/) | 已读项目页/摘要：股线层级、反射与透射、精度和成本取舍 | 明确宏观近似的边界；未逐式精读论文，不声称复现其算法 |
| [LightWave Principled BSDF官方文档](https://docs.lightwave3d.com/2026/principled-bsdf.html) | 已读Roughness、Anisotropy、Rotation的独立控制定义；Sheen单列为掠射角附加项 | 借鉴成熟交互划分；不照搬其单位、完整BSDF或所有材质参数 |

**采用的是缎面宏观定向主反射的形状近似，不是完整缎面仿真。** 新函数由本项目定义，不冒充上述论文、Cathy源码、UE5 BRDF或完整GGX/Ward实现。

不加入经纬微结构、纱线几何、局部方向图、透射、SSS、独立sheen、颜色或双色双层高光。Sheen的边缘柔光不能替代缎面定向主高光；这些功能不是首版Mask的必需项。

## 2. 面板：3＋2，共5项

全部为float滑块；没有额外“高级”形状参数、颜色控件、模式枚举或调试组。

| 分组 / ID | 显示名 | 范围 / 初始默认 | 语义 |
|---|---|---|---|
| 01_高光形状 / `p_anisotropy` | 各向异性度 | [0,1] / 0.7 | 控制两轴展开的差异，0为各向同性；不是整体亮度倍率 |
| 同组 / `p_direction_deg` | 方向（织纹参考） | [0,180]° / 0° | 从现有U参考方向绕N右手旋转反射长轴；是局部三维方向，不是旋转UV图像 |
| 同组 / `p_roughness` | 高光粗糙度／宽度 | [0,1] / 0.5 | 越大越宽柔；本项目艺术映射，不等同于某引擎roughness贴图的数值 |
| 02_光照定位 / `p_light_azimuth_deg` | 光照方位 | [-180,180]° / 现有完整精度默认 | Mask使用的方向光定位 |
| 同组 / `p_light_elevation_deg` | 光照仰角 | [-89,89]° / 现有完整精度默认 | 同上 |

初始a/r为设计预设，实施阶段须用真实布料曲面确认可用性，不声称已完成视觉标定。光向默认仍来自 `(0.4,-0.6,0.7)`，读取 `aniso_pp.params.get(...).default` 的完整精度并冻结，不用显示近似值回写。

明确告知使用者：

- a=0仍有普通高光，不是全黑；整体叠加强度在外部Blend/Levels处理。
- 长轴方向以本节定义为准，不假定它永远等于真实纱线方向。180°为同一轴，90°交换长短轴。
- 光照/观察假设仍影响Mask；不承诺只靠两个材质滑块决定所有位置。
- 固定沿用v6.2的双面处理及 `normal_proxy` 观察假设，不增加相机/视向/双面开关；这也意味着输出不是任意真实视角正确的反射。
- 删掉头发式Shift、双层参数和分段阈值。需要进一步图形化整形时在节点外做，不在首版重新堆入滑块。

## 3. 新主高光的数学规格

### 3.1 复用几何，建立独立正交反射基底

取得当前核心已有的Ns、Us、L、H及有效位，保留v6.2实际 `N·L<=0` 翻转门控。**不消费旧linear RGB，不复用KK的raw/shaped结果。**

在新kernel中重新确认单位正交条件：

```
nN = safeNormalize(frame.normal, (0,0,1), epsLen)
N = nN.xyz
tN = safeNormalize(frame.tangent_u - N*dot(N,frame.tangent_u),
                   finitePlaneFallback(N), epsLen)
T0 = tN.xyz
bN = safeNormalize(cross(N,T0), finitePlaneFallback(N), epsLen)
B0 = bN.xyz
hN = safeNormalize(frame.half_vector, (0,0,1), epsLen)
H = hN.xyz
```

- `epsLen=1e-12`，所有候选先有限；保护触发与原有效位独立记录。
- B0是右手正交**反射轴**，不冒充作者UV的+V。原手性与基底有效性仍由现有几何链决定。
- `Vg = frame.geometry_validity * frame.tangent_validity * nN.w * tN.w * bN.w`。
- `Vh = frame.half_validity * hN.w`。
- 有效基底必须满足长度/正交误差≤1e-4；fallback只保护数值，不把坏几何变成有效表面。

方向旋转（弧度）：

```
theta = p_direction_deg*pi/180
T = cos(theta)*T0 + sin(theta)*B0
B = -sin(theta)*T0 + cos(theta)*B0
```

两轴一起旋转，不只旋转T而保留旧B。方向0°以现有U为参考，90°为其几何正交轴，不混同镜像UV的有向+V。

### 3.2 从两个滑块生成两轴宽度

```
a = clamp(p_anisotropy,0,1)
r = clamp(p_roughness,0,1)
alpha = 0.03 + 0.47*r*r
k = 1 + 7*a
alphaT = alpha*sqrt(k)
alphaB = alpha/sqrt(k)
```

- a=0：两轴相同；a=1：长短轴宽度比为8。
- r增大：两轴同时展开；r=0仍有非零下限，不生成数值奇异的理想镜面。
- `alphaT*alphaB=alpha²`用于解耦方向差异和基准宽度，**不代表能量守恒或屏幕白色面积恒定**。
- 最窄轴下界为 `0.03/sqrt(8)`，无需引入跨字段合法性约束。

### 3.3 归一化椭圆主瓣与遮罩

```
hn = clamp(dot(N,H),-1,1)
ht = clamp(dot(T,H),-1,1)
hb = clamp(dot(B,H),-1,1)
denH = max(hn,1e-4)
q = (ht/(alphaT*denH))² + (hb/(alphaB*denH))²
lobe = pow(2,-min(max(q,0),80))
frontHalf = bool_to_float(hn > 0)
facing = clamp(dot(N,frame.light),0,1)
M = clamp(lobe * frontHalf * facing * Vg * Vh,0,1)
```

解释与硬约束：

- 在半向量的局部斜率平面中，q=1是半高轮廓，形成可旋转的椭圆；q=0的主瓣值为1。
- 这是本项目的高光**形状函数**，不含完整BRDF的Fresnel/Smith/能量归一化，也不包含微观织法；不将其命名为论文完整模型。
- 不再使用 `mix(iso,KK,anisotropy)`，各向异性真正作用于两轴宽度；不保留毛发Shift或固定卡通台阶。
- `frontHalf` 用比较bool显式转float，不把bool接入浮点运算；den保护在选择之前生效。
- q上限只防止无意义的极端指数，不是NaN修复。有效单位输入和宽度下限可约束除法/平方在float32范围内；NaN/Inf输入仍拒收。
- facing只是局部朝光调制，不是自阴影。双面翻转是继承的艺术约定，不宣称物理布料背面模型。

## 4. 输出与资源契约

### 4.1 单一灰度输出

- 新wrapper资源标识 `aniso_mask`，单一输出标识 `mask`。
- 2048²、单通道灰度、线性Raw、32F；0为无高光，1为最大响应。
- coverage外及无效几何区为0，不填白、不扩边、不做padding。
- 不做曝光、Reinhard、sRGB编码、自动gamma、逐图最大值归一化或直方图拉伸；不要求每套灯光都出现值1。
- 文件导出可用Raw灰度PNG16；数学参考用经过dtype核实的float32 EXR/读回，不把half当float32。
- 作为SD Blend的mask/opacity使用。若进入其他引擎按数据导入，不直接接UE Anisotropy输入冒充材质参数图。

首选单个 `colorswitch=False` 的PP，最终function输出float1。M0须证明其samplecol读取彩色位置/法线仍正确；失败就停止，不偷偷交付RGB端口作为等价替代。

### 4.2 输入继承，资源独立

- 以当前旧SBS中真实绑定的 `filename` 解析打包资源，不按目录中1-/2-历史副本的时间猜输入，也不跟随已失效的Adobe临时 `filepath`。
- 保持现有core的4槽：0=position、1=normalobj、2=coverage、3=AO。
- AO只为复用当前构图器保留兼容槽，**不进入新主瓣或frame出口的依赖**，必须验证替换有限AO数据后Mask不变。
- 全部复制到新 `aniso_mask.resources/`，不在运行时依赖旧资源目录、原D:目录或临时文件。
- bitmap和PP均显式Raw/32F/Absolute尺寸。生产仅2048²；测试允许方形2幂尺寸，manifest同步驱动texel与输出。
- 当前core仅接受一个texel标量；拒绝非方形或不对齐输入，不隐式resize，不为本次任务扩展旧尺寸体系。
- 换资产沿用生成时绑定/内嵌流程；不新增image参数、方向图或相关XML注入。

## 5. 代码复用与唯一存量接口变更

### 5.1 不能再沿用上一版“薄适配取KK灰度”

当前 `sd/stages.py::build_core` 返回合成后的linear RGBA，没有公开N/T/H。新材料目标与KK形状不同，不能只把颜色设黑/白或换滑块名字。

为避免复制整套几何链，**计划只给该函数增加一个默认不启用的中间量收集出口**：

```
现有：build_core(fg, texel=..., param_resolver=None) -> (packed, meta)
拟增：build_core(fg, texel=..., param_resolver=None, *, frame_out=None)
返回：仍为原来的 (packed, meta)
```

`frame_out is not None` 时填入已存在的NodeRef，不为出口增加重复运算：

| key | 现有局部量 | 类型 |
|---|---|---|
| normal | Ns | f3 |
| tangent_u | Us | f3 |
| light | L | f3 |
| half_vector | H | f3 |
| geometry_validity | validity | f1 |
| tangent_validity | uValid | f1 |
| half_validity | hValid | f1 |

必须用 `is not None` 判断，不能让空dict被当作关闭。不得修改旧返回值、旧参数/默认值、求值公式或旧输出选择；默认路径前后节点构造与数值必须不变。所有出口NodeRef属于调用者的新FG，不跨图/实例共享。

### 5.2 新节点装配

1. 新package/wrapper、5个float参数、4张独立bitmap。
2. 调用现有core，传入冻结的v6.2兼容参数resolver和空frame_out。只把两项灯光参数映射为用户输入；view_mode=normal_proxy、two_sided=1，其他旧参数为有限合法常数；未知源pid报错。
3. 新a/theta/r仅进入新kernel，不影响旧KK参数。丢弃旧packed作为输出，不从旧linear取值。
4. 在同一FG中用frame_out和现有Emitter构建§3的基底与主瓣；设置M为最终输出。
5. 不创建PP2，不注册颜色控件，不执行旧生成脚本。

原core可能仍发射无用的KK/颜色子树；本版不保证编译器全部消除或一定提速。先保证正确、复用与隔离，优化须在性能证据后单独提出。

### 5.3 复用的现有模块

- `sd/aniso_pp/emitter.py`：NodeRef、typed算术、safe_normalize、cross3、dot3、sin/cos、pow、step/sel、clamp。lerp.x保持f1，比较bool显式转float。
- `sd/aniso_pp/api.py`：create_pp、get_perpixel_graph、connect_pp_input、new_param及现有注册范式；实际绑定必须验证，不能只信参数名。
- `sd/aniso_pp/params.py::Param/get`：数据结构/完整精度默认值来源，不修改共享PARAMS列表。
- `sd/aniso_pp/readback.py::compute_and_save`：执行者读回；明确输出pin，检查失败和dtype。
- `sd/stage3_pp2.py`：只参考new package、CopiedAndLinked bitmap、output、保存范式。**不能import或执行它**，因为其顶层会重建旧SBS。

## 6. 文件分工与保护边界

以下为执行者将来创建/修改的工单，本轮只写本计划：

```
sd/
├── stages.py                    # 唯一存量代码变更：可选frame_out兼容出口
├── aniso_mask.sbs               # 新交付，不覆盖旧包
├── aniso_mask.resources/
├── build_aniso_mask.py          # 独立入口，main guard
├── aniso_mask_tools/
│   ├── __init__.py
│   ├── schema.py                # 5参数、固定常量、合法域、版本与源快照
│   ├── kernel.py                # 正交反射基底、两轴宽度、椭圆主瓣
│   └── builder.py               # resolver、frame收集、新包/输出/保存
└── validation_mask/
    ├── reference.py             # 独立CPU/解析参考
    ├── cases.py                 # 几何/参数fixtures、manifest
    ├── judge_mask.py            # 数值、有效性、不变量、回归/隔离
    └── out/<run_id>/
doc/
└── ANISO_MASK.md                # 新节点使用、参考与限制
```

**不可覆盖/修改：**旧 `aniso_lightmap.sbs`、`aniso_lightmap.resources/**`、`stage3_pp2.py`、`aniso_pp/**`、GLSL、旧参数文档/报告/成品。`stages.py`仅允许上述兼容出口，不能借机重构或修其他问题。

保护要求：

- 冻结HEAD、工作区状态、受保护文件/资源哈希；旧SBS及资源交付前后必须零变化。
- frame_out扩展前保存临时legacy核心数值基准；扩展后默认关闭出口路径必须完全回归，不能仅检查旧SBS文件没变。
- 新图/资源/报告使用独立命名空间。新结果先保存独立临时目录并验证，再发布；已有非本工具所有的同名文件拒绝覆盖。
- 不全量卸载包/清缓存，不删用户当前图的节点；只管理新Mask自有对象。模块/包身份不明时使用干净验证会话。
- 新包及资源目录单独移到不含旧包/原资产路径的位置后仍可求值，证明独立交接；这由执行者测试，本轮不移动文件。

## 7. 分阶段目标与门禁

采用M0–M3，不重跑旧迁移全部阶段，也不重开已裁定的项目范围。

| 阶段 | 实现目标 | 验收/产物 |
|---|---|---|
| **M0 基线与新出口探针** | 冻结输入/旧产物；保存legacy核心基准；增加frame_out；验证灰度PP的彩色samplecol分量、4槽、float1/Raw32F；常量0/0.5/1和RGB16低位 | 默认legacy路径数值不变、旧SBS/资源哈希不变；collector同图、类型齐全；灰度输入/输出无降位或gamma |
| **M1 新主瓣与交互映射** | 新schema/kernel；解析/合成曲面；a/theta/r与两轴宽度、正交基底、保护与validity | §8数学/不变量通过；5项参数无跨字段调节负担；视觉上形成柔和定向主高光，不以旧KK外观相同为目标 |
| **M2 新SBS交付闭环** | 2048²真实资产、新package/resources、5参数、单灰度输出、保存重开、多实例 | 仅5项可见；无颜色/Shift/sheens等额外控件；参数实际生效；资源可独立携带；新旧实例互不串参 |
| **M3 完整验收与文档** | 数值矩阵、Raw文件、Blend接入、性能/回归、使用说明 | 所有门禁通过后交付新SBS；差异与限制留痕，不拿旧项目PASS替代新Mask验收 |

失败只处理本阶段允许文件。若必须修改旧公式、增加参数、改变输出或扩张资源范围，先提交设计变更。

## 8. 验收方法

### 8.1 数学、精度与有效性

- 全图中间量/输出NaN/Inf均为0；空输出/空比较域、错尺寸/通道/dtype直接失败。
- 有效N/T/B/H单位长度与正交误差≤1e-4；基底fallback触发与有效域单独报告。
- 最终M在[0,1]；coverage外/几何无效区精确0。记录clamp前的范围，不靠clamp掩盖计算错误。
- 非退化有效内域float32对照初始 `max|Δ|≤1e-4, RMSE≤1e-5`；有效性先单独比较，禁止取两侧有效域交集隐藏错判。
- 旧项目的25个阈值临界像素不是新Mask自动白名单；新差异须逐项定位原始值、阈值和影响域，不任意扩张边界豁免。
- PNG16数据写出舍入检查与端到端数学误差分开统计；0/0.5/1标定块不得被gamma改变。EXR明确FLOAT，不是默认HALF。

### 8.2 必测不变量

| 用例 | 预期 |
|---|---|
| a=0、改变theta | Mask不变；使用非零非饱和fixture，不能全黑假通过 |
| a>0、theta旋转90° | 长短轴作用交换；有可解释的方向响应 |
| theta+180° | 同一轴，Mask一致（数值容差内）；不再有Shift破坏周期 |
| r递增 | 固定其他输入时响应逐点不下降，主瓣展开；不要求屏幕像素宽度线性变化 |
| 主瓣独立探针 | H=N时lobe=1；局部斜率落在对应alpha轴上时q=1、lobe=0.5；最终Mask另计facing/gates |
| a=1与r=0等极值 | 无零轴宽/除零/NaN/Inf；长短轴宽度比按k定义，不把a当亮度 |
| hn<=0、H退化、坏基底 | 所有候选有限，最终Mask按有效位为0，不从任意fallback绘出假高光 |
| AO/旧KK/颜色隔离 | 改变有限AO数据或非几何旧参数不影响新Mask；依赖图与数值均确认 |
| 镜像/旋转UV | 方向遵守已声明的反射基底，周期/正交正确，不把B0误当有向+V |
| 双面基线 | 保持现有N·L<=0门控、normal_proxy假设；边界附近无非有限值或额外假有效区 |

几何fixture至少含普通平面、斜向法线、旋转/镜像UV、孔洞、末行列、退化邻域。真实布料资产用于视觉/集成验收，不代替解析测试。CPU参考必须独立计算§3，不能把新PP输出再读一遍当真值。

### 8.3 交互、性能与不破坏旧节点

- 5项滑块逐项验证；两个新实例用不同参数得到独立结果，修改新实例不得影响另一实例或旧lightmap。
- Mask接外部Blend遮罩端，用外部颜色验证混合；配色和叠加强度留给使用者，新节点不加颜色输入。
- 保存/关闭/重开，参数和bitmap仍在；新包加新资源目录可独立交接。
- frame_out=None时旧核心与扩展前基准数值一致；frame_out启用但仍选择旧packed输出也必须一致，证明收集器不改算法。
- 同机同尺寸记录旧/新首次求值、预热后多次更新的中位数/P95、节点数/资源开销。若新热更新时间超过旧基线25%，需要分析整改，不降低精度或暗改旧公式；不拿旧单个探针耗时冒充整图真值。
- 旧SBS/资源及保护列表哈希不变；stages.py差异仅为批准的兼容出口。报告包含版本、输入哈希、固定值、5参数快照、诊断和实测结果。

### 8.4 后续执行入口

SD内由执行者使用现有 `sd-bridge` 流程或Python编辑器运行新入口，复用readback；外部在现有验证Python环境运行 `validation_mask` 的fixture/reference/judge。结果仅写新目录，不执行旧生成脚本。

**以上均为将来验收步骤，本轮没有执行，也没有将目标标成PASS。**

## 9. 完成标准与使用说明

执行者最终交付：

1. 新 `sd/aniso_mask.sbs` 与独立 `.resources`。
2. 新生成模块、唯一兼容出口变更及其旧路径回归证据。
3. M0–M3数值/交互/性能/隔离报告与 `doc/ANISO_MASK.md`。
4. 明示：这是固定光照/normal_proxy假设下的缎面风格宏观主高光Mask，不是完整BRDF、纱线仿真、自阴影、透射或局部织纹生成。

建议调参顺序：默认光照 → 调方向 → 调各向异性度 → 调粗糙度/宽度 → 必要时调整光照定位；颜色、整体强度和进一步图形化整形在节点外完成。

**本轮只交付本Markdown设计。不得据此自动实施或覆盖当前交付物。**
