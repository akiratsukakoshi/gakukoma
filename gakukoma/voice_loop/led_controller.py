from gpiozero import RGBLED
import time

class LedController:
    def __init__(self):
        # Hardware configuration for RGB LED (GPIO BCM numbering)
        # Red: GPIO17, Green: GPIO27, Blue: GPIO22
        # Common cathode is default (active_high=True)
        self.led = RGBLED(red=17, green=27, blue=22)

    def set_state(self, state: str):
        self.led.off()  # Stop current sequence before switching
        
        if state == "idle":
            # Blue blinking: on=0.5s / off=0.5s (1s cycle)
            self.led.blink(on_time=0.5, off_time=0.5,
                           on_color=(0, 0, 1), off_color=(0, 0, 0),
                           background=True)
        elif state == "listening":
            # Green static on
            self.led.color = (0, 1, 0)
        elif state == "thinking":
            # Yellow (R+G) blinking: on=0.15s / off=0.15s (0.3s cycle)
            self.led.blink(on_time=0.15, off_time=0.15,
                           on_color=(1, 1, 0), off_color=(0, 0, 0),
                           background=True)
        elif state == "speaking":
            # Red static on
            self.led.color = (1, 0, 0)
        # For unknown states, LED remains off due to the initial self.led.off()

    def close(self):
        self.led.off()
        self.led.close()
