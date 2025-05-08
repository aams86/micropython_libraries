# ble_ranger.py
import ubluetooth
import struct
import time
from ble_base import BLEManager, BLEService, BLECharacteristic
BLE_RANGER_SERVICE_UUID = "0bfc2787-e220-4b0f-ae98-13731add0000"
BLE_RANGER_TX_CHAR_UUID = "0bfc2787-e220-4b0f-ae98-13731add0001"
BLE_RANGER_RX_CHAR_UUID = "0bfc2787-e220-4b0f-ae98-13731add0002"

class BLERanger:
    def __init__(self, name="ble-ranger", tx_pwr = 4):
        self.ble_manager = BLEManager(name=name, tx_power=4)
        # Define a service
        service = BLEService(uuid=BLE_RANGER_SERVICE_UUID)
        
        # Define characteristics
        def on_write(conn_handle, char, value):
            self.write_handler(value.decode())
            #print(f"Write received on {char.uuid} from connection {conn_handle}. Value: {value.decode()}")
            

        char1 = BLECharacteristic(
            uuid=BLE_RANGER_RX_CHAR_UUID,
            flags=ubluetooth.FLAG_WRITE,
            write_callback=on_write,
        )

        char2 = BLECharacteristic(
            uuid=BLE_RANGER_TX_CHAR_UUID,
            flags=ubluetooth.FLAG_NOTIFY,
        )
        
        service.add_characteristic(char1)
        service.add_characteristic(char2)
        # Add the service to the BLE manager
        self.ble_manager.add_service(service)
        self.ble_manager.set_advertising_service(BLE_RANGER_SERVICE_UUID)

        self.ble_manager.advertising.start()
        
        self.channel_callbacks = dict()
    
    def write_handler(self, value):
        #print(f"received value: {value}")
        commands = value.split(";")
        for command in commands:
            if(len(command) > 0):
                channel = None
                data = None
                rcv = command.split(":")
                try:
                    channel = int(rcv[0])
                    data = rcv[1]
                except:
                    print("invalid channel type")
                    break
                try:
                    if channel in self.channel_callbacks:
                        self.channel_callbacks[channel](channel, data)
                    else:
                        print(f"unhandled write: {command}")
                except Exception as e:
                    print(f"failed to handle data: {e}")
                    break
    
    def register_disconnect(self, callback):
        self.ble_manager.register_disconnect_callback(callback)
        
    def register_connect(self, callback):
        self.ble_manager.register_connect_callback(callback)
    
    def register_channel(self, channel, callback):
        self.channel_callbacks[channel] = callback

def on_connect(arg):
    print("connected")

def on_disconnect(arg):
    print("disconnected")

def channel_callback(channel, data):
    print(f"data received:: channel: {channel} data: {data}")
def main():
    bleRanger = BLERanger("draw bot")

    bleRanger.register_connect(on_connect)
    bleRanger.register_disconnect(on_disconnect)

    bleRanger.register_channel(1, channel_callback)

    while True:
        time.sleep(1)
if __name__ == "__main__":
    main()
