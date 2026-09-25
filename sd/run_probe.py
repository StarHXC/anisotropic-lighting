# -*- coding: utf-8 -*-
"""探针任务派发 + 结果读取（外部本地 Python，Claude 调用）。

用法：
    python "sd/run_probe.py" 0a          # 派发任务并等待结果（最多 300s）

前提：bridge_plugin 已装进 SD（initializeSDPlugin 轮询任务文件）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

SD_DIR = Path(__file__).resolve().parent
VAL = SD_DIR / 'validation'
TASK = VAL / '_bridge_task.json'
RESULT = VAL / '_bridge_result.json'


def main() -> int:
    probe = sys.argv[1] if len(sys.argv) > 1 else '0a'
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0

    VAL.mkdir(parents=True, exist_ok=True)
    # 清理旧结果
    if RESULT.exists():
        RESULT.unlink()
    TASK.write_text(json.dumps({'probe': probe}, ensure_ascii=False),
                    encoding='utf-8')
    print(f'[DISPATCH] probe {probe} → {TASK}')

    t0 = time.time()
    while time.time() - t0 < timeout:
        if RESULT.exists():
            res = json.loads(RESULT.read_text(encoding='utf-8'))
            ok = res.get('ok')
            print(f"[RESULT] probe {res.get('probe')} ok={ok}")
            if not ok and res.get('error'):
                print('--- error tail ---')
                print('\n'.join(res['error'].splitlines()[-25:]))
            return 0 if ok else 1
        time.sleep(1.0)
    print('[TIMEOUT] 等待超时——检查 SD 桥插件是否在运行'
          '（Explorer 里应能看到 aniso_pp_bridge 载入日志）')
    return 2


if __name__ == '__main__':
    sys.exit(main())
