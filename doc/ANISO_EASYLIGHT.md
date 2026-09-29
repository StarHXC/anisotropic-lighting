# aniso_easylight — 灰度简化版光照节点

`sd/aniso_easylight.sbs` 是 `aniso_lightmap`（v6.2，35 参数彩色 RGBA sRGB）的
**去色简化衍生版**：删除全部颜色相关参数功能，11 参数灰度输出。
**旧节点未做任何改动**（保护清单 freeze check 通过，含 stages.py 在内零新增 diff）。

> **这是什么**：白光照明假设下的灰度光强层——KK 双层各向异性高光 + 漫反射 +
> AO 门控的**纯直射响应**（环境底光已置零）。不是彩色光照成品；
> 配色/环境光/曝光在引擎或外部节点完成。

## 1. 快速使用

1. **导入**：SD 里 File → Import 选择 `sd/aniso_easylight.sbs`
   （4 张贴图内嵌于 `aniso_easylight.resources/`，随包走）
2. **输出**：2048² **单通道灰度线性 Raw 32F**（HDR 域约 [0, 2.6]）——
   **0 = 无光照**，值 = 线性光强。**不是 sRGB 显示图**，不要直接当颜色看
3. **接引擎**：按数据导入当光照/亮度层；tone map/曝光/环境光在引擎侧做
4. **调参顺序**：光照定位 → 条纹方向/主轴 → 各向异性度 → 层锐度 → 遮蔽

## 2. 面板（11 项，4 组）

| 分组 / ID | 显示名 | 类型 | 范围 / 默认 | 语义 |
|---|---|---|---|---|
| 01_光照定位 / `p_light_azimuth_deg` | 光照方位 | float | [-180,180]° / -56.31° | 方向光定位（与旧节点/mask 同源全精度默认） |
| 同组 / `p_light_elevation_deg` | 光照仰角 | float | [-89,89]° / 44.15° | 同上 |
| 02_各向异性 / `p_aniso_axis` | 主轴（u/v） | int | 0/1 / 0 | KK 条纹主轴：0=沿 u，1=沿 v |
| 同组 / `p_aniso_angle_deg` | 条纹旋转角 | float | [-180,180]° / 0° | 主轴基础上整体旋转 |
| 同组 / `p_aniso_amount` | 各向异性度 | float | [0,1] / 1.0 | 1=纯拉丝，0=各向同性高光 |
| 03_高光形状 / `p_shift1` | 层1偏移 | float | [-4,4] / 0.0 | 主层切线偏移 |
| 同组 / `p_exponent1` | 层1锐度 | float | [1,256] / 48 | 主层窄聚/柔散 |
| 同组 / `p_shift2` | 层2偏移 | float | [-4,4] / 0.35 | 衬光层偏移（默认与层1错开） |
| 同组 / `p_exponent2` | 层2锐度 | float | [1,256] / 8 | 衬光层宽柔 |
| 04_遮蔽与双面 / `p_two_sided` | 双面光照 | int | 0/1 / 1 | v6.2 背光法线翻转开关（N·L≤0 门控） |
| 同组 / `p_ao_direct` | 直射光 AO | float | [0,1] / 0.0 | 0=直射不受 AO（旧默认），1=全量压制 |

## 3. 相对旧节点的删减与冻结（声明式简化）

| 删除项 | 处置 | 依据 |
|---|---|---|
| 5 个颜色参数（light/ambient/spec1/spec2/diffuse_color） | 冻结白色；**ambient 冻结黑色**（底光置零） | 去色需求 |
| light/spec1/spec2_intensity | 冻结 1.0 / 1.0 / **0.6**（旧默认双层配比） | 亮度外置 |
| spec 分段 4 项（mode/edge0/edge1/threshold） | 冻结旧默认 smooth(0.35/0.55/0.5) | 整形外置（mask 范式） |
| diffuse 分段 4 项 | 冻结 **mode=0 连续 half-lambert**（旧默认 mode=1） | 灰度光强层用连续漫反射 |
| front_k | 冻结 1.0 | 旧默认 |
| ao_strength | 冻结 1.0，语义并入 `p_ao_direct`（单旋钮） | 消除双参数混淆 |
| ambient_ao | 删除（随底光置零退场） | 死参数 |
| view 三件套 | 冻结 normal_proxy 烘焙语义 | mask 范式 |
| exposure_ev / validity_fill / PP2 输出级 | 整体删除（无曝光/Reinhard/sRGB） | Raw 线性契约 |

## 4. 输出契约

- 单一输出 `light`：2048²、单通道、**线性 Raw 32F**、域约 [0, 2.6]（HDR）
- coverage 外 / 无效几何区**精确 0**（validity 二值门控，与旧 PP2 同语义）
- 不做曝光、Reinhard、sRGB、gamma、归一化
- 数学：`light = luma(diffuse + KK双层×facing) × ao_direct × validity`
  （amb≡0；三通道恒等经 luma 合一——白光灰度化无色偏，M2 判据 max|r−g|≤1e-6 级）

## 5. 验证摘要（M0–M3 全部 PASS）

| 阶段 | 关键证据 |
|---|---|
| M0 | 保护清单 31 文件核对通过（stages.py 为 mask 项目已批准白名单差异，本轮零新增） |
| M2 | 仅 11 参数可见；1 PP+4 bitmap+1 output；三组哨兵（方位+90°/exponent=8/遮蔽）输出均显著变化；双实例隔离像素级一致；旧 lightmap 共存隔离位级一致 |
| M3 | **旧节点 parity**：等价性命题下与旧 lightmap 逆映射输出全图对照 max\|Δ\|=2.8e-5、RMSE=1.85e-6（4.19M 像素）；性能 new/old=1.008（死子树 ~0.8% 开销） |

详细报告在 `sd/validation_easylight/out/m2|/m3/`。

**等价性命题**（M3 已验证）：easylight 默认输出 ≡ 旧 aniso_lightmap 在
「五色全白(ambient 黑) + intensity 旧默认(1/1/0.6) + spec 分段旧默认 +
diffuse_mode=0 + view normal_proxy + exposure_ev=0 + validity_fill=0」
设置下、去掉 Reinhard/sRGB/exposure 后的线性亮度。

## 6. 已知限制

- 白光/固定光照假设；输出不是任意真实视角正确的反射
- 双面处理沿用 v6.2 艺术约定（N·L≤0 翻转门控），不宣称物理布料背面模型
- 旧节点的彩色观感（ambient 底色、卡通分段漫反射）不在本节点；
  需要旧观感请用旧节点，或外部串 Level/分段节点复原
- 死子树残留（白乘子/置零 amb/死分支）为复用代价，性能影响 ~0.8%
  （mask 项目同款裁定：先保证正确/复用/隔离，优化须在性能证据后另立工单）

## 7. 文件分工

```
sd/
├── aniso_easylight.sbs            # 新交付，不覆盖旧包
├── aniso_easylight.resources/     # 独立资源（4 张贴图内嵌）
├── build_aniso_easylight.py       # 独立入口（main guard）
├── aniso_easylight_tools/
│   ├── __init__.py
│   ├── schema.py                  # 11 参数、FREEZE_CONSTANTS、EXPOSED_MAP、合法域
│   └── builder.py                 # 新包/参数注册/resolver/build_core 复用/灰度尾部/保存
├── probe_easylight_build.py       # M2 构建探针
├── probe_easylight_verify.py      # M2 打包闭环探针
├── probe_easylight_m3.py          # M3 parity 探针
└── validation_easylight/
    ├── judge_m2.py                # M2 哨兵 + M3 parity 外部判定
    └── out/                       # 报告
doc/ANISO_EASYLIGHT.md             # 本文件
```
