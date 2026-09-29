# -*- coding: utf-8 -*-
"""aniso_mask_tools — aniso_mask 节点生成工具（ANISO_MASK_PLAN 执行件）。

- schema.py  — 5 参数、固定常量、合法域、版本
- kernel.py  — §3 数学：正交反射基底、两轴宽度、椭圆主瓣（图内发射）
- builder.py — resolver、frame 收集、新包/输出/保存

红线：不覆盖旧 aniso_lightmap.sbs / .resources / stage3_pp2.py / aniso_pp/**；
stages.py 仅允许 build_core 的 frame_out 兼容出口。
"""
