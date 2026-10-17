"""Bounded, read-only selected-session metadata; no discovery or prose export."""
import json
import math
import os
import re
import stat
from contextlib import contextmanager


def text(value, limit=200):
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


def integer(value):
    return value if type(value) is int and value >= 0 else None


def number(value):
    if type(value) is int:
        return integer(value)
    return value if type(value) is float and value >= 0 and math.isfinite(value) else None


def metadata(kind, raw):
    if not isinstance(raw, dict):
        raise ValueError('metadata object required')
    if kind == 'plan':
        rows = raw.get('agents')
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ValueError('agents required')
        result = []
        for row in rows:
            if not isinstance(row, dict) or not text(row.get('name')):
                raise ValueError('invalid agent')
            level = row.get('level')
            result.append({'name': row['name'], 'level': level if type(level) is int else text(level),
                           'parent': text(row.get('parent'))})
        return {'agents': result}
    if kind == 'board':
        count, stops = integer(raw.get('event_count')), integer(raw.get('pressure_stop_count'))
        if count is None or stops is None:
            raise ValueError('invalid board counts')
        return {'event_count': count, 'last_event_at': text(raw.get('last_event_at')), 'pressure_stop_count': stops}
    stopped = raw.get('stopped_agents', [])
    if not isinstance(stopped, list) or len(stopped) > 1000 or any(not text(x) for x in stopped):
        raise ValueError('invalid stopped identifiers')
    return {'elapsed_minutes': number(raw.get('elapsed_minutes')), 'requests': integer(raw.get('requests')),
            'upper_bound_cents_for_reported_usage': number(raw.get('upper_bound_cents_for_reported_usage')),
            'unknown_usage': raw.get('unknown_usage') if type(raw.get('unknown_usage')) is bool else None,
            'stopped_agents': sorted(set(stopped))}


def _decode(data, kind):
    def reject(value):
        raise ValueError('nonfinite JSON')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def load(value):
        return json.loads(value, parse_constant=reject, object_pairs_hook=pairs)
    decoded = data.decode('utf-8')
    if kind != 'board':
        raw = load(decoded)
        return metadata(kind, raw), text(raw.get('at_utc'))
    rows = [load(line) for line in decoded.splitlines() if line.strip()]
    if any(not isinstance(row, dict) or not text(row.get('event')) for row in rows):
        raise ValueError('invalid event')
    stamp = text(rows[-1].get('at_utc')) if rows else None
    return metadata(kind, {'event_count': len(rows), 'last_event_at': stamp,
                          'pressure_stop_count': sum(row['event'] == 'pressure_stop' for row in rows)}), stamp


@contextmanager
def _selected(base_dir, session_id):
    path = os.fspath(base_dir)
    held = []
    try:
        if os.name == 'nt':
            import ctypes as c
            from ctypes import wintypes as w
            import msvcrt
            # Only canonical local drive paths; no UNC, device names or alternate streams.
            if not isinstance(path, str) or not re.fullmatch(r'[A-Za-z]:\\.*', path):
                raise ValueError('absolute local base required')
            parts = path[3:].split('\\')
            if any(not p or p in ('.', '..') or re.search(r'[<>:"/|?*\x00-\x1f]', p)
                   or p.endswith((' ', '.')) for p in parts):
                raise ValueError('noncanonical base')
            api = c.WinDLL('kernel32', use_last_error=True)
            api.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
            api.CreateFileW.restype = w.HANDLE
            api.CloseHandle.argtypes = [w.HANDLE]
            api.GetFileInformationByHandleEx.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
            api.GetFileType.argtypes = [w.HANDLE]
            def winopen(name, directory):
                # Share READ only: retained ancestors cannot be renamed or opened for mutation.
                handle = api.CreateFileW('\\\\?\\' + name, 0x80 if directory else 0x80000000,
                                         1, None, 3, 0x02200000, None)
                if handle == c.c_void_p(-1).value:
                    raise c.WinError(c.get_last_error())
                try:
                    attrs = (w.DWORD * 2)()
                    if not api.GetFileInformationByHandleEx(handle, 9, attrs, c.sizeof(attrs)):
                        raise c.WinError(c.get_last_error())
                    if attrs[0] & 0x400 or bool(attrs[0] & 0x10) != directory or api.GetFileType(handle) != 1:
                        raise ValueError('reparse or wrong resource type')
                    if directory:
                        held.append(handle)
                        return None
                    return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
                except BaseException:
                    api.CloseHandle(handle)
                    raise
            current = path[:3]
            winopen(current, True)
            for part in parts + [session_id]:
                current = current.rstrip('\\') + '\\' + part
                winopen(current, True)
            yield lambda name: winopen(current + '\\' + name, False)
        else:
            if not isinstance(path, str) or not os.path.isabs(path) or any(p in ('.', '..') for p in path.split('/')):
                raise ValueError('absolute canonical base required')
            if any(not hasattr(os, x) for x in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK')) or os.open not in os.supports_dir_fd:
                raise NotImplementedError('safe relative opens unavailable')
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            held.append(os.open('/', flags))
            for part in list(filter(None, path.split('/'))) + [session_id]:
                held.append(os.open(part, flags, dir_fd=held[-1]))
            yield lambda name: os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=held[-1])
    finally:
        for handle in reversed(held):
            api.CloseHandle(handle) if os.name == 'nt' else os.close(handle)


def read_session_metadata(session_id, *, base_dir, max_bytes=65536):
    """base_dir is the authorized absolute .data/astra-tree directory."""
    if not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,199}', session_id):
        raise ValueError('invalid selected session identifier')
    if type(max_bytes) is not int or not 1 <= max_bytes <= 65536:
        raise ValueError('invalid byte limit')
    result = {'id': session_id, 'sources': {}, 'plan': None, 'board': None, 'summary': None}
    def mark(kind, status, stamp=None):
        result['sources'][kind] = {'status': status, 'event_at': stamp}
    try:
        with _selected(base_dir, session_id) as opener:
            for kind in ('plan', 'board', 'summary'):
                fd = None
                try:
                    fd = opener(kind + ('.jsonl' if kind == 'board' else '.json'))
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise ValueError('regular file required')
                    data = bytearray()
                    while len(data) <= max_bytes:
                        chunk = os.read(fd, min(8192, max_bytes + 1 - len(data)))
                        if not chunk:
                            break
                        data.extend(chunk)
                    if len(data) > max_bytes:
                        raise ValueError('source too large')
                    result[kind], stamp = _decode(data, kind)
                    mark(kind, 'available', stamp)
                except FileNotFoundError:
                    mark(kind, 'missing')
                except (OSError, ValueError, RecursionError, OverflowError):
                    mark(kind, 'invalid')
                finally:
                    if fd is not None:
                        os.close(fd)
    except (OSError, ValueError, NotImplementedError) as exc:
        status = 'missing' if isinstance(exc, FileNotFoundError) else 'unavailable' if isinstance(exc, NotImplementedError) else 'invalid'
        for kind in ('plan', 'board', 'summary'):
            mark(kind, status)
    return result
