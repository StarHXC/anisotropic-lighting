# aniso_lightmap 参数面板说明

> 适用交付物：`sd/aniso_lightmap.sbs`（v4，34 参数）
> 面板位置：选中实例 → **INSTANCE PARAMETERS**（5 个分组，折叠展示）
> 数学依据与验收证据见 `PHASE2_COMPLETION.md`；本文面向日常调参。

---

## 快速上手：最常调的 6 个

| 想做什么 | 调哪个 | 在哪组 |
|---|---|---|
| 转动光照方向 | **光 azimuth / elevation** | 01 |
| 光强/色调 | 光 强度、光颜色(Color) | 01 |
| 高光锐度（拉丝聚拢/发散） | exponent1（主层） | 03 |
| 高光强度 | spec1_intensity | 03 |
| 暗部环境色/强度 | ambient_color(Color)、ambient_intensity | 01 |
| 整体明暗 | exposure_ev | 04 |

多数场景只需要这一张表。下面是全量参考。

---

## 01_光照方向（6 项）

光源方向在图内由角度实时合成（与烘焙端 `light_dir=(0.4,−0.6,0.7)` 同一语义）。

| 参数 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| p_light_azimuth_deg | 滑块 | −56.3099° | [−180, 180] | 方位角：绕 Z 轴（平面内）旋转光源。**改它=高光条纹绕法线转动** |
| p_light_elevation_deg | 滑块 | 44.1489° | [−89, 89] | 仰角：光源抬升/压低。越高 N·L 直射分量越强 |
| p_light_intensity | 滑块 | 1.0 | [0, 4] | 直射光倍率 |
| p_light_color | **Color** | 白 (1,1,1) | — | 直射光颜色（乘进高光+漫反射直射项） |
| p_ambient_color | **Color** | (0.06, 0.07, 0.09) | — | 环境光颜色。默认刻意偏暗偏蓝，接近烘焙基准 |
| p_ambient_intensity | 滑块 | 1.0 | [0, 4] | 环境光倍率 |

> ⚠️ azimuth 与 elevation 合成向量若退化（极端组合），输出无定义——保持在滑块范围内即不会触发。

## 02_各向异性（3 项）

控制高光条纹的方向与各向异性程度。丝缕方向 = 主轴再旋转 angle。

| 参数 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| p_aniso_axis | int | 0 (u) | 0/1 | 主轴：0=沿 u（水平丝），1=沿 v（垂直丝） |
| p_aniso_angle_deg | 滑块 | 0° | [−180, 180] | 在主轴基础上整体旋转条纹方向（度） |
| p_aniso_amount | 滑块 | 1.0 | [0, 1] | 各向异性度：1=纯各向异性（拉丝），0=退化为普通各向同性高光 |

## 03_高光（13 项）

双层 Kajiya-Kay 高光。**层 1 为主视觉层**（默认窄而亮），层 2 为辅助层（默认宽而弱，做衬光）。两层完全独立。

| 参数 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| p_shift1 | 滑块 | 0.0 | [−4, 4] | 层 1 切线偏移：沿法线方向平移高光瓣。正值≈上移光线，负值≈下移 |
| p_exponent1 | 滑块 | 48 | [1, 256] | 层 1 锐度：越大条纹越窄越聚拢（丝质感强）；越小越柔散 |
| p_spec1_color | **Color** | 白 | — | 层 1 颜色 |
| p_spec1_intensity | 滑块 | 1.0 | [0, 4] | 层 1 强度 |
| p_shift2 | 滑块 | 0.35 | [−4, 4] | 层 2 切线偏移（默认与层 1 错开，形成双条纹） |
| p_exponent2 | 滑块 | 8 | [1, 256] | 层 2 锐度（默认宽柔） |
| p_spec2_color | **Color** | 白 | — | 层 2 颜色（可做彩色衬光） |
| p_spec2_intensity | 滑块 | 0.6 | [0, 4] | 层 2 强度 |
| p_spec_mode | int | 1 | 0/1/2 | 分段形状：0=continuous 原始连续 / 1=smooth 平滑台阶 / 2=hard 硬边卡通 |
| p_spec_edge0 / p_spec_edge1 | 滑块 | 0.35 / 0.55 | [0,1] | smooth 模式的下/上过渡边。**必须 edge0 < edge1**，否则形状静默变形（无 SD 侧校验） |
| p_spec_threshold | 滑块 | 0.5 | [0,1] | hard 模式的硬边阈值 |
| p_front_k | 滑块 | 1.0 | [0.01, 4] | 背面高光抑制：N·L 前置系数。>1 收紧正面区域，<1 放宽（背面漏光） |

> 💡 卡通三段形状由 `spec_mode` + `edge0/edge1/threshold` 共同决定；想要连续写实高光就停在 mode 0。

## 04_漫反射_曝光（10 项）

| 参数 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| p_diffuse_mode | int | 1 | 0/1/2 | 漫反射分段：0=half-lambert 连续 / 1=smooth / 2=hard 卡通 |
| p_diffuse_color | **Color** | 白 | — | 漫反射颜色（乘在分段后的 N·L 上；染非白即整体偏色） |
| p_diffuse_edge0 / p_diffuse_edge1 | 滑块 | 0.30 / 0.50 | [0,1] | smooth 模式过渡边。**必须 edge0 < edge1** |
| p_diffuse_threshold | 滑块 | 0.5 | [0,1] | hard 模式阈值 |
| p_ao_strength | 滑块 | 1.0 | [0, 1] | AO 压制强度：1=按 mask1 的 AO 全量压环境光，0=不压 |
| p_ao_direct_light | 滑块 | 0.0 | [0, 1] | AO 是否也压直射光：0=只压环境（默认），1=直射同压 |
| p_exposure_ev | 滑块 | 0.0 | [−10, 10] | 输出级曝光（EV）：每 +1 亮度×2，在 tone map 之前生效 |
| p_validity_fill | 滑块 | 1.0 | [0, 1] | 无效区（coverage 外）填充色灰度：1=白，0=黑 |

## 05_观察模式（3 项）

视向量 Vn 的来源。默认 normal_proxy 即烘焙端基准语义，**没有特殊需求不要动**。

| 参数 | 类型 | 默认 | 范围 | 说明 |
|---|---|---|---|---|
| p_view_mode | int | 2 | 0/1/2 | 0=directional 固定方向 / 1=perspective 逐像素指向相机 / 2=normal_proxy 用法线代视向（烘焙基准） |
| p_view_direction | float3 | (0,0,1) | — | mode 0 的视向（图内自动归一化，零向量退化无定义） |
| p_camera_position | float3 | (0,0,1) | — | mode 1 的相机位置（世界系，与位置图同空间） |

---

## 输入与输出（非参数，但常被问）

| 项 | 说明 |
|---|---|
| 输出 | 2048² RGBA **sRGB** 成品 lightmap（A≡1，无效区=validity_fill 灰） |
| 4 张输入 | 烘焙端固定提供：bake_position / bake_normalobj / mask1 / bake_ao（已内嵌，随 .sbs 走） |
| 依赖尺寸 | texel 间距在生成时由 bake_position.png 实际分辨率派生（2048²→1/2048）。**换非 2048² 资产必须重跑生成脚本**，不要手工改图 |

## 调参注意事项

1. **跨字段合法性 SD 侧不校验**：edge0≥edge1、零视向等非法组合会静默变形/退化。拿不准时对照本文档范围；本地校验器 `sd/aniso_pp/params.py` 的 `validate()` 可离线检查
2. **改参数即时生效**，但 PP 是逐像素重算：2048² 下拖动流畅，一次大幅改动多参数会明显卡一下属正常
3. **颜色参数的 Color(RGB) 编辑器**取色即所见即所得（线性域直接进光照式，无 sRGB 转换——与 GLSL 烘焙端一致）
4. 想恢复烘焙基准：面板右上角实例参数菜单 → **Reset parameters**（全部回到上表默认值）
5. **换资产**（不同贴图/尺寸）：重跑 `sd/stage3_pp2.py`（改 `BAKE_ROOT`），不要在旧实例上换图——图像输入无法经 Python API 注入

## 参数为什么是 34 个（v4 裁定记录）

原 41 个。移除的 7 个均与日常调参无关（详见 `PHASE2_COMPLETION.md` §v4）：
- `debug_mode`、`spec_layer_index` —— 迁移验收用的中间量视图（DEBUG 0–9），证据已固化，成品路径无数值影响
- `detail_mode/strength/green_sign` —— detail 法线功能未解锁，节点图根本不读取
- `texel_u/v` —— 系统参数（由输入图尺寸派生），不应手工调节
