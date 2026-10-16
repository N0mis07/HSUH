"""Live VPS observations, never estimates of a Windows client's resources."""
import platform
import time

import psutil


def snapshot():
    m = psutil.virtual_memory()
    s = psutil.swap_memory()
    processes = []
    unreadable = 0
    for p in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            info = p.info
            if not info['memory_info']:
                unreadable += 1
                continue
            processes.append({'pid': info['pid'], 'name': (info['name'] or 'unknown')[:80], 'rss': info['memory_info'].rss})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            unreadable += 1
    processes.sort(key=lambda p: p['rss'], reverse=True)
    return {
        'sampled_at': time.time(), 'hostname': platform.node(), 'scope': 'VPS host /proc view',
        'memory': {'total': m.total, 'available': m.available, 'used': m.total-m.available,
                   'cached': getattr(m, 'cached', 0), 'buffers': getattr(m, 'buffers', 0), 'unit': 'bytes'},
        'swap': {'total': s.total, 'used': s.used}, 'processes': processes[:12],
        'unreadable_processes': unreadable,
        'note': 'Used = total − available. Process RSS includes shared pages: do not sum it. Host view, not per-chat attribution.',
    }
