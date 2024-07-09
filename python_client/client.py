import asyncio
from bleak import BleakScanner, BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic


ADDRESS = "70:CB:0D:D0:34:1C"
MODEL_NBR_UUID = "2A24"


UART_SERVICE_UUID = "6E40FFF0-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

CMD_REAL_TIME_HEART_RATE = 30
CMD_START_HEART_RATE = 105;

def make_packet(command_key: int, sub_data: bytearray) -> bytearray:
    packet = bytearray(15)
    packet[0] = command_key

    assert len(sub_data) <= 14
    packet[1:len(sub_data)] = sub_data
    
    packet[-1] = crc(packet)

    return packet

def crc(packet: bytearray) -> int:
    return sum(packet) & 255

async def main():
    print("connecting")

    def handle_rx(_: BleakGATTCharacteristic, data: bytearray):
        print("received:", data)

    async with BleakClient(ADDRESS) as client:
        print("Connected")

        await client.start_notify(UART_TX_CHAR_UUID, handle_rx)
        nus = client.services.get_service(UART_SERVICE_UUID)
        rx_char = nus.get_characteristic(UART_RX_CHAR_UUID)

        packet = make_packet(CMD_START_HEART_RATE, bytearray(b'\x00\x01'))
        await client.write_gatt_char(rx_char, packet, response=False)
        print("wrote packet, waiting...")

        await asyncio.sleep(2)
        packet = make_packet(CMD_REAL_TIME_HEART_RATE, bytearray(b'3'))
        await client.write_gatt_char(rx_char, packet, response=False)

        await asyncio.sleep(20)


if __name__ == '__main__':
    asyncio.run(main())


