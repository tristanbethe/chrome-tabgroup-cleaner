"""
🗄️ chrome_leveldb.py — minimal, dependency-free LevelDB reader/writer
=====================================================================

Reads a Chrome/Chromium LevelDB folder (e.g. 'Sync Data/LevelDB' or an
IndexedDB '*.leveldb' folder) and yields the LIVE key/value records — with
tombstones (deleted records) filtered out via the highest sequence numbers.

Supports:
  • .log  write-ahead-log files (uncompressed, block/record framing)
  • .ldb / .sst SSTable files (block format + snappy decompression)

Deliberately pure-Python with no external packages, so the tool runs anywhere
without build hassle. Read-only for reading; the write layer only appends.

Based on the public LevelDB on-disk format (leveldb/table_format.md,
leveldb/log_format.md) and the Snappy raw format.

⚠️ Chrome must be closed (file locks) — same as for the inspector.
"""

import struct
from pathlib import Path

# Magic number at the end of every SSTable footer (leveldb)
TABLE_MAGIC = 0xDB4775248B80FB57
FOOTER_LEN = 48
LOG_BLOCK_SIZE = 32768

# LevelDB internal-key value types
TYPE_DELETION = 0x0
TYPE_VALUE = 0x1


# ------------------------------------------------------------------
# 🔢 Varint (LE base-128)
# ------------------------------------------------------------------
def read_varint(data, pos):
    """Read a varint at data[pos]; return (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


# ------------------------------------------------------------------
# 🗜️ Snappy raw decompression (pure Python)
# ------------------------------------------------------------------
def snappy_decompress(data):
    """Decompress a Snappy 'raw' block. Returns bytes."""
    length, pos = read_varint(data, 0)
    out = bytearray()
    n = len(data)
    while pos < n:
        tag = data[pos]
        pos += 1
        kind = tag & 0x03
        if kind == 0:  # literal
            lit_len = tag >> 2
            if lit_len >= 60:
                extra = lit_len - 59          # 60->1, 61->2, 62->3, 63->4
                lit_len = int.from_bytes(data[pos:pos + extra], "little")
                pos += extra
            lit_len += 1
            out += data[pos:pos + lit_len]
            pos += lit_len
        else:
            if kind == 1:      # copy, 1-byte offset
                copy_len = ((tag >> 2) & 0x07) + 4
                offset = ((tag >> 5) << 8) | data[pos]
                pos += 1
            elif kind == 2:    # copy, 2-byte offset
                copy_len = (tag >> 2) + 1
                offset = int.from_bytes(data[pos:pos + 2], "little")
                pos += 2
            else:              # kind == 3, copy, 4-byte offset
                copy_len = (tag >> 2) + 1
                offset = int.from_bytes(data[pos:pos + 4], "little")
                pos += 4
            start = len(out) - offset
            # byte-by-byte because copies may overlap
            for i in range(copy_len):
                out.append(out[start + i])
    if length != len(out):
        # not fatal; return what we have
        pass
    return bytes(out)


# ------------------------------------------------------------------
# 📄 .log (write-ahead log) parser
# ------------------------------------------------------------------
def _iter_log_batches(raw):
    """Reassemble logical records (WriteBatches) from the block/record framing."""
    pos = 0
    n = len(raw)
    pending = bytearray()
    while pos + 7 <= n:
        # block alignment: fewer than 7 bytes left in this block -> skip padding
        block_off = pos % LOG_BLOCK_SIZE
        if LOG_BLOCK_SIZE - block_off < 7:
            pos += (LOG_BLOCK_SIZE - block_off)
            continue
        # 7-byte header: crc(4) + length(2 LE) + type(1)
        length = struct.unpack_from("<H", raw, pos + 4)[0]
        rtype = raw[pos + 6]
        pos += 7
        chunk = raw[pos:pos + length]
        pos += length
        if rtype == 1:          # FULL
            yield bytes(chunk)
        elif rtype == 2:        # FIRST
            pending = bytearray(chunk)
        elif rtype == 3:        # MIDDLE
            pending += chunk
        elif rtype == 4:        # LAST
            pending += chunk
            yield bytes(pending)
            pending = bytearray()
        # rtype 0 = padding / empty: ignore


def _parse_write_batch(batch):
    """Parse a WriteBatch: header(seq u64 + count u32) + records."""
    if len(batch) < 12:
        return
    seq = struct.unpack_from("<Q", batch, 0)[0]
    count = struct.unpack_from("<I", batch, 8)[0]
    pos = 12
    for _ in range(count):
        if pos >= len(batch):
            break
        tag = batch[pos]
        pos += 1
        if tag == TYPE_VALUE:
            klen, pos = read_varint(batch, pos)
            key = batch[pos:pos + klen]; pos += klen
            vlen, pos = read_varint(batch, pos)
            val = batch[pos:pos + vlen]; pos += vlen
            yield key, val, seq, TYPE_VALUE
        elif tag == TYPE_DELETION:
            klen, pos = read_varint(batch, pos)
            key = batch[pos:pos + klen]; pos += klen
            yield key, b"", seq, TYPE_DELETION
        else:
            break  # unknown -> stop parsing this batch
        seq += 1


def read_log_file(path):
    """Yield (user_key, value, seq, type) from a .log file."""
    raw = Path(path).read_bytes()
    for batch in _iter_log_batches(raw):
        yield from _parse_write_batch(batch)


# ------------------------------------------------------------------
# 🧱 .ldb / .sst (SSTable) parser
# ------------------------------------------------------------------
def _read_block(raw, offset, size):
    """Read a block + trailer (type 1 byte, crc 4 bytes); decompress if snappy."""
    block = raw[offset:offset + size]
    btype = raw[offset + size]          # compression type
    if btype == 0:
        return block
    elif btype == 1:
        return snappy_decompress(block)
    else:
        raise ValueError(f"Unknown block compression {btype} (not none/snappy)")


def _iter_block_entries(block):
    """Yield (key_bytes, value_bytes) from a decompressed block."""
    if len(block) < 4:
        return
    num_restarts = struct.unpack_from("<I", block, len(block) - 4)[0]
    restart_region = (num_restarts + 1) * 4
    end = len(block) - restart_region
    pos = 0
    last_key = b""
    while pos < end:
        shared, pos = read_varint(block, pos)
        non_shared, pos = read_varint(block, pos)
        vlen, pos = read_varint(block, pos)
        key_delta = block[pos:pos + non_shared]; pos += non_shared
        value = block[pos:pos + vlen]; pos += vlen
        key = last_key[:shared] + key_delta
        last_key = key
        yield key, value


def read_table_file(path):
    """Yield (user_key, value, seq, type) from a .ldb/.sst file."""
    raw = Path(path).read_bytes()
    if len(raw) < FOOTER_LEN:
        return
    footer = raw[-FOOTER_LEN:]
    magic = struct.unpack_from("<Q", footer, FOOTER_LEN - 8)[0]
    if magic != TABLE_MAGIC:
        return  # not a valid leveldb table
    # footer starts with metaindex_handle, then index_handle (varints)
    _, fp = read_varint(footer, 0)        # metaindex offset
    _, fp = read_varint(footer, fp)       # metaindex size
    idx_off, fp = read_varint(footer, fp)
    idx_size, fp = read_varint(footer, fp)

    index_block = _read_block(raw, idx_off, idx_size)
    for _sep_key, handle_val in _iter_block_entries(index_block):
        d_off, hp = read_varint(handle_val, 0)
        d_size, hp = read_varint(handle_val, hp)
        try:
            data_block = _read_block(raw, d_off, d_size)
        except Exception:
            continue
        for ikey, value in _iter_block_entries(data_block):
            if len(ikey) < 8:
                continue
            user_key = ikey[:-8]
            trailer = struct.unpack_from("<Q", ikey, len(ikey) - 8)[0]
            seq = trailer >> 8
            vtype = trailer & 0xFF
            yield user_key, value, seq, vtype


# ------------------------------------------------------------------
# 🔀 Merge: live records from a whole LevelDB folder
# ------------------------------------------------------------------
class LevelDBRecord:
    __slots__ = ("key", "value", "seq", "type", "source")

    def __init__(self, key, value, seq, vtype, source):
        self.key = key
        self.value = value
        self.seq = seq
        self.type = vtype
        self.source = source

    @property
    def is_live(self):
        return self.type == TYPE_VALUE


def read_leveldb_dir(dir_path):
    """Read all .log + .ldb/.sst in a folder and merge to the latest record per
    key (highest seq). Returns a list[LevelDBRecord] (both live and deleted)."""
    dir_path = Path(dir_path)
    best = {}   # user_key -> LevelDBRecord (highest seq)

    def consider(key, value, seq, vtype, source):
        cur = best.get(key)
        if cur is None or seq >= cur.seq:
            best[key] = LevelDBRecord(key, value, seq, vtype, source)

    for f in sorted(dir_path.glob("*.ldb")) + sorted(dir_path.glob("*.sst")):
        try:
            for key, value, seq, vtype in read_table_file(f):
                consider(key, value, seq, vtype, f.name)
        except Exception:
            continue
    for f in sorted(dir_path.glob("*.log")):
        try:
            for key, value, seq, vtype in read_log_file(f):
                consider(key, value, seq, vtype, f.name)
        except Exception:
            continue

    return list(best.values())


# ------------------------------------------------------------------
# ✍️  WRITE layer: surgically append deletions to the log
# ------------------------------------------------------------------
# CRC32C (Castagnoli, reflected) — leveldb log records require this, otherwise
# Chrome treats the record as corrupt and ignores/truncates the log.
def _make_crc32c_table():
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 & -(crc & 1))
        table.append(crc & 0xFFFFFFFF)
    return table


_CRC32C_TABLE = _make_crc32c_table()


def crc32c(data):
    """Standard CRC32C value (with init/final 0xFFFFFFFF) of data."""
    crc = 0xFFFFFFFF
    for b in data:
        crc = _CRC32C_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def _mask_crc(crc):
    """leveldb's crc masking (rotate + delta)."""
    return (((crc >> 15) | (crc << 17)) + 0xA282EAD8) & 0xFFFFFFFF


def _put_varint32(value):
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def build_deletion_batch(keys, start_seq):
    """Build a leveldb WriteBatch with deletions only for `keys`.
    Header: seq(u64 LE) + count(u32 LE); per record: 0x00 + varint(len) + key."""
    body = bytearray()
    for k in keys:
        body.append(TYPE_DELETION)
        body += _put_varint32(len(k))
        body += k
    header = struct.pack("<QI", start_seq, len(keys))
    return bytes(header) + bytes(body)


def append_batch_to_log(log_path, batch):
    """Frame a WriteBatch into log records (32KB blocks, crc32c) and append to the
    existing log file, with correct block alignment."""
    log_path = Path(log_path)
    size = log_path.stat().st_size
    block_offset = size % LOG_BLOCK_SIZE
    out = bytearray()

    def emit(rtype, payload):
        crc = _mask_crc(crc32c(bytes([rtype]) + payload))
        out.extend(struct.pack("<IH", crc, len(payload)))
        out.append(rtype)
        out.extend(payload)

    ptr = 0
    left = len(batch)
    begin = True
    while True:
        leftover = LOG_BLOCK_SIZE - block_offset
        if leftover < 7:
            out.extend(b"\x00" * leftover)   # block-trailer padding
            block_offset = 0
            leftover = LOG_BLOCK_SIZE
        avail = LOG_BLOCK_SIZE - block_offset - 7
        frag = min(left, avail)
        end = (left == frag)
        if begin and end:
            rtype = 1   # FULL
        elif begin:
            rtype = 2   # FIRST
        elif end:
            rtype = 4   # LAST
        else:
            rtype = 3   # MIDDLE
        emit(rtype, batch[ptr:ptr + frag])
        ptr += frag
        left -= frag
        begin = False
        block_offset += 7 + frag
        if left == 0:
            break

    with open(log_path, "ab") as f:
        f.write(out)
    return len(out)


def max_sequence(records):
    """Highest sequence number in a set of records (for new writes)."""
    return max((r.seq for r in records), default=0)


def active_log_file(dir_path):
    """The log file Chrome replays on startup = highest-numbered .log."""
    logs = sorted(Path(dir_path).glob("*.log"),
                  key=lambda p: int(p.stem) if p.stem.isdigit() else -1)
    return logs[-1] if logs else None


if __name__ == "__main__":
    import sys
    # 🧪 CRC32C self-test: known vector "123456789" -> 0xE3069283
    assert crc32c(b"123456789") == 0xE3069283, "CRC32C implementation is broken!"
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if len(sys.argv) < 2:
        print("Usage: python chrome_leveldb.py <path to leveldb folder>")
        sys.exit(1)
    recs = read_leveldb_dir(sys.argv[1])
    live = [r for r in recs if r.is_live]
    print(f"📦 {len(recs)} unique keys, of which {len(live)} live, "
          f"{len(recs) - len(live)} tombstoned")
