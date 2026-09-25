# -*- coding: utf-8 -*-
"""aniso_pp 任务桥 —— 装进 SD 后轮询任务文件并执行探针。

安装（一次性）：
    把本文件复制到
    C:\\Users\\<user>\\Documents\\Adobe\\Adobe Substance 3D Designer\\python\\sduserplugins\\aniso_pp_bridge\\__init__.py
    （目录需自建），重启 SD 或在 Plugin Manager 里 Reload。

协议：
    执行者把任务写到  sd/validation/_bridge_task.json：
        {"probe": "0a"}          → exec sd/probe_0a.py
    桥每 1.5s 检查一次；执行完写回 _bridge_result.json：
        {"ok": true/false, "report": <report path>, "error": ...}
    然后删除任务文件。

工作目录：桥用探针自身的 __file__ 逻辑定位 sd/，与 UI 无关。
"""
import json
import os
import sys
import traceback

TASK_FILE = None
RESULT_FILE = None
SD_DIR = None

# SD 注入的模块级单例
from PySide6 import QtCore  # noqa: E402


def _locate_dirs():
    global TASK_FILE, RESULT_FILE, SD_DIR
    # 本文件位于 sduserplugins/aniso_pp_bridge/__init__.py；
    # 探针目录按约定在 <项目>/sd/。从用户文档目录向上找最近修改的
    # "Anisotropic Lighting/sd" 不稳妥——改为绝对路径配置（安装时写死）。
    # 默认安装路径由安装脚本填入。
    cfg = os.path.join(os.path.dirname(__file__), 'bridge_config.json')
    with open(cfg, encoding='utf-8-sig') as f:  # utf-8-sig 容忍 BOM
        cfg_d = json.load(f)
    SD_DIR = cfg_d['sd_dir']
    val = os.path.join(SD_DIR, 'validation')
    os.makedirs(val, exist_ok=True)
    TASK_FILE = os.path.join(val, '_bridge_task.json')
    RESULT_FILE = os.path.join(val, '_bridge_result.json')


class _Poller(QtCore.QObject):
    tick = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._busy = False        # 防重入：一轮未完成不接新任务
        self._done_key = None     # 已完成的任务签名（防同任务重复执行）

    def poll(self):
        if self._busy:
            return
        try:
            if not os.path.exists(TASK_FILE):
                return
            with open(TASK_FILE, encoding='utf-8') as f:
                task = json.load(f)
            probe = task.get('probe', '')
            key = json.dumps(task, sort_keys=True)
            if key == self._done_key:
                # 同一任务已执行过 → 只补写结果并删除任务文件，不再执行
                self._cleanup(key, probe, None, already=True)
                return
            self._busy = True
            try:
                result = {'probe': probe, 'ok': False, 'error': None,
                          'report': os.path.join(SD_DIR, 'validation',
                                                 f'probe_{probe}_report.json')}
                try:
                    path = os.path.join(SD_DIR, f'probe_{probe}.py')
                    # 强制重读 aniso_pp 模块
                    for k in [k for k in sys.modules
                              if k == 'aniso_pp' or k.startswith('aniso_pp.')]:
                        del sys.modules[k]
                    if SD_DIR not in sys.path:
                        sys.path.insert(0, SD_DIR)
                    src = open(path, encoding='utf-8').read()
                    g = {'__name__': '__bridge__', '__file__': path}
                    exec(compile(src, path, 'exec'), g)
                    result['ok'] = bool(g.get('report', {}).get('ok'))
                except BaseException as e:
                    result['error'] = traceback.format_exc()
                self._cleanup(key, probe, result)
            finally:
                self._busy = False
        except BaseException:
            pass  # 桥自身不崩；任务文件损坏时静默等待下轮

    def _cleanup(self, key, probe, result, already=False):
        try:
            with open(RESULT_FILE, 'w', encoding='utf-8') as f:
                if already:
                    json.dump({'probe': probe, 'ok': None,
                               'note': 'duplicate task suppressed'},
                              f, ensure_ascii=False, indent=2)
                elif result is not None:
                    json.dump(result, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
        try:
            os.remove(TASK_FILE)
        except OSError:
            pass
        if not already:
            self._done_key = key


def initializeSDPlugin():
    _locate_dirs()
    p = _Poller()
    t = QtCore.QTimer()
    t.setInterval(1500)
    t.timeout.connect(p.poll)
    t.start()
    # 防 GC
    globals()['_bridge_timer'] = t
    globals()['_bridge_poller'] = p
    print('[aniso_pp_bridge] started, task file:', TASK_FILE)


def uninitializeSDPlugin():
    t = globals().get('_bridge_timer')
    if t is not None:
        t.stop()
