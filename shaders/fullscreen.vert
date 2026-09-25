#version 330
// 全屏三角形：无顶点缓冲，gl_VertexID 展开三顶点。
// 输出 v_uv 使用 q 语义（左上原点、y 向下，PLAN §3.4）——
// 但纹理按「首行为顶部」上传，GL 纹理 v=0 在底部，因此采样时
// 由 aniso.frag 统一处理；顶点这里输出标准 clip 空间 uv。

out vec2 v_clipUV; // clip 空间 uv：(0,0) 左下角

void main() {
    // 三顶点覆盖整个屏幕：(-1,-1), (3,-1), (-1,3)
    vec2 pos = vec2(
        float((gl_VertexID & 1) << 2) - 1.0,
        float((gl_VertexID & 2) << 1) - 1.0
    );
    v_clipUV = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
