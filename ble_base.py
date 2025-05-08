import ubluetooth
import time


class Advertising:
    def __init__(self, ble, name):
        """
        Handles BLE advertising.
        """
        self.ble = ble
        self.name = name
        self.service_uuids = []
        
    def add_service_uuid(self, uuid):
        """
        Add a custom service UUID to the advertisement payload.
        """
        self.service_uuids.append(ubluetooth.UUID(uuid))

    def _build_adv_payload(self):
        """
        Build the advertising payload with service UUIDs only.
        """
        payload = bytearray()
        payload += bytearray([2, 0x01, 0x06])  # Flags: General discoverable, BR/EDR not supported

        # Add Service UUIDs (128-bit)
        for service_uuid in self.service_uuids:
            uuid_bytes = bytes(service_uuid)
            payload += bytearray([len(uuid_bytes) + 1, 0x07]) + uuid_bytes

        return payload

    def _build_scan_response(self):
        """
        Build the scan response payload with the device name.
        """
        name_bytes = self.name.encode("utf-8")
        payload = bytearray()
        payload += bytearray([len(name_bytes) + 1, 0x09]) + name_bytes  # Complete Local Name
        return payload

    def start(self, interval=100):
        """
        Start BLE advertising with the advertising and scan response payloads.
        """
        adv_payload = self._build_adv_payload()
        scan_response = self._build_scan_response()

        # Start advertising with scan response
        self.ble.gap_advertise(interval, adv_payload, resp_data=scan_response)
        print(f"Advertising started with service UUIDs and name '{self.name}' in scan response.")


    def stop(self):
        """
        Stop BLE advertising.
        """
        self.ble.gap_advertise(None)
        print("Advertising stopped")


class BLECharacteristic:
    def __init__(self, uuid, flags, write_callback=None):
        self.uuid = ubluetooth.UUID(uuid)
        self.flags = flags
        self.write_callback = write_callback
        self.handle = None
        self.value = b""

    def set_value(self, value):
        self.value = value

    def get_value(self):
        return self.value


class BLEService:
    def __init__(self, uuid):
        self.uuid = ubluetooth.UUID(uuid)
        self.characteristics = []

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)


class BLEManager:
    def __init__(self, name="PicoW", tx_power=0):
        self.ble = ubluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq_handler)

        self.advertising = Advertising(self.ble, name)
        self.tx_power = tx_power
        self.services = []
        self.characteristic_handles = {}  # Map handle -> characteristic
        self.connections = set()
        
        self.connect_callback = None
        self.disconnect_callback = None

        # Configure TX power
        self.set_tx_power(self.tx_power)
        
    def set_advertising_service(self, uuid):
        self.advertising.add_service_uuid(uuid)
    
    def register_connect_callback(self, callback):
        """
        Register a callback for central device connection events.
        """
        self.connect_callback = callback

    def register_disconnect_callback(self, callback):
        """
        Register a callback for central device disconnection events.
        """
        self.disconnect_callback = callback

    def _irq_handler(self, event, data):
        if event == 1:  # _IRQ_CENTRAL_CONNECT
            conn_handle, *_ = data
            self.connections.add(conn_handle)
            print(f"Central connected: {conn_handle}")
            if self.connect_callback:
                self.connect_callback(conn_handle)

        elif event == 2:  # _IRQ_CENTRAL_DISCONNECT
            conn_handle, *_ = data
            self.connections.discard(conn_handle)
            print(f"Central disconnected: {conn_handle}")
            if self.disconnect_callback:
                self.disconnect_callback(conn_handle)
            self.advertising.start()  # Restart advertising

        elif event == 3:  # _IRQ_GATTS_WRITE
            conn_handle, attr_handle = data
            #print(f"data rcv:{data}, {event}")
            value = self.ble.gatts_read(attr_handle)
            print(value.decode())
            if attr_handle in self.characteristic_handles:
                char = self.characteristic_handles[attr_handle]
                if char.write_callback:
                    char.write_callback(conn_handle, char, value)

    def set_tx_power(self, power):
        """
        Set the transmit power for the BLE radio.
        """
        try:
            self.ble.config(txpower=power)
            print(f"Transmit power set to {power} dBm")
        except Exception as e:
            print(f"Error setting TX power: {e}")

    def add_service(self, service):
        """
        Add a BLE service.
        """
        char_defs = [(char.uuid, char.flags) for char in service.characteristics]
        self.services.append(service)

        # Register the service
        service_def = (service.uuid, char_defs)
        handles = self.ble.gatts_register_services([service_def])

        # Assign handles to characteristics
        for char, handle in zip(service.characteristics, handles[0]):
            char.handle = handle
            self.characteristic_handles[handle] = char
        print(f"Service {service.uuid} added with handles: {handles}")

    def notify(self, char_uuid, value):
        """
        Notify all connected centrals of a characteristic value change.
        """
        for service in self.services:
            for char in service.characteristics:
                if char.uuid == ubluetooth.UUID(char_uuid):
                    char.set_value(value)
                    for conn_handle in self.connections:
                        self.ble.gatts_notify(conn_handle, char.handle, value)
                    print(f"Notification sent for {char_uuid} with value: {value}")
                    return
        print(f"Characteristic {char_uuid} not found.")

    def shutdown(self):
        """
        Shut down BLE.
        """
        self.connections.clear()
        self.advertising.stop()
        self.ble.active(False)
        print("BLE shut down")


# Example Usage
if __name__ == "__main__":
    ble_manager = BLEManager(name="PicoW-BLE", tx_power=4)

    # Define a service
    service = BLEService(uuid="12345678-1234-5678-1234-56789abcdef0")

    # Define characteristics
    def on_write(conn_handle, char, value):
        value = value.decode()
        print(f"Write received on {char.uuid} from connection {conn_handle}. Value: {value}")

    char1 = BLECharacteristic(
        uuid="12345678-1234-5678-1234-56789abcdef1",
        flags=ubluetooth.FLAG_READ | ubluetooth.FLAG_WRITE,
        write_callback=on_write,
    )

    char2 = BLECharacteristic(
        uuid="12345678-1234-5678-1234-56789abcdef2",
        flags=ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY,
    )

    # Add characteristics to the service
    service.add_characteristic(char1)
    service.add_characteristic(char2)

    # Add the service to the BLE manager
    ble_manager.add_service(service)

    try:
        ble_manager.advertising.start()

        # Simulate sending notifications
        while True:
            time.sleep(5)
            ble_manager.notify("12345678-1234-5678-1234-56789abcdef2", b"Hello BLE!")

    except KeyboardInterrupt:
        ble_manager.shutdown()

