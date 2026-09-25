#version 330
// output.frag — 曝光、输出曲线与一次 sRGB 编码（PLAN §6.2）。
// 契约：
// - 计算与有效域延拓在线性阶段；量化发生在输出编码之后（PLAN §6.2）。
// - sRGB 用标准分段传递函数；同一展开与阈值（与 common.glsl 一致）。
// - 基准链路显式一次 sRGB 编码，禁止再叠加硬件 sRGB 或库自动 gamma。
// - C4：无 if/条件运算符；step+mix 展开，分支两侧数值合法。

#include <common.glsl>

uniform sampler2D u_linear;   // 核心 pass 线性结果（RGB）+ 有效标记（A）
uniform float u_exposureEV;   // 艺术参数（PLAN §6.2：编码规则不是艺术参数）
uniform float u_validityFill; // 无效域填充：1.0=白底（PLAN §6.2 背景可填纯白）

in vec2 v_clipUV;
out vec4 fragColor;

void main() {
    // 读回链路统一「首行为顶部」：数据图上传与 FBO 读回的行序由 gl/context.py
    // 统一处理；此处采样方向与核心 pass 的输出纹理一致（q.y = v）。
    vec2 q = vec2(v_clipUV.x, 1.0 - v_clipUV.y);
    vec4 linear = texture(u_linear, q);

    // PLAN §6.2：C_exposed = max(C,0) * 2^EV
    vec3 c = max(linear.rgb, vec3(0.0)) * pow(2.0, u_exposureEV);
    // Reinhard：C_ldr = C_exposed / (1 + C_exposed)
    vec3 ldr = c / (1.0 + c);
    // 一次 sRGB 编码（标准分段函数）
    vec3 srgb = vec3(
        linearToSRGB(ldr.r),
        linearToSRGB(ldr.g),
        linearToSRGB(ldr.b)
    );

    // 无效域：独立标记（core pass A），不把「高光=0 的坏 texel」当正确种子
    // （PLAN §6.1）；最终导出前由 Python 做有效域延拓与 padding。
    float valid = step(0.5, linear.a);
    vec3 outRGB = mix(vec3(u_validityFill), srgb, valid);
    fragColor = vec4(outRGB, 1.0);
}
