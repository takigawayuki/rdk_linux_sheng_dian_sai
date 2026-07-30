"""Fixed 18-byte vision-to-motor serial protocol."""

from dataclasses import dataclass
from enum import IntEnum
import math
import struct


SOF = 0xA5
PAYLOAD_SIZE = 16
PACKET_SIZE = 18
_PAYLOAD_FORMAT = "<BBfffH"


class VisionStatus(IntEnum):
    """0x20 remains the valid-target flag used by the reference protocol."""

    LOST = 0x00
    DETECTED = 0x20
    PREDICTED = 0x21


@dataclass(frozen=True)
class VisionSerialFrame:
    status: VisionStatus
    error_cm: float
    position_cm: float
    velocity_cm_s: float
    sequence: int

    def validate(self) -> None:
        if not isinstance(self.status, VisionStatus):
            raise ValueError("status must be a VisionStatus")
        if not all(
            math.isfinite(value)
            for value in (self.error_cm, self.position_cm, self.velocity_cm_s)
        ):
            raise ValueError("vision frame float fields must be finite")
        if not 0 <= self.sequence <= 0xFFFF:
            raise ValueError("sequence must fit in uint16")


def crc16(data: bytes) -> int:
    """CRC-16/MCRF4XX used by the supplied A5...BE 99 reference packet."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 0x0001 else crc >> 1
    return crc & 0xFFFF


def build_packet(frame: VisionSerialFrame) -> bytes:
    frame.validate()
    payload = struct.pack(
        _PAYLOAD_FORMAT,
        SOF,
        int(frame.status),
        frame.error_cm,
        frame.position_cm,
        frame.velocity_cm_s,
        frame.sequence,
    )
    if len(payload) != PAYLOAD_SIZE:
        raise AssertionError("vision protocol payload size changed")
    return payload + struct.pack("<H", crc16(payload))


def parse_packet(packet: bytes) -> VisionSerialFrame:
    if len(packet) != PACKET_SIZE:
        raise ValueError(f"vision packet must be {PACKET_SIZE} bytes")
    if packet[0] != SOF:
        raise ValueError("invalid vision packet start byte")
    expected_crc = crc16(packet[:PAYLOAD_SIZE])
    received_crc = struct.unpack_from("<H", packet, PAYLOAD_SIZE)[0]
    if received_crc != expected_crc:
        raise ValueError("vision packet CRC mismatch")
    _, status, error_cm, position_cm, velocity_cm_s, sequence = struct.unpack(
        _PAYLOAD_FORMAT, packet[:PAYLOAD_SIZE]
    )
    try:
        parsed_status = VisionStatus(status)
    except ValueError as error:
        raise ValueError(f"unsupported vision status: 0x{status:02X}") from error
    return VisionSerialFrame(
        status=parsed_status,
        error_cm=error_cm,
        position_cm=position_cm,
        velocity_cm_s=velocity_cm_s,
        sequence=sequence,
    )

