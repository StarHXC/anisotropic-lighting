# aniso_pp — SD Pixel Processor 迁移（Stage 0 探针阶段）
#
# 依据 doc/SD_MIGRATION_PLAN.md（2026-09-25 静态审核修订版）。
# 仅放行 Stage 0（0A–0E）；本包当前只包含探针所需的最小模块：
#   api.py     — SD API 薄封装（全部设置读回断言，禁止吞异常）
#   emitter.py — 函数图发射器（NodeRef 类型标签 + §5.3 类型断言 + §6 配方）
#   params.py  — 参数 schema（0D 起接入）
#
# 红线（计划 §红线）：
#   - 只创建带 owner/版本标识的新副本；不按模糊名称清理用户图
#   - 不修改 D:\SD_Project\Plugins\ 与 GLSL 侧现有文件
#   - 设置必须读回断言；失败显式抛错并留痕，不吞异常继续

__version__ = '0.0.0+stage0'
