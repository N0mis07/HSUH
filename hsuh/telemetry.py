"""Bounded, cached VPS observations. Never inspect process arguments or environments."""
from collections import deque
import os
from pathlib import Path
import platform
import threading
import time

import psutil


def pressure(resource):
    try:
        result = {}
        for line in (Path('/proc/pressure') / resource).read_text().splitlines():
            kind, *values = line.split()
            result[kind] = {k: float(v) for k, v in (value.split('=') for value in values) if k.startswith('avg')}
        return result
    except (OSError, ValueError):
        return None


class TelemetryReader:
    def __init__(self):
        self.lock = threading.Lock()
        self.cached = None
        self.updated = 0
        self.previous = None
        self.process_cpu = {}
        self.history = deque(maxlen=120)

    def read(self):
        with self.lock:
            now = time.monotonic()
            if self.cached is not None and now - self.updated < 3:
                return self.cached
            m, s = psutil.virtual_memory(), psutil.swap_memory()
            processes, unreadable, threads = [], 0, 0
            previous_cpu, self.process_cpu = self.process_cpu, {}
            for process in psutil.process_iter(['pid', 'name', 'memory_info', 'status', 'num_threads', 'cpu_times', 'create_time']):
                try:
                    info = process.info
                    if not info['memory_info'] or not info['cpu_times']:
                        unreadable += 1
                        continue
                    key = (info['pid'], info['create_time'])
                    used_cpu = info['cpu_times'].user + info['cpu_times'].system
                    self.process_cpu[key] = (now, used_cpu)
                    before = previous_cpu.get(key)
                    cpu = max(0, (used_cpu - before[1]) / (now - before[0]) * 100) if before and now > before[0] else None
                    threads += info['num_threads'] or 0
                    processes.append({'pid': info['pid'], 'name': (info['name'] or 'unknown')[:80],
                                      'rss': info['memory_info'].rss, 'status': info['status'],
                                      'threads': info['num_threads'], 'cpu_percent': round(cpu, 1) if cpu is not None else None})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    unreadable += 1
            processes.sort(key=lambda p: p['rss'], reverse=True)
            disk = psutil.disk_usage(str(Path.home().anchor))
            net, io = psutil.net_io_counters(), psutil.disk_io_counters()
            counters = {'net_rx': net.bytes_recv, 'net_tx': net.bytes_sent,
                        'disk_read': io.read_bytes if io else None, 'disk_write': io.write_bytes if io else None}
            rates = {key: None for key in counters}
            if self.previous and now > self.previous[0]:
                interval = now - self.previous[0]
                for key, value in counters.items():
                    old = self.previous[1][key]
                    if value is not None and old is not None and value >= old:
                        rates[key] = (value - old) / interval
            self.previous = (now, counters)
            cpu = psutil.cpu_percent(interval=0.1)
            try:
                load = list(os.getloadavg())
            except (AttributeError, OSError):
                load = None
            sampled = time.time()
            self.history.append({'at': sampled, 'cpu': cpu, 'memory': round((m.total-m.available) / m.total * 100, 2),
                                 'rx': rates['net_rx'], 'tx': rates['net_tx']})
            self.cached = {
                'sampled_at': sampled, 'hostname': platform.node(), 'scope': 'VPS host /proc view',
                'uptime_seconds': max(0, sampled - psutil.boot_time()),
                'cpu': {'percent': cpu, 'logical': psutil.cpu_count(), 'physical': psutil.cpu_count(logical=False), 'load': load},
                'memory': {'total': m.total, 'available': m.available, 'used': m.total-m.available,
                           'free': m.free, 'cached': getattr(m, 'cached', 0), 'buffers': getattr(m, 'buffers', 0), 'unit': 'bytes'},
                'swap': {'total': s.total, 'used': s.used},
                'disk': {'total': disk.total, 'used': disk.used, 'free': disk.free},
                'rates': rates, 'network': {'received': net.bytes_recv, 'sent': net.bytes_sent},
                'pressure': {key: pressure(key) for key in ('cpu', 'memory', 'io')},
                'processes': processes[:100], 'process_count': len(processes), 'threads': threads,
                'unreadable_processes': unreadable, 'history': list(self.history),
                'note': 'Used RAM = total minus available. RSS contains shared pages and is not additive. Process CPU uses one core as 100%; first samples have no rate. Network includes virtual interfaces; it is not billed egress.',
            }
            self.updated = now
            return self.cached


_reader = TelemetryReader()


def snapshot():
    return _reader.read()
