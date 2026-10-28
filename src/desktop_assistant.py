"""Local assistant state. No keyboard/mouse injection or focus APIs are used."""
from pathlib import Path
from datetime import datetime, timedelta
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
import threading
import time


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


class PhysicalInput:
    """Read activity timestamps and held-state bits; never record typed keys."""
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.UINT), ('dwTime', wintypes.DWORD)]

    def __init__(self):
        self.user = ctypes.windll.user32
        self.kernel = ctypes.windll.kernel32
        self.user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user.GetAsyncKeyState.restype = ctypes.c_short
        self.kernel.GetTickCount.restype = wintypes.DWORD

    def quiet(self):
        info = self.LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not self.user.GetLastInputInfo(ctypes.byref(info)):
            return False
        age = (self.kernel.GetTickCount() - info.dwTime) & 0xffffffff
        if age < 250:
            return False
        return not any(self.user.GetAsyncKeyState(key) & 0x8000 for key in range(1, 255))


class Assistant:
    DEFAULTS = {'enabled': False, 'speed': 5, 'auto_chest': False, 'threshold': 1000,
                'remember_monitor': True}

    def __init__(self, root, physical=None, clock=time.time):
        self.path = Path(root) / 'assistant_state.json'
        self.clock = clock
        self.physical = physical
        self.lock = threading.RLock()
        self.last_save = 0
        self.next_tick = 0
        self.open_settings = False
        self.quit_requested = False
        self.flush_generation = 0
        self.flush_done = 0
        self.runtime = {}
        self.update_required = False
        self.state = {'settings': dict(self.DEFAULTS), 'session': 0, 'confirmed': 0,
                      'local': {'total': 0, 'balance': 0, 'chests': {}, 'opened': 0},
                      'baselines': {}, 'days': {}, 'rooms': [], 'monitor': None,
                      'rewards': [], 'session_chests': 0}
        if self.path.exists():
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            self.state.update(saved)
            self.state['settings'] = {**self.DEFAULTS, **saved.get('settings', {})}
        # Old simulated local balances are archival only. Never import them into
        # the original application's account store or the real daily baseline.
        if self.state.get('schema') != 2:
            self.state['legacy_local'] = self.state.pop('local', {})
            self.state['legacy_local_days'] = self.state['days'].pop('local', {})
            self.state['schema'] = 2
        self.state.pop('local', None)

    def save(self, force=False):
        if force or self.clock() - self.last_save >= 5:
            atomic_json(self.path, self.state)
            self.last_save = self.clock()

    def day(self):
        return datetime.fromtimestamp(self.clock()).date()

    def observe(self, scope, total):
        if not isinstance(total, (int, float)) or not math.isfinite(total) or total < 0:
            raise ValueError('Invalid cumulative count')
        total = int(total)
        key = hashlib.sha256(str(scope).encode()).hexdigest()[:24]
        before = self.state['baselines'].get(key)
        self.state['baselines'][key] = total
        date = str(self.day())
        bucket = 'normal'
        days = self.state['days'].setdefault(bucket, {})
        # Reset/account changes establish a new baseline; never fabricate growth.
        if before is not None and total >= before:
            days[date] = days.get(date, 0) + total - before
        cutoff = str(self.day() - timedelta(days=90))
        for old in list(days):
            if old < cutoff:
                del days[old]
        if len(self.state['baselines']) > 100:
            self.state['baselines'] = {key: total}

    def snapshot(self):
        value = json.loads(json.dumps(self.state))
        value.pop('baselines', None)
        value['weekly'] = {}
        for scope in ('local', 'normal'):
            days = value['days'].get(scope, {})
            value['weekly'][scope] = [{'date': str(self.day() - timedelta(days=i)),
                                      'count': days.get(str(self.day() - timedelta(days=i)), 0)}
                                     for i in range(6, -1, -1)]
        value.pop('days', None)
        value['flush_generation'] = self.flush_generation
        value['flush_done'] = self.flush_done
        value['runtime'] = dict(self.runtime)
        value['update_required'] = self.update_required
        return value

    def handle(self, action, body, offline=False):
        with self.lock:
            if action == 'configure':
                changes = body.get('settings', {})
                if not isinstance(changes, dict) or set(changes) - self.DEFAULTS.keys():
                    raise ValueError('Unknown setting')
                for key, val in changes.items():
                    if key in ('enabled', 'auto_chest', 'remember_monitor') and type(val) is not bool:
                        raise ValueError('Expected boolean')
                    if key == 'speed' and (type(val) is not int or val not in (1, 5, 10)):
                        raise ValueError('Speed must be 1, 5 or 10')
                    if key == 'threshold' and (type(val) is not int or not 1 <= val <= 1000000000):
                        raise ValueError('Invalid chest threshold')
                self.state['settings'].update(changes)
                self.save(True)
            elif action == 'reset':
                self.state['session'] = self.state['confirmed'] = 0
                self.state['session_chests'] = 0
                self.save(True)
            elif action == 'renderer-start':
                self.runtime = {'seen_at': self.clock(), 'connected': True}
            elif action in ('tick', 'observe'):
                if 'total' in body:
                    scope = 'normal:' + str(body.get('account', 'guest'))[:200]
                    self.observe(scope, body['total'])
                    self.runtime.update(total=body['total'], balance=body.get('balance', 0),
                                        logged_in=body.get('logged_in') is True,
                                        local_atlas=bool(offline), chests=body.get('chests', {}))
                self.runtime.update(seen_at=self.clock(), connected=True)
                sent = body.get('sent', 0)
                confirmed = body.get('confirmed', 0)
                if type(sent) is not int or sent not in (0, 1) or type(confirmed) is not int or not 0 <= confirmed <= sent:
                    raise ValueError('Invalid acknowledgment')
                self.state['session'] += sent
                self.state['confirmed'] += confirmed
                if action == 'tick':
                    now = self.clock()
                    quiet = self.physical is not None and self.physical.quiet()
                    allowed = not self.update_required and self.state['settings']['enabled'] and quiet and now >= self.next_tick
                    self.runtime.update(quiet=bool(quiet), blocked=self.update_required)
                    if allowed:
                        self.next_tick = now + 1 / self.state['settings']['speed']
                    self.save()
                    open_settings, self.open_settings = self.open_settings, False
                    quit_requested, self.quit_requested = self.quit_requested, False
                    return {'allowed': bool(allowed), 'quiet': bool(quiet), 'open_settings': open_settings, 'quit':quit_requested, 'flush_generation':self.flush_generation if self.flush_generation>self.flush_done else 0,
                            'settings': dict(self.state['settings']), 'session': self.state['session'],
                            'confirmed': self.state['confirmed'], 'update_required': self.update_required}
                self.save(body.get('flush') is True)
            elif action == 'flush-request':
                self.flush_generation += 1
            elif action == 'flush-ack':
                generation = body.get('generation')
                if type(generation) is int and self.flush_done <= generation <= self.flush_generation:
                    self.flush_done = generation
            elif action == 'open-settings':
                view = body.get('view')
                if view is not None and view not in ('settings', 'overview', 'rewards', 'daily', 'atlas'):
                    raise ValueError('Unknown view')
                self.open_settings = view or True
            elif action == 'quit':
                self.quit_requested = True
            elif action == 'local-chest':
                raise ValueError('模拟开箱已移除，请使用原版账号开箱')
            elif action == 'reward':
                item = body.get('reward', {})
                if not isinstance(item, dict) or item.get('confirmed') is not True:
                    raise ValueError('Only confirmed original chest results can be recorded')
                if not isinstance(item.get('id'), str) or not 1 <= len(item['id']) <= 120:
                    raise ValueError('Invalid reward event id')
                if item.get('side') not in ('left', 'right') or not item.get('asset_name'):
                    raise ValueError('Invalid original chest result')
                if len(json.dumps(item)) > 8192:
                    raise ValueError('Reward record too large')
                if not any(r['id'] == item['id'] for r in self.state['rewards']):
                    fields = ('id', 'side', 'asset_id', 'asset_type', 'asset_name', 'name', 'rarity', 'cost', 'source', 'image')
                    reward = {k: item[k] for k in fields if k in item}
                    reward.update(time=int(self.clock()), confirmed=True)
                    self.state['rewards'].insert(0, reward)
                    del self.state['rewards'][1000:]
                    self.state['session_chests'] += 1
                    self.save(True)
            elif action == 'room':
                if offline:
                    raise ValueError('本地模式不能进入联机')
                code = str(body.get('code', '')).strip()
                if not re_room(code):
                    raise ValueError('Invalid room code')
                rooms = self.state['rooms']
                old = next((r for r in rooms if r['code'] == code), None)
                if old:
                    rooms.remove(old)
                rooms.insert(0, {'code': code, 'host': str(body.get('host', ''))[:100],
                                 'favorite': old.get('favorite', False) if old else False, 'visited': int(self.clock())})
                rooms.sort(key=lambda r: not r['favorite'])
                del rooms[100:]
                self.save(True)
            elif action == 'favorite':
                for room in self.state['rooms']:
                    if room['code'] == body.get('code'):
                        room['favorite'] = body.get('favorite') is True
                self.state['rooms'].sort(key=lambda r: not r['favorite'])
                self.save(True)
            elif action == 'monitor':
                monitor = body.get('monitor')
                if monitor is not None and (not isinstance(monitor, dict) or not isinstance(monitor.get('name'), str)):
                    raise ValueError('Invalid monitor')
                if len(json.dumps(monitor)) > 2048:
                    raise ValueError('Monitor record too large')
                self.state['monitor'] = monitor
                self.save(True)
            elif action != 'state':
                raise ValueError('Unknown assistant action')
            return self.snapshot()


def re_room(code):
    import re
    return bool(re.fullmatch(r'[A-Za-z0-9-]{1,32}', code))
