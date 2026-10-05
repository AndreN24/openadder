import unittest

from openadder import protocol as p


class ReportLayout(unittest.TestCase):
    def test_header_and_crc(self):
        r = p.get_firmware()
        self.assertEqual(len(r), 90)
        self.assertEqual(r[:8], bytes([0x00, 0x3F, 0, 0, 0, 0x02, 0x00, 0x81]))
        self.assertEqual(r[88], 0x02 ^ 0x00 ^ 0x81)

    def test_build_rejects_long_arguments(self):
        with self.assertRaises(ValueError):
            p.build(0, 0, 0, bytes(81))

    def test_set_dpi(self):
        r = p.set_dpi(1600, 800)
        self.assertEqual(r[5:8], bytes([0x07, 0x04, 0x05]))
        self.assertEqual(r[8:15], bytes([0x01, 0x06, 0x40, 0x03, 0x20, 0, 0]))

    def test_set_dpi_clamps(self):
        r = p.set_dpi(50, 99999)
        self.assertEqual(r[9:13], bytes([0x00, 0x64, 0x4E, 0x20]))  # 100, 20000

    def test_get_dpi_and_parse(self):
        self.assertEqual(p.get_dpi()[6:9], bytes([0x04, 0x85, 0x00]))
        resp = p.parse(bytes([0x02]) + p.set_dpi(1600, 800)[1:])
        self.assertEqual(p.parse_dpi(resp), (1600, 800))

    def test_dpi_stages_round_trip(self):
        stages = [(400, 400), (800, 800), (1600, 1600)]
        r = p.set_dpi_stages(stages, 2)
        self.assertEqual(r[5], 3 + 3 * 7)
        self.assertEqual(r[8:11], bytes([0x00, 2, 3]))
        self.assertEqual(r[11:18], bytes([1, 0x01, 0x90, 0x01, 0x90, 0, 0]))
        resp = p.parse(bytes([0x02]) + r[1:])
        self.assertEqual(p.parse_dpi_stages(resp), (stages, 2))
        self.assertEqual(p.get_dpi_stages()[6:8], bytes([0x04, 0x86]))

    def test_dpi_stages_limits(self):
        with self.assertRaises(ValueError):
            p.set_dpi_stages([], 1)
        with self.assertRaises(ValueError):
            p.set_dpi_stages([(800, 800)] * 6, 1)
        with self.assertRaises(ValueError):
            p.set_dpi_stages([(800, 800)], 2)

    def test_poll_rate(self):
        self.assertEqual(p.set_poll_rate(500)[8], 0x02)
        self.assertEqual(p.get_poll_rate()[6:8], bytes([0x00, 0x85]))
        self.assertEqual(p.parse_poll_rate(p.parse(bytes([0x02]) + p.set_poll_rate(125)[1:])), 125)
        with self.assertRaises(ValueError):
            p.set_poll_rate(250)

    def test_effects(self):
        static = p.effect_static(p.LOGO_LED, (10, 20, 30))
        self.assertEqual(static[5:8], bytes([0x09, 0x0F, 0x02]))
        self.assertEqual(static[8:17], bytes([0x01, 0x04, 0x01, 0, 0, 0x01, 10, 20, 30]))
        self.assertEqual(p.effect_breathing(1, (1, 2, 3))[8:17], bytes([1, 1, 2, 1, 0, 1, 1, 2, 3]))
        self.assertEqual(p.effect_reactive(1, (1, 2, 3), 9)[8:17], bytes([1, 1, 5, 0, 4, 1, 1, 2, 3]))
        self.assertEqual(p.effect_spectrum(4)[5:11], bytes([0x06, 0x0F, 0x02, 0x01, 0x04, 0x03]))
        self.assertEqual(p.effect_off(4)[5:11], bytes([0x06, 0x0F, 0x02, 0x01, 0x04, 0x00]))

    def test_brightness(self):
        self.assertEqual(p.set_brightness(p.SCROLL_WHEEL_LED, 300)[8:11], bytes([0x01, 0x01, 255]))
        self.assertEqual(p.get_brightness(4)[6:10], bytes([0x0F, 0x84, 0x01, 0x04]))
        resp = p.parse(bytes([0x02]) + p.set_brightness(4, 99)[1:])
        self.assertEqual(p.parse_brightness(resp), 99)

    def test_parse(self):
        with self.assertRaises(ValueError):
            p.parse(b"\x00" * 10)
        resp = p.parse(bytes([0x05]) + p.get_firmware()[1:])
        self.assertFalse(resp.ok)
        self.assertEqual(resp.status_name, "not supported")
        self.assertEqual(p.parse(bytes([0x09]) + bytes(89)).status_name, "unknown 0x09")


class DriverMode(unittest.TestCase):
    def test_device_mode_reports(self):
        self.assertEqual(p.set_device_mode(p.DRIVER_MODE)[6:10], bytes([0x00, 0x04, 0x03, 0x00]))
        self.assertEqual(p.get_device_mode()[6:8], bytes([0x00, 0x84]))
        with self.assertRaises(ValueError):
            p.set_device_mode(0x02)

    def test_report4(self):
        self.assertEqual(p.parse_report4(bytes([0x04, 0x20, 0x22] + [0] * 13)), {"dpi_up"})
        self.assertEqual(p.parse_report4(bytes([0x04, 0x50] + [0] * 14)), {"profile"})
        self.assertEqual(p.parse_report4(bytes([0x04] + [0] * 15)), set())
        self.assertIsNone(p.parse_report4(bytes([0x05, 0x02, 0x03, 0x20])))
        self.assertIsNone(p.parse_report4(b""))


if __name__ == "__main__":
    unittest.main()
