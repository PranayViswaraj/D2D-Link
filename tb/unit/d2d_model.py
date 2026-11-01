"""Python reference models shared by unit and system tests."""

FT = dict(IDLE=0, REQ_HDR=1, REQ_DATA=2, RSP_HDR=3, RSP_DATA=4, ACK=5, NAK=6, CREDIT=7, TRAIN=8)
TRAIN_PATTERN = 0xD2D2A5A55A5AC3C33C
ST = dict(RESET=0, TRAIN=1, ACTIVE=2, RETRAIN=3, FAILED=4)


def crc16_ccitt(value: int, nbits: int) -> int:
    """CRC-16/CCITT-FALSE over an nbits-wide integer, MSB first."""
    crc = 0xFFFF
    for i in range(nbits - 1, -1, -1):
        fb = ((crc >> 15) & 1) ^ ((value >> i) & 1)
        crc = ((crc << 1) & 0xFFFF) ^ (0x1021 if fb else 0)
    return crc


def crc16_bytes(data: bytes) -> int:
    return crc16_ccitt(int.from_bytes(data, "big"), 8 * len(data))


# Self-check of the model against the published check value of CRC-16/CCITT-FALSE.
assert crc16_bytes(b"123456789") == 0x29B1


def make_flit(typ, seq=0, ack=0, cq=0, cs=0, flags=0, payload=0):
    hdr = (typ << 108) | (seq << 100) | (ack << 92) | (cq << 84) | (cs << 76) | (flags << 72) | payload
    return (hdr << 16) | crc16_ccitt(hdr, 112)


def split_flit(f):
    return dict(type=(f >> 124) & 0xF, seq=(f >> 116) & 0xFF, ack=(f >> 108) & 0xFF,
                cq=(f >> 100) & 0xFF, cs=(f >> 92) & 0xFF, flags=(f >> 88) & 0xF,
                payload=(f >> 16) & ((1 << 72) - 1), crc=f & 0xFFFF,
                crc_ok=crc16_ccitt(f >> 16, 112) == (f & 0xFFFF))
