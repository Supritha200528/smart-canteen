"""
Compact, pure Python QR Code generator (Byte Mode, Version 1-5, ECC Level M).
Zero third-party dependencies. Generates valid SVG output.
"""

def _gf_tables():
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        exp[i + 255] = x
        log[x] = i
        x = (x << 1) ^ (0x11D if (x & 0x80) else 0)
    return exp, log

_EXP, _LOG = _gf_tables()

def _gf_mul(x, y):
    if x == 0 or y == 0:
        return 0
    return _EXP[_LOG[x] + _LOG[y]]

def _rs_poly(degree):
    g = [1]
    for i in range(degree):
        root = _EXP[i]
        next_g = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            next_g[j] ^= _gf_mul(c, root)
            next_g[j + 1] ^= c
        g = next_g
    return g

def _rs_encode(data, ecc_len):
    gen = _rs_poly(ecc_len)
    msg = list(data) + [0] * ecc_len
    for i in range(len(data)):
        coef = msg[i]
        if coef != 0:
            for j in range(len(gen)):
                msg[i + j] ^= _gf_mul(gen[j], coef)
    return msg[len(data):]

QR_SPECS = {
    1: {"size": 21, "data_bytes": 14, "total_cw": 26, "ecc_cw": 10, "align": []},
    2: {"size": 25, "data_bytes": 26, "total_cw": 44, "ecc_cw": 16, "align": [18]},
    3: {"size": 29, "data_bytes": 42, "total_cw": 70, "ecc_cw": 26, "align": [22]},
    4: {"size": 33, "data_bytes": 62, "total_cw": 100, "ecc_cw": 36, "align": [26]},
    5: {"size": 37, "data_bytes": 84, "total_cw": 134, "ecc_cw": 48, "align": [30]},
}

FORMAT_BITS = {
    0: 0b101010000010010 ^ 0b000001010011001,
    1: 0b101010000010010 ^ 0b000010101010011,
    2: 0b101010000010010 ^ 0b000100011111100,
    3: 0b101010000010010 ^ 0b000111100110110,
    4: 0b101010000010010 ^ 0b001001101111010,
    5: 0b101010000010010 ^ 0b001010010110000,
    6: 0b101010000010010 ^ 0b001100110011111,
    7: 0b101010000010010 ^ 0b001111001010101,
}

def generate_qr_svg(text: str, scale: int = 8, margin: int = 4) -> str:
    """Generate an SVG string for the given text."""
    raw = text.encode("utf-8")
    version = None
    for v in (1, 2, 3, 4, 5):
        if len(raw) <= QR_SPECS[v]["data_bytes"]:
            version = v
            break
    if not version:
        # Fall back to v5 truncated if unexpectedly long
        version = 5
        raw = raw[:QR_SPECS[5]["data_bytes"]]

    spec = QR_SPECS[version]
    total_cw = spec["total_cw"]
    ecc_cw_len = spec["ecc_cw"]
    data_bytes = spec["data_bytes"]

    # Byte mode = 0100 (4 bits) + char count (8 bits) + data bits
    bits = "0100" + f"{len(raw):08b}"
    for b in raw:
        bits += f"{b:08b}"

    needed_bits = (total_cw - ecc_cw_len) * 8
    pad_term = min(4, needed_bits - len(bits))
    bits += "0" * pad_term

    if len(bits) % 8 != 0:
        bits += "0" * (8 - (len(bits) % 8))

    pad_bytes = ["11101100", "00010001"]
    p_idx = 0
    while len(bits) < needed_bits:
        bits += pad_bytes[p_idx % 2]
        p_idx += 1

    data_cw = [int(bits[i:i+8], 2) for i in range(0, len(bits), 8)]
    ecc_cw = _rs_encode(data_cw, ecc_cw_len)
    all_cw = data_cw + ecc_cw

    n = spec["size"]
    mat = [[None] * n for _ in range(n)]
    is_func = [[False] * n for _ in range(n)]

    def set_finder(r, c):
        for dr in range(7):
            for dc in range(7):
                is_func[r + dr][c + dc] = True
                if dr in (0, 6) or dc in (0, 6):
                    mat[r + dr][c + dc] = 1
                elif 2 <= dr <= 4 and 2 <= dc <= 4:
                    mat[r + dr][c + dc] = 1
                else:
                    mat[r + dr][c + dc] = 0
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if 0 <= rr < n and 0 <= cc < n and not is_func[rr][cc]:
                    is_func[rr][cc] = True
                    mat[rr][cc] = 0

    set_finder(0, 0)
    set_finder(0, n - 7)
    set_finder(n - 7, 0)

    for pos in spec["align"]:
        r, c = pos, pos
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                rr, cc = r + dr, c + dc
                if not is_func[rr][cc]:
                    is_func[rr][cc] = True
                    if abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0):
                        mat[rr][cc] = 1
                    else:
                        mat[rr][cc] = 0

    for i in range(n):
        if not is_func[6][i]:
            is_func[6][i] = True
            mat[6][i] = 1 if i % 2 == 0 else 0
        if not is_func[i][6]:
            is_func[i][6] = True
            mat[i][6] = 1 if i % 2 == 0 else 0

    is_func[4 * version + 9][8] = True
    mat[4 * version + 9][8] = 1

    for i in range(9):
        if not is_func[8][i]: is_func[8][i] = True
        if not is_func[i][8]: is_func[i][8] = True
    for i in range(8):
        if not is_func[8][n - 1 - i]: is_func[8][n - 1 - i] = True
        if not is_func[n - 1 - i][8]: is_func[n - 1 - i][8] = True

    bits_stream = "".join(f"{b:08b}" for b in all_cw)
    bit_idx = 0
    right = n - 1
    upward = True
    while right > 0:
        if right == 6:
            right -= 1
        cols = [right, right - 1]
        rows = range(n - 1, -1, -1) if upward else range(n)
        for r in rows:
            for c in cols:
                if not is_func[r][c]:
                    bit = int(bits_stream[bit_idx]) if bit_idx < len(bits_stream) else 0
                    bit_idx += 1
                    mask = 1 if (r + c) % 2 == 0 else 0
                    mat[r][c] = bit ^ mask
        upward = not upward
        right -= 2

    fmt = FORMAT_BITS[0]
    fmt_bits = [(fmt >> (14 - i)) & 1 for i in range(15)]
    for i in range(6): mat[8][i] = fmt_bits[i]
    mat[8][7] = fmt_bits[6]
    mat[8][8] = fmt_bits[7]
    mat[7][8] = fmt_bits[8]
    for i in range(9, 15): mat[14 - i][8] = fmt_bits[i]

    for i in range(7): mat[n - 1 - i][8] = fmt_bits[i]
    for i in range(8): mat[8][n - 8 + i] = fmt_bits[7 + i]

    size = (n + 2 * margin) * scale
    rects = []
    for r in range(n):
        for c in range(n):
            if mat[r][c] == 1:
                x = (c + margin) * scale
                y = (r + margin) * scale
                rects.append(f'<rect x="{x}" y="{y}" width="{scale}" height="{scale}" fill="#14213d"/>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">\n'
        f'  <rect width="{size}" height="{size}" fill="#ffffff" rx="10"/>\n'
        f'  {"".join(rects)}\n'
        f'</svg>'
    )
