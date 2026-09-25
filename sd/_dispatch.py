# -*- coding: utf-8 -*-
"""临时派发器（绕过 run_probe 的去重）：任务带 nonce。"""
import json
import sys
import time

probe = sys.argv[1]
nonce = sys.argv[2]
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0

task_path = r'E:\AI_Project\Anisotropic Lighting\sd\validation\_bridge_task.json'
result_path = r'E:\AI_Project\Anisotropic Lighting\sd\validation\_bridge_result.json'

import os
if os.path.exists(result_path):
    os.remove(result_path)
with open(task_path, 'w', encoding='utf-8') as f:
    json.dump({'probe': probe, 'nonce': nonce}, f)
print('[DISPATCH]', probe, nonce)

t0 = time.time()
while time.time() - t0 < timeout:
    if os.path.exists(result_path):
        r = json.load(open(result_path, encoding='utf-8'))
        print('[RESULT]', json.dumps({k: r.get(k) for k in ('probe', 'ok')},
                                     ensure_ascii=False))
        if r.get('error'):
            print(r['error'][-1500:])
        sys.exit(0 if r.get('ok') else 1)
    time.sleep(1.0)
print('[TIMEOUT]')
sys.exit(2)
