# -*- coding: utf-8 -*-
r"""Stage 0 / 0B 第二轮 — 真实贴图 idx 映射 + API 读回自动验证。

前置：用户已把 bake_position/bake_normalobj/mask1/bake_ao 四个 Bitmap
拖进 test graph（graph_scan.json 留痕）。

验证内容：
  1. 4 张 Bitmap 按固定语义顺序接入 PP（position→0, normalobj→1, mask→2, ao→3）
  2. 函数图打包采样：(s0.r, s1.g, s2.b, s3.r)
  3. graph.compute() + SDTexture.save(path, '') —— API 自动落盘（无色彩变换）
  4. 外部 check_export 依据各图真实内容判定 idx→pin→语义映射

坐标适配（$pos→q、q→采样地址）仍待梯度图；本轮聚焦 idx 映射与读回链路。

输出：sd/validation/probe_0b2_report.json + probe_0b2_readback.png
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

for _k in [k for k in sys.modules if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
    del sys.modules[_k]

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'probe_0b2_report.json')
READBACK_PATH = os.path.join(VAL_DIR, 'probe_0b2_readback.png')

report = {'probe': '0B2', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'0B2 探针失败于: {name}  ({detail})')


def main():
    from aniso_pp import api as SDAPI
    from aniso_pp.emitter import Emitter, NodeRef
    from aniso_pp.readback import compute_and_save
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    graph = SDAPI.get_current_graph()
    step('当前 graph', 'CompGraph' in type(graph).__name__,
         {'class': type(graph).__name__, 'id': SDAPI.get_graph_title(graph)})

    # ---- 找用户的 4 张 Bitmap（按资源 url 语义命名匹配，不按位置/视觉）
    wanted = {
        'bake_position': None,
        'bake_normalobj': None,
        'mask1': None,
        'bake_ao': None,
    }
    nodes = graph.getNodes()
    n = nodes.getSize()
    for i in range(n):
        node = nodes.getItem(i)
        try:
            if node.getDefinition().getId() != 'sbs::compositing::bitmap':
                continue
            url = node.getReferencedResource().getUrl()
        except BaseException:
            continue
        for key in wanted:
            if f'/{key}' in url and wanted[key] is None:
                wanted[key] = node
    missing = [k for k, v in wanted.items() if v is None]
    step('4 张语义贴图定位', not missing,
         {k: (v is not None) for k, v in wanted.items()} if not missing
         else {'missing': missing})

    # ---- 新建 4×4 PP（本轮专用；不清理用户已有节点）
    # idx 映射裁定（probe_0b_idx_verdict.json）：sample(i) 跳过第 1 连接，
    # 且 idx=2 恒返回 0（版本缺陷，三重复现）→ 采用 5 槽占位方案：
    # 接线 [dummy, position, normalobj, mask, ao]，采样 idx 0/1/3/4。
    with SDAPI.undo_group('aniso_pp 0B2: build'):
        pp, ev = SDAPI.create_pp(graph, colorswitch=True, size_log2=11)
        pp.setPosition(float2(600.0, 0.0))
        # dummy 占位（idx2 不可用）
        from sd.api.sdbasetypes import ColorRGBA
        from sd.api.sdvaluecolorrgba import SDValueColorRGBA
        dummy = graph.newNode('sbs::compositing::uniform')
        dprop = dummy.getPropertyFromId('outputcolor', SDPropertyCategory.Input)
        dummy.setPropertyValue(dprop, SDValueColorRGBA.sNew(ColorRGBA(0, 0, 0, 1)))
        dummy.setPosition(float2(300.0, -200.0))
        order = ['DUMMY', 'bake_position', 'bake_normalobj', 'mask1', 'bake_ao']
        used = []
        for name in order:
            src = dummy if name == 'DUMMY' else wanted[name]
            used.append(SDAPI.connect_pp_input(src, pp))
        pins = SDAPI.enumerate_input_pins(pp)
    step('PP 4×4 + 5 槽接线（idx2=占位）', True,
         {'used_pins_raw': used, 'pins_after': pins, 'order': order})

    # ---- 函数图：打包 (pos.r, nrm.r, mask.r, ao.r) ← sample idx 0/1/3/4
    fg, created = SDAPI.get_perpixel_graph(pp)
    pos = SDAPI.get_pos_node(fg)
    em = Emitter(fg, cache_scope='probe_0b2')
    s_pos = SDAPI.samplecol_node(fg, pos, 0)   # → 第 2 连接 = bake_position
    s_nrm = SDAPI.samplecol_node(fg, pos, 1)   # → 第 3 连接 = bake_normalobj
    s_msk = SDAPI.samplecol_node(fg, pos, 3)   # → 第 5 连接 = mask1
    s_ao = SDAPI.samplecol_node(fg, pos, 4)    # → 第 6 连接 = bake_ao
    r0 = em.sw1(NodeRef(s_pos, 'f4'), 0)
    r1 = em.sw1(NodeRef(s_nrm, 'f4'), 0)
    r2 = em.sw1(NodeRef(s_msk, 'f4'), 0)
    r3 = em.sw1(NodeRef(s_ao, 'f4'), 0)
    packed = em.v4_from_f3(em.v3(r0, r1, r2), r3)
    SDAPI.fg_set_output(fg, packed.node)
    step('函数图打包输出 (pos.r, nrm.r, mask.r, ao.r) @idx 0/1/3/4', True,
         {'created': created,
          'interpretation': 'R=position.r G=normal.r B=mask.r A=ao.r；'
                            '对照源统计判定'})

    # ---- compute + API 读回（无色彩变换）
    # SD 求值以 output 节点为根（官方示例图中带 output 节点后 compute 才有值）。
    # 建 compositing::output 接 PP 输出，compute 后读 PP 的输出属性值。
    out_node = graph.newNode('sbs::compositing::output')
    out_node.setPosition(float2(900.0, 0.0))
    pp.newPropertyConnectionFromId('unique_filter_output', out_node, 'inputNodeOutput')
    rb = compute_and_save(graph, pp, READBACK_PATH)
    step('compute + SDTexture.save 读回（经 output 节点驱动）', rb['ok'],
         {'path': READBACK_PATH, 'size': rb['size'],
          'error': (rb['error'] or '')[:300]})
    # 保存为 EXR 便于数值比较（第二次调用按扩展名写 EXR）
    READBACK_EXR = os.path.join(VAL_DIR, 'probe_0b2_readback.exr')
    rb2 = compute_and_save(graph, pp, READBACK_EXR)
    step('EXR float 读回', rb2['ok'],
         {'path': READBACK_EXR, 'size': rb2['size'],
          'error': (rb2['error'] or '')[:300]})

    report['readback'] = {'path': READBACK_PATH, 'size': rb['size']}
    report['manual_checks'] = []
    report['ok'] = True


# ---------------------------------------------------------------- 运行
try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT] ' + repr(e))
    print(traceback.format_exc())

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f'[DONE] 报告已写入 {REPORT_PATH}')
