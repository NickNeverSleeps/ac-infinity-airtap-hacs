from bleak.exc import BleakError

DOMAIN = "ac_infinity"

MANUFACTURER = "AC Infinity"

DEVICE_TIMEOUT = 30
UPDATE_SECONDS = 15

BLEAK_EXCEPTIONS = (AttributeError, BleakError, TimeoutError)

DEVICE_MODEL = {1: "Controller 67",
                6: "Airtap Series",
                7: "Controller 69",
                11: "Controller 69 Pro"}

FAMILY_E_MODELS = {7, 9, 11, 12}

# Temporary compatibility profile for the Airtap that advertises only its local
# name (``BLE_FAN``) and does not include the normal AC Infinity manufacturer
# payload.  Keep this deliberately limited to the reported device address: a
# local name alone is not a safe way to identify arbitrary BLE devices.
TEST_DEVICE_ADDRESS = "A4:C1:38:DC:7F:1F"
TEST_DEVICE_NAME = "BLE_FAN"
TEST_DEVICE_TYPE = 6
TEST_DEVICE_VERSION = 1
