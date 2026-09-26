# -*- coding: utf-8 -*-
"""probes/ 子目录定位验证探针：报告自身路径与执行上下文。"""
import os

report = {
    'ok': True,
    'file': __file__,
    'probe_name': globals().get('__probe_name__', '<missing>'),
    'exists': os.path.exists(__file__),
}
