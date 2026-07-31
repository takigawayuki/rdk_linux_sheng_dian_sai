import unittest

from project.Driver.buzzer import Buzzer, BuzzerConfig


class FakeGPIO:
    BCM = "BCM"
    BOARD = "BOARD"
    OUT = "OUT"
    HIGH = 1
    LOW = 0

    def __init__(self):
        self.calls = []

    def setwarnings(self, enabled):
        self.calls.append(("setwarnings", enabled))

    def setmode(self, mode):
        self.calls.append(("setmode", mode))

    def setup(self, pin, direction, initial=None):
        self.calls.append(("setup", pin, direction, initial))

    def output(self, pin, level):
        self.calls.append(("output", pin, level))

    def cleanup(self, pin):
        self.calls.append(("cleanup", pin))


class BuzzerTests(unittest.TestCase):
    def test_active_low_levels_and_cleanup(self):
        gpio = FakeGPIO()
        buzzer = Buzzer(gpio_module=gpio).open()
        buzzer.on()
        buzzer.off()
        buzzer.close()

        self.assertIn(("setmode", gpio.BCM), gpio.calls)
        self.assertIn(("setup", 16, gpio.OUT, gpio.HIGH), gpio.calls)
        self.assertIn(("output", 16, gpio.LOW), gpio.calls)
        self.assertEqual(gpio.calls[-2:], [("output", 16, gpio.HIGH), ("cleanup", 16)])
        self.assertFalse(buzzer.is_open)

    def test_context_manager_turns_buzzer_off_after_error(self):
        gpio = FakeGPIO()
        with self.assertRaisesRegex(RuntimeError, "test error"):
            with Buzzer(gpio_module=gpio) as buzzer:
                buzzer.on()
                raise RuntimeError("test error")
        self.assertEqual(gpio.calls[-2:], [("output", 16, gpio.HIGH), ("cleanup", 16)])

    def test_configuration_validation(self):
        with self.assertRaises(ValueError):
            BuzzerConfig(pin=-1).validate()
        with self.assertRaises(ValueError):
            BuzzerConfig(numbering="INVALID").validate()


if __name__ == "__main__":
    unittest.main()
