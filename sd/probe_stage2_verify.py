# -*- coding: utf-8 -*-
r"""Stage 2 持久化验证：unload aniso_lightmap 包 → 重新 load → 枚举参数与节点 →
在 test graph 实例化该 wrapper → compute。
输出：sd/validation/stage2_verify_report.json
"""
import json
import os
import sys
import traceback

SD_DIR = os.path.dirname(os.path.abspath(__file__))
if SD_DIR not in sys.path:
    sys.path.insert(0, SD_DIR)

VAL_DIR = os.path.join(SD_DIR, 'validation')
REPORT_PATH = os.path.join(VAL_DIR, 'stage2_verify_report.json')
SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')

report = {'probe': 'stage2_verify', 'steps': [], 'fail': None}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    report['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'stage2_verify 失败于: {name}  ({detail})')


def main():
    import sd
    from sd.api.sdproperty import SDPropertyCategory
    from sd.api.sdbasetypes import float2
    from aniso_pp import api as SDAPI
    from aniso_pp.readback import compute_and_save

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    # ---- 全量清扫：unload 一切含 aniso_lightmap 的驻留包（v4 实测：
    # 重复 load 堆积同名包 + test graph 里本工具旧实例钉住旧包导致 unload 失败）
    def _count_params(p_):
        g_ = p_.findResourceFromUrl('pkg:///aniso_lightmap')
        if g_ is None:
            return None, -1
        ps_ = g_.getProperties(SDPropertyCategory.Input)
        return g_, sum(1 for i_ in range(ps_.getSize())
                       if str(ps_.getItem(i_).getId()).startswith('p_'))

    # 先删 test graph 里本工具创建的 aniso 实例（按引用资源判定，不碰用户节点）
    test = SDAPI.get_current_graph()
    step('test graph', 'CompGraph' in type(test).__name__)
    deleted_inst = 0
    nodes_all = test.getNodes()
    to_delete = []
    for i_ in range(nodes_all.getSize()):
        nd_ = nodes_all.getItem(i_)
        try:
            rr = nd_.getReferencedResource()
            if rr is not None and 'aniso_lightmap' in str(rr.getUrl()):
                to_delete.append(nd_)
        except BaseException:
            continue
    for nd_ in to_delete:
        try:
            test.deleteNode(nd_)
            deleted_inst += 1
        except BaseException:
            pass
    step('清理本工具旧实例', True, {'deleted': deleted_inst})

    swept = 0
    remaining = -1
    unload_fails = []
    for _round in range(8):
        pkgs_all = pkg_mgr.getPackages()
        victims = []
        for i_ in range(pkgs_all.getSize()):
            p_ = pkgs_all.getItem(i_)
            try:
                if p_.findResourceFromUrl('pkg:///aniso_lightmap') is not None:
                    victims.append(p_)
            except BaseException:
                continue
        remaining = len(victims)
        if not victims:
            break
        for v_ in victims:
            try:
                pkg_mgr.unloadUserPackage(v_)
                swept += 1
            except BaseException as e:
                unload_fails.append(repr(e)[:120])
    # remaining 可容忍（Library/Explorer 面板驻留的包 unload 被拒，API 无移除
    # 入口；pkgpin 探针实测打开图无引用）。但必须验证 pkg:/// 解析到的包内容
    # 与磁盘一致——若驻留旧版（参数数 ≠ 磁盘），下方"参数持久化"断言会失败，
    # 此时需用户手动关闭该包（Explorer 右键 → close）后重跑本探针。
    step('驻留包清扫', True,
         {'swept': swept, 'remaining': remaining, 'fails': unload_fails[:3]})

    # ---- reload 并断言：**loadUserPackage 返回的包对象**（非 pkg:/// URL——
    # pkgdeep 探针实测驻留旧包时 URL 解析到陈旧版本且 unload 静默无效）
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    step('重新加载 .sbs', pkg is not None)
    graph, n_params = _count_params(pkg)
    from aniso_pp.params import PARAMS as _P
    step('参数持久化(返回包对象)', n_params == len(_P),
         {'count': n_params, 'expected': len(_P)})

    nodes = graph.getNodes()
    kinds = {}
    for i in range(nodes.getSize()):
        d = str(nodes.getItem(i).getDefinition().getId())
        kinds[d] = kinds.get(d, 0) + 1
    step('节点持久化', kinds.get('sbs::compositing::pixelprocessor') == 2
         and kinds.get('sbs::compositing::bitmap') == 4,
         kinds)

    # ---- 颜色注解持久化抽查（API 读 editor 注解）
    color_ok = 0
    for cid in ('p_light_color', 'p_spec1_color', 'p_diffuse_color'):
        pr = graph.getPropertyFromId(cid, SDPropertyCategory.Input)
        if pr is None:
            continue
        try:
            ed = graph.getPropertyAnnotationValueFromId(pr, 'editor')
            if ed is not None and str(ed.get()) == 'color':
                color_ok += 1
        except BaseException:
            pass
    step('颜色编辑器注解(抽查3)', color_ok == 3, {'ok': color_ok})

    # ---- 在 test graph 实例化（接 output 节点防死码消除）
    # InvalidHandle 防御：从刚 load 的 pkg 重新解析资源并断言类名
    res = pkg.findResourceFromUrl('pkg:///aniso_lightmap')
    if res is None:
        raise RuntimeError('loadUserPackage 返回包中找不到 aniso_lightmap 资源')
    try:
        cls = str(res.getClassName())
    except BaseException:
        cls = '<unknown>'
    inst = None
    last_err = None
    for attempt in range(3):
        try:
            inst = test.newInstanceNode(res)
            break
        except BaseException as e:
            last_err = repr(e)
    if inst is None:
        raise RuntimeError(f'newInstanceNode 3 次失败(最后: {last_err}; res 类: {cls})')
    inst.setPosition(float2(5000.0, 2000.0))
    step('实例化到 test graph', inst is not None, {'res_class': cls})

    out_node = test.newNode('sbs::compositing::output')
    out_node.setPosition(float2(5600.0, 2000.0))
    outs = inst.getProperties(SDPropertyCategory.Output)
    out_pin = str(outs.getItem(0).getId())
    inst.newPropertyConnectionFromId(out_pin, out_node, 'inputNodeOutput')

    # ---- compute（含 wrapper 内 4 bitmap 相对路径解析）
    exr = os.path.join(VAL_DIR, 'stage2_inst.exr')
    rb = compute_and_save(test, inst, exr)
    step('实例 compute+save', rb['ok'],
         {'size': rb['size'], 'err': (rb['error'] or '')[:200]})

    report['swept'] = swept
    report['deleted_inst'] = deleted_inst
    report['ok'] = True


try:
    main()
except BaseException as e:
    report['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print('[DONE]', REPORT_PATH)
