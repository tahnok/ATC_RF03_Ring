"""
A python client for connecting to the Colmi R02 Smart ring
"""

import asyncio
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic


ADDRESS = "70:CB:0D:D0:34:1C"

UART_SERVICE_UUID = "6E40FFF0-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

DEVICE_INFO_UUID = "0000180A-0000-1000-8000-00805F9B34FB"
DEVICE_HW_UUID = "00002A27-0000-1000-8000-00805F9B34FB"
DEVICE_FW_UUID = "00002A26-0000-1000-8000-00805F9B34FB"

CMD_REAL_TIME_HEART_RATE = 30 # 0x1E
CMD_START_HEART_RATE = 105 # 0x69
CMD_STOP_HEART_RATE = 106 # 0x6A
CMD_BATTERY = 3
CMD_BLINK_TWICE = 16 # 0x10

def make_packet(command_key: int, sub_data: bytearray|None = None) -> bytearray:
    packet = bytearray(16)
    packet[0] = command_key

    if sub_data:
        assert len(sub_data) <= 14
        for i in range(len(sub_data)):
            packet[i + 1] = sub_data[i]
    
    packet[-1] = crc(packet)

    return packet

def crc(packet: bytearray) -> int:
    return sum(packet) & 255

START_HEART_RATE_PACKET = make_packet(CMD_START_HEART_RATE, bytearray(b'\x01\x00')) # why is this backwards?
CONTINUE_HEART_RATE_PACKET = make_packet(CMD_REAL_TIME_HEART_RATE, bytearray(b'3'))
STOP_HEART_RATE_PACKET = make_packet(CMD_STOP_HEART_RATE, bytearray(b'\x01\x00\x00'))

START_SPO2_PACKET = make_packet(CMD_START_HEART_RATE, bytearray(b'\x03\x25'))
STOP_SPO2_PACKET = make_packet(CMD_STOP_HEART_RATE, bytearray(b'\x03\x00\x00'))

BATTERY_PACKET = make_packet(CMD_BATTERY)
BLINK_TWICE_PACKET = make_packet(CMD_BLINK_TWICE)

FLAG_ERROR_MASK = 127

def parse_response(packet: bytearray) -> dict[str, int]:
    if packet[0] > 127: # high bit is set
        assert False, f"Packet has error bit set {packet}"

    packet_type = packet[0]
    if packet_type == CMD_START_HEART_RATE:
        return {
                "type": packet[1],
                "errCode": packet[2],
                "value": packet[3],
                }
    elif packet_type == CMD_STOP_HEART_RATE:
        return {}
    elif packet_type == CMD_BATTERY:
        return {
                "batteryLevel": packet[1],
                "charging": bool(packet[2]),
                }
    else:
        assert False, f"unknown packet type {packet}"

async def get_heart_rate(client, rx_char) -> None:
    await client.write_gatt_char(rx_char, START_HEART_RATE_PACKET, response=False)
    print("wrote HR reading packet, waiting...")

    for _ in range(16):
        await asyncio.sleep(2)
        await client.write_gatt_char(rx_char, CONTINUE_HEART_RATE_PACKET, response=False)
        print(".")

    await client.write_gatt_char(rx_char, STOP_HEART_RATE_PACKET, response=False)


async def get_spo2(client, rx_char) -> None:
    await client.write_gatt_char(rx_char, START_SPO2_PACKET, response=False)
    print("wrote SPO2 reading packet, waiting...")

    for _ in range(16):
        await asyncio.sleep(2)
        print(".")

    await client.write_gatt_char(rx_char, STOP_SPO2_PACKET, response=False)

async def main():
    print("Connecting...")

    def handle_rx(_: BleakGATTCharacteristic, data: bytearray):
        print("received:", data)
        print(parse_response(data))

    async with BleakClient(ADDRESS) as client:
        print("Connected")

        device_info = client.services.get_service(DEVICE_INFO_UUID)
        assert device_info

        hw_info = device_info.get_characteristic(DEVICE_HW_UUID)
        assert hw_info
        x = await client.read_gatt_char(hw_info)
        print(x)

        fw_info = device_info.get_characteristic(DEVICE_FW_UUID)
        assert fw_info
        x = await client.read_gatt_char(fw_info)
        print(x)

        await client.start_notify(UART_TX_CHAR_UUID, handle_rx)

        nus = client.services.get_service(UART_SERVICE_UUID)
        assert nus
        rx_char = nus.get_characteristic(UART_RX_CHAR_UUID)
        assert rx_char

        print("Trying to get battery")
        await client.write_gatt_char(rx_char, BATTERY_PACKET, response=False)
        await asyncio.sleep(5)


        print("Getting heart rate")
        await get_heart_rate(client, rx_char)

        print("Getting SpO2")
        await get_spo2(client, rx_char)




if __name__ == '__main__':
    asyncio.run(main())


