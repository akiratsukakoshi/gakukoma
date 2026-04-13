import board
import busio
import adafruit_pca9685
print("Initializing I2C...")
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    print("I2C initialized.")
    pca = adafruit_pca9685.PCA9685(i2c)
    print("PCA9685 initialized.")
    pca.deinit()
    print("PCA9685 deinitialized.")
except Exception as e:
    print(f"Error during initialization: {e}")
