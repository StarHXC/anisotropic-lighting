# -*- coding: utf-8 -*-
r"""节点排布：对 aniso_lightmap 两个 PP 的 perpixel 函数图执行 auto_layout
（skill node-alignment.md 的拓扑分层排布），保存后回读验证。
输出：sd/validation/layout_report.json
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

SBS_OUT = os.path.join(SD_DIR, 'aniso_lightmap.sbs')
REPORT = {'probe': 'layout', 'steps': [], 'ok': False}


def step(name, ok, detail=None):
    entry = {'step': name, 'ok': bool(ok)}
    if detail is not None:
        entry['detail'] = detail
    REPORT['steps'].append(entry)
    print(('[PASS] ' if ok else '[FAIL] ') + name + (f'  {detail}' if detail else ''))
    if not ok:
        raise RuntimeError(f'layout 失败于: {name}  ({detail})')


from sd.api.sdproperty import SDPropertyCategory
from sd.api.sdbasetypes import float2


def auto_layout(fg, max_rows=4, sx=220, sy=140):
    """skill node-alignment.md 的拓扑分层排布（原样复制，仅扩了 orphan 容错）。"""
    nodes_arr = fg.getNodes()
    all_nodes = [nodes_arr.getItem(i) for i in range(nodes_arr.getSize())]
    if not all_nodes:
        return 0

    uid_map = {id(n): n for n in all_nodes}
    in_conns = {id(n): set() for n in all_nodes}
    out_adj = {id(n): [] for n in all_nodes}

    for n in all_nodes:
        props = n.getProperties(SDPropertyCategory.Input)
        for j in range(props.getSize()):
            p = props.getItem(j)
            try:
                conns = n.getPropertyConnections(p)
                if conns:
                    for k in range(conns.getSize()):
                        c = conns.getItem(k)
                        src = c.getInputPropertyNode()
                        if id(src) in in_conns:
                            in_conns[id(n)].add(id(src))
                            out_adj[id(src)].append(id(n))
            except BaseException:
                pass

    in_deg = {nid: len(s) for nid, s in in_conns.items()}
    queue = [nid for nid, d in in_deg.items() if d == 0]
    ordered = []
    while queue:
        cur = queue.pop(0)
        ordered.append(cur)
        for nxt in out_adj[cur]:
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                queue.append(nxt)
    ordered.extend([nid for nid in in_conns if nid not in ordered])

    depth = {nid: 0 for nid in ordered}
    for nid in ordered:
        for nxt in out_adj[nid]:
            if depth[nxt] < depth[nid] + 1:
                depth[nxt] = depth[nid] + 1

    layers = {}
    for nid in ordered:
        layers.setdefault(depth[nid], []).append(nid)

    x_offset = 0
    for d in sorted(layers.keys()):
        nids = layers[d]
        layer_cols = (len(nids) + max_rows - 1) // max_rows
        for idx, nid in enumerate(nids):
            col = idx // max_rows
            row = idx % max_rows
            uid_map[nid].setPosition(float2(float((x_offset + col) * sx),
                                            float(row * sy)))
        x_offset += layer_cols
    return len(all_nodes)


def main():
    import sd
    from aniso_pp import api as SDAPI

    step('环境', True, {'sd_api_version': SDAPI.app_version()})
    pkg_mgr = sd.getContext().getSDApplication().getPackageMgr()

    # ---- 全量清扫 + 重载（v4 实测的同名包驻留问题）
    swept = 0
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
        if not victims:
            break
        for v_ in victims:
            try:
                pkg_mgr.unloadUserPackage(v_)
                swept += 1
            except BaseException:
                pass
    pkg = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    graph = pkg.findResourceFromUrl('pkg:///aniso_lightmap')
    step('清扫+重载', graph is not None, {'swept': swept})

    # ---- 找两个 PP，对各自 perpixel 函数图排布
    nodes = graph.getNodes()
    pps = []
    for i in range(nodes.getSize()):
        nd = nodes.getItem(i)
        if str(nd.getDefinition().getId()) == 'sbs::compositing::pixelprocessor':
            pps.append(nd)
    step('PP 定位', len(pps) == 2, {'count': len(pps)})

    for idx, pp in enumerate(sorted(pps, key=lambda n: n.getPosition().x)):
        fg = pp.getPropertyGraph(
            pp.getPropertyFromId('perpixel', SDPropertyCategory.Input))
        n_laid = auto_layout(fg)
        step(f'PP{idx + 1} 排布', n_laid > 0, {'nodes': n_laid})

    # ---- 保存（savePackage 原路径）
    pkg_mgr.savePackage(pkg)
    step('保存', os.path.getsize(SBS_OUT) > 0, {'size': os.path.getsize(SBS_OUT)})

    # ---- 回读验证：卸载重载后抽查位置分布
    for v_ in [p_ for p_ in [pkg_mgr.getPackages().getItem(i_)
                              for i_ in range(pkg_mgr.getPackages().getSize())]
               if _has_aniso(p_)]:
        try:
            pkg_mgr.unloadUserPackage(v_)
        except BaseException:
            pass
    pkg2 = pkg_mgr.loadUserPackage(SBS_OUT, True, True)
    graph2 = pkg2.findResourceFromUrl('pkg:///aniso_lightmap')
    nodes2 = graph2.getNodes()
    pps2 = sorted([nodes2.getItem(i) for i in range(nodes2.getSize())
                   if str(nodes2.getItem(i).getDefinition().getId())
                   == 'sbs::compositing::pixelprocessor'],
                  key=lambda n: n.getPosition().x)
    stats = []
    ok_all = True
    for idx, pp in enumerate(pps2):
        fg = pp.getPropertyGraph(
            pp.getPropertyFromId('perpixel', SDPropertyCategory.Input))
        arr = fg.getNodes()
        xs, ys, at_origin = set(), set(), 0
        n = arr.getSize()
        for i in range(n):
            p_ = arr.getItem(i).getPosition()
            xs.add(round(p_.x, 1))
            ys.add(round(p_.y, 1))
            if abs(p_.x) < 0.01 and abs(p_.y) < 0.01:
                at_origin += 1
        spread_x = max(xs) - min(xs) if xs else 0
        # 判据：深度列数可观（拓扑分层成功）+ 横向铺开 + 原点堆积≤1
        good = len(xs) >= 10 and spread_x > 1000 and at_origin <= 1
        ok_all = ok_all and good
        stats.append({'pp': idx + 1, 'nodes': n, 'distinct_x': len(xs),
                      'distinct_y': len(ys), 'spread_x': spread_x,
                      'at_origin': at_origin})
    step('位置回读分布', ok_all, stats)

    REPORT['ok'] = True


def _has_aniso(p_):
    try:
        return p_.findResourceFromUrl('pkg:///aniso_lightmap') is not None
    except BaseException:
        return False


try:
    main()
except BaseException as e:
    REPORT['fail'] = {'error': repr(e), 'traceback': traceback.format_exc()}
    print('[ABORT]', repr(e))
    print(traceback.format_exc())

with open(os.path.join(SD_DIR, 'validation', 'layout_report.json'), 'w',
          encoding='utf-8') as f:
    json.dump(REPORT, f, ensure_ascii=False, indent=2)
print('[DONE]')
