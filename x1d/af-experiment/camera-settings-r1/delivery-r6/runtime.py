"""AF r3 主机诊断；保持原 AF 合同，首笔跨路由回复只等待一次。"""
import hashlib, json, os, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
AF = HERE.parent
sys.path.insert(0, str(AF))
from af_only_install import AfOnlyLoader, UpgradeIO
from range_contract import AfOnlyContract

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()

class Trace:
    def __init__(self, path, contract):
        self.path = Path(path)
        self.file = self.path.open('xb')
        self.seq = 0
        self.previous = '0' * 64
        self.append({'event': 'header', 'contractSha256': contract,
                     'policySha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

    def append(self, data):
        item = dict(data, seq=self.seq, previous=self.previous)
        digest = hashlib.sha256(canonical(item)).hexdigest()
        line = canonical(dict(item, sha256=digest)) + b'\n'
        if self.file.write(line) != len(line):
            raise OSError('short trace write')
        self.file.flush()
        os.fsync(self.file.fileno())
        self.seq += 1
        self.previous = digest

    def close(self):
        self.file.close()

    @staticmethod
    def inspect(path):
        raw = Path(path).read_bytes()
        lines = raw.splitlines(keepends=True)
        previous = '0' * 64
        items = []
        for index, line in enumerate(lines):
            if not line.endswith(b'\n'):
                return {'completeTail': False, 'events': items, 'lastSha256': previous}
            item = json.loads(line)
            digest = item.pop('sha256')
            if item['seq'] != index or item['previous'] != previous or hashlib.sha256(canonical(item)).hexdigest() != digest:
                raise ValueError('trace chain mismatch')
            previous = digest
            items.append(item)
        if not items or items[0]['event'] != 'header':
            raise ValueError('trace header missing')
        return {'completeTail': True, 'events': items, 'lastSha256': previous}

class TracedIO(UpgradeIO):
    def __init__(self, contract, trace):
        super().__init__(contract)
        self.trace = trace
        self.after_hold = False
        self.last_operation = None
        self.metrics = None

    def traced(self, kind, address, callback, timeout, boundary=None):
        if self.failed:
            raise RuntimeError('failed transaction; no retry')
        started = self.clock()
        self.metrics = {}
        self.last_operation = {'kind': kind, 'address': None if address is None else hex(address),
            'boundary': boundary, 'nextRequest': self.requests + 1, 'timeoutMs': timeout}
        result = None
        error = None
        try:
            self.trace.append(dict(self.last_operation, event='intent', phase=self.phase,
                monotonic=started, requests=self.requests, writes=self.writes))
            result = callback()
        except BaseException as caught:
            error = caught
            self.failed = True
            raise
        finally:
            try:
                self.trace.append(dict(self.last_operation, event='result', phase=self.phase,
                    monotonic=self.clock(), elapsedMs=round((self.clock()-started)*1000, 3),
                    requests=self.requests, writes=self.writes, allHandlesClosed=self.closed,
                    ok=error is None, errorType=None if error is None else type(error).__name__,
                    error=None if error is None else str(error), win32=getattr(error, 'win32', None),
                    transport=dict(self.metrics)))
            except BaseException:
                self.failed = True
                raise
        return result

    def exchange(self, kind, a=None, v=None):
        first = self.after_hold
        self.after_hold = False
        # Only the first FARM read/version after a successful Linux hold gets 20 s.
        timeout = 20000 if first and kind in ('read', 'version') else 2000
        self.read_timeout = timeout
        return self.traced(kind, a, lambda: super(TracedIO, self).exchange(kind, a, v), timeout)

    def check_hold(self, label):
        result = self.traced('hold', None, lambda: super(TracedIO, self).check_hold(label), 20000, label)
        self.after_hold = True
        return result

    def wrap(self, packet, timeout, farm):
        io = self
        original_write = packet.write_query
        original_read = packet.read_reply
        def write(size):
            io.metrics['writeStarted'] = io.clock()
            try:
                count = original_write(size)
                io.metrics['writeBytes'] = count
                return count
            finally:
                io.metrics['writeEnded'] = io.clock()
        def read(size):
            io.metrics['readStarted'] = io.clock()
            try:
                if farm and timeout != 2000:
                    data = io.read_with_timeout(packet, size, timeout)
                else:
                    data = original_read(size)
                io.metrics['readBytes'] = len(data)
                return data
            finally:
                io.metrics['readEnded'] = io.clock()
        packet.write_query = write
        packet.read_reply = read
        return packet

    def transport(self, kind, a, v):
        return self.wrap(super().transport(kind, a, v), self.read_timeout, True)

    def hold_transport(self, packet, token):
        return self.wrap(super().hold_transport(packet, token), 20000, False)

    def read_with_timeout(self, packet, size, timeout):
        import read_usb_link_once as usb
        if size != 512 or timeout != 20000:
            raise ValueError('r3 first reply policy')
        remaining = timeout
        if self.segment_deadline is not None:
            remaining = min(timeout, int((self.segment_deadline - self.clock()) * 1000))
        if remaining < 1:
            raise RuntimeError('hold segment expired before reply')
        self.metrics['effectiveReadTimeoutMs'] = remaining
        value = usb.U32(remaining)
        packet.check(packet.winusb.WinUsb_SetPipePolicy(packet.usb, 0x82, 3, 4, usb.c.byref(value)), 'USB_TIMEOUT_POLICY')
        buffer = usb.c.create_string_buffer(size)
        count = usb.U32()
        try:
            packet.check(packet.winusb.WinUsb_ReadPipe(packet.usb, 0x82, buffer, size, usb.c.byref(count), None), 'USB_READ')
            return buffer.raw[:count.value]
        finally:
            usb.c.memset(buffer, 0, size)
