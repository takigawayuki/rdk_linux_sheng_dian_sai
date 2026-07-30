import struct
import unittest

from project.Driver.my_serial import MySerial
from project.Driver.vision_protocol import (
    VisionSerialFrame,
    VisionStatus,
    build_packet,
    crc16,
    parse_packet,
)


class FakeSerial:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.is_open = True
        self.writes = []
        self.received = bytearray()

    @property
    def in_waiting(self):
        return len(self.received)

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def close(self):
        self.is_open = False

    def read(self, size):
        result = bytes(self.received[:size])
        del self.received[:size]
        return result


class VisionProtocolTests(unittest.TestCase):
    def test_crc_matches_supplied_reference_packet(self):
        payload = bytes.fromhex(
            "A5 20 00 80 0F 43 CD CC B6 43 00 00 00 00 00 00"
        )
        self.assertEqual(crc16(payload), 0x99BE)
        self.assertEqual(struct.pack("<H", crc16(payload)), bytes.fromhex("BE 99"))

    def test_packet_is_18_bytes_and_round_trips(self):
        source = VisionSerialFrame(
            status=VisionStatus.DETECTED,
            error_cm=-1.25,
            position_cm=3.5,
            velocity_cm_s=8.0,
            sequence=65535,
        )
        packet = build_packet(source)
        decoded = parse_packet(packet)
        self.assertEqual(len(packet), 18)
        self.assertEqual(packet[0], 0xA5)
        self.assertEqual(packet[1], 0x20)
        self.assertEqual(decoded.status, source.status)
        self.assertAlmostEqual(decoded.error_cm, source.error_cm)
        self.assertAlmostEqual(decoded.position_cm, source.position_cm)
        self.assertAlmostEqual(decoded.velocity_cm_s, source.velocity_cm_s)
        self.assertEqual(decoded.sequence, source.sequence)

    def test_crc_rejects_corrupted_packet(self):
        packet = bytearray(
            build_packet(VisionSerialFrame(VisionStatus.LOST, 0.0, 0.0, 0.0, 1))
        )
        packet[7] ^= 0x01
        with self.assertRaisesRegex(ValueError, "CRC"):
            parse_packet(bytes(packet))

    def test_serial_state_sends_target_minus_position(self):
        fake = FakeSerial()
        link = MySerial("loop", serial_factory=lambda **kwargs: fake)
        self.assertTrue(link.open())
        self.assertTrue(
            link.send_vision_state(
                position_cm=3.0,
                target_position_cm=1.0,
                velocity_cm_s=-2.0,
                sequence=9,
            )
        )
        decoded = parse_packet(fake.writes[0])
        self.assertAlmostEqual(decoded.error_cm, -2.0)
        self.assertAlmostEqual(decoded.position_cm, 3.0)
        self.assertAlmostEqual(decoded.velocity_cm_s, -2.0)
        self.assertEqual(decoded.sequence, 9)

    def test_lost_state_zeros_float_fields(self):
        fake = FakeSerial()
        link = MySerial("loop", serial_factory=lambda **kwargs: fake)
        link.open()
        link.send_vision_state(None, valid=False, sequence=10)
        decoded = parse_packet(fake.writes[0])
        self.assertEqual(decoded.status, VisionStatus.LOST)
        self.assertEqual(decoded.error_cm, 0.0)
        self.assertEqual(decoded.position_cm, 0.0)
        self.assertEqual(decoded.velocity_cm_s, 0.0)

    def test_reads_currently_available_serial_bytes(self):
        fake = FakeSerial()
        fake.received.extend(b"PING\r\n")
        link = MySerial("loop", serial_factory=lambda **kwargs: fake)
        link.open()
        self.assertEqual(link.receive_available(), b"PING\r\n")
        self.assertEqual(link.receive_available(), b"")


if __name__ == "__main__":
    unittest.main()
