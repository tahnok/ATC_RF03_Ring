import asyncio
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic


ADDRESS = "70:CB:0D:D0:34:1C"

UART_SERVICE_UUID = "6E40FFF0-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

CMD_REAL_TIME_HEART_RATE = 30
CMD_START_HEART_RATE = 105
CMD_STOP_HEART_RATE = 106

def make_packet(command_key: int, sub_data: bytearray) -> bytearray:
    packet = bytearray(15)
    packet[0] = command_key

    assert len(sub_data) <= 14
    packet[1:len(sub_data)] = sub_data
    
    packet[-1] = crc(packet)

    return packet

def crc(packet: bytearray) -> int:
    return sum(packet) & 255

START_HEART_RATE_PACKET = make_packet(CMD_START_HEART_RATE, bytearray(b'\x00\x01'))
CONTINUE_HEART_RATE_PACKET = make_packet(CMD_REAL_TIME_HEART_RATE, bytearray(b'3'))
STOP_HEART_RATE_PACKET = make_packet(CMD_STOP_HEART_RATE, bytearray(b'\x01\x00\x00'))

FLAG_ERROR_MASK = 127

def parse_response(packet: bytearray) -> dict[str, int]:
    if packet[0] > 127: # high bit is set
        assert False, f"Packet has error bit set {packet}"

    if packet[0] == CMD_START_HEART_RATE:
        return {
                "type": packet[1],
                "errCode": packet[2],
                "value": packet[3],
                }
    elif packet[0] == CMD_STOP_HEART_RATE:
        return {}
    else:
        assert False, f"unknown packet type {packet}"


async def main():
    print("Connecting...")

    def handle_rx(_: BleakGATTCharacteristic, data: bytearray):
        print("received:", data)
        print(parse_response(data))

    async with BleakClient(ADDRESS) as client:
        print("Connected")

        await client.start_notify(UART_TX_CHAR_UUID, handle_rx)
        nus = client.services.get_service(UART_SERVICE_UUID)
        assert nus
        rx_char = nus.get_characteristic(UART_RX_CHAR_UUID)
        assert rx_char
        print(rx_char.max_write_without_response_size)

        await client.write_gatt_char(rx_char, START_HEART_RATE_PACKET, response=False)
        print("wrote packet, waiting...")

        for _ in range(40):
            await asyncio.sleep(2)
            await client.write_gatt_char(rx_char, CONTINUE_HEART_RATE_PACKET, response=False)
            print(".")

        await client.write_gatt_char(rx_char, STOP_HEART_RATE_PACKET, response=False)


def scratch():
    print(parse_response(bytearray(b'i\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00i')))
    print(parse_response(bytearray(b'i\x00\x00F\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xaf')))

if __name__ == '__main__':
    asyncio.run(main())


