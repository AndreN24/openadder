import unittest
from unittest import mock

from openadder import device as d
from openadder import protocol as p


class FakeHid:
    """A hid.device() that answers feature reports from a list of status bytes."""

    def __init__(self, statuses=(0x02,), args=b"", echo=True):
        self.statuses = list(statuses)
        self.args = args
        self.echo = echo
        self.sent = []
        self.closed = False

    def send_feature_report(self, data):
        self.sent.append(bytes(data))

    def get_feature_report(self, report_id, length):
        req = bytearray(self.sent[-1][1:])
        req[0] = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if not self.echo:
            req[7] ^= 0x01
        req[8:8 + len(self.args)] = self.args
        return list(b"\x00" + bytes(req))

    def open_path(self, path):
        pass

    def close(self):
        self.closed = True


class Transport(unittest.TestCase):
    def setUp(self):
        sleep = mock.patch.object(d.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_reads_values(self):
        dev = d.DeathAdderV2(FakeHid(args=bytes([1, 2])))
        self.assertEqual(dev.firmware(), "1.02")
        dev = d.DeathAdderV2(FakeHid(args=bytes([1, 0x03, 0x20, 0x03, 0x20])))
        self.assertEqual(dev.dpi(), (800, 800))

    def test_busy_is_retried(self):
        hid = FakeHid(statuses=[0x01, 0x01, 0x02], args=bytes([3]))
        self.assertEqual(d.DeathAdderV2(hid).device_mode(), 3)
        self.assertEqual(len(hid.sent), 1)

    def test_failure_and_wrong_answer_raise(self):
        with self.assertRaisesRegex(d.DeviceError, "not supported"):
            d.DeathAdderV2(FakeHid(statuses=[0x05])).set_poll_rate(500)
        with self.assertRaisesRegex(d.DeviceError, "different command"):
            d.DeathAdderV2(FakeHid(echo=False)).firmware()

    def test_writes_send_the_protocol_reports(self):
        hid = FakeHid()
        dev = d.DeathAdderV2(hid)
        dev.set_dpi(1600)
        dev.set_effect(p.LOGO_LED, "breathing", (1, 2, 3))
        dev.set_device_mode(p.DRIVER_MODE)
        self.assertEqual(hid.sent[0][1:], p.set_dpi(1600, 1600))
        self.assertEqual(hid.sent[1][1:], p.effect_breathing(p.LOGO_LED, (1, 2, 3)))
        self.assertEqual(hid.sent[2][1:], p.set_device_mode(p.DRIVER_MODE))
        with self.assertRaises(ValueError):
            dev.set_effect(p.LOGO_LED, "disco")

    def test_open(self):
        with mock.patch.object(d.hid, "enumerate", return_value=[]):
            with self.assertRaisesRegex(d.DeviceError, "not found"):
                d.DeathAdderV2.open()
        infos = [{"interface_number": 1, "path": b"one"}, {"interface_number": 0, "path": b"zero"}]
        good = FakeHid(args=bytes([1, 2]))
        with mock.patch.object(d.hid, "enumerate", return_value=infos), \
                mock.patch.object(d.hid, "device", return_value=good):
            self.assertEqual(d.DeathAdderV2.open().firmware(), "1.02")
        bad = FakeHid(statuses=[0x03])
        with mock.patch.object(d.hid, "enumerate", return_value=infos), \
                mock.patch.object(d.hid, "device", return_value=bad):
            with self.assertRaisesRegex(d.DeviceError, "did not answer"):
                d.DeathAdderV2.open()
        self.assertTrue(bad.closed)


class Listener(unittest.TestCase):
    def test_press_and_release_events(self):
        reports = [bytes([0x04, 0x20, 0x22] + [0] * 13), bytes([0x04, 0x20, 0x50] + [0] * 13),
                   bytes([0x05, 0x02, 0x03]), [], bytes([0x04] + [0] * 15)]
        events = []
        listener = d.ButtonListener(lambda b, pressed: events.append((b, pressed)))
        h = mock.Mock()
        h.read.side_effect = reports + [OSError("unplugged")]
        listener._loop(h)
        self.assertEqual(events, [("dpi_up", True), ("profile", True),
                                  ("dpi_up", False), ("profile", False)])
        h.close.assert_called_once()

    def test_buttons_held_when_unplugged_are_released(self):
        events = []
        listener = d.ButtonListener(lambda b, pressed: events.append((b, pressed)))
        h = mock.Mock()
        h.read.side_effect = [bytes([0x04, 0x21] + [0] * 14), OSError("unplugged")]
        listener._loop(h)
        self.assertEqual(events, [("dpi_down", True), ("dpi_down", False)])


    def test_start_opens_only_the_report4_collections(self):
        infos = [{"interface_number": 0, "usage_page": 1, "usage": 2, "path": b"mouse"},
                 {"interface_number": 1, "usage_page": 1, "usage": 6, "path": b"keyboard"},
                 {"interface_number": 1, "usage_page": 1, "usage": 0, "path": b"vendor-a"},
                 {"interface_number": 1, "usage_page": 1, "usage": 0, "path": b"vendor-b"}]
        opened = []

        class Handle:
            def open_path(self, path):
                if path == b"vendor-b":
                    raise OSError("busy")
                opened.append(path)

            def read(self, size, timeout):
                return []

            def close(self):
                pass

        listener = d.ButtonListener(lambda *a: None)
        with mock.patch.object(d.hid, "enumerate", return_value=infos),                 mock.patch.object(d.hid, "device", side_effect=Handle):
            listener.start()
        self.assertEqual(opened, [b"vendor-a"])
        self.assertEqual(len(listener._threads), 1)
        listener.stop()
        self.assertEqual(listener._threads, [])


if __name__ == "__main__":
    unittest.main()
