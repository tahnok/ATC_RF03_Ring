"""
A python client for connecting to the Colmi R02 Smart ring


TODO:
    - fetch "steps"
    - get "Stress"
    - make nicer methods for getting data from callback
    - "scan" mode instead of hard coded address
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
CMD_GET_STEP_SOMEDAY = 67 #0x43

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

GET_TODAY_STEPS_PACKET = make_packet(CMD_GET_STEP_SOMEDAY, bytearray(b'\x00\x0F\x00\x5F\x01'))

def parse_sport_detail_packet(packet: bytearray):
    assert len(packet) == 16
    assert packet[0] == CMD_GET_STEP_SOMEDAY
    assert packet[1] != 255, "Packet request malformed"
    offset = 0
    new_calorie_protocol = False

    if packet[1] == 240:
        if packet[3] == 1:
            new_calorie_protocol = True
        offset = 1
        #
    else:
        #year
        ...

async def send_packet(client: BleakClient, rx_char, packet: bytearray) -> None:
    await client.write_gatt_char(rx_char, packet, response=False)


def parse_heart_rate(packet: bytearray) -> dict[str, int]:
    return {
            "type": packet[1],
            "error_code": packet[2],
            "value": packet[3],
            }

def empty_parse(packet: bytearray) -> None:
    """Used for commands that we expect a response, but there's nothing in the response"""
    return None

def parse_battery(packet: bytearray) -> dict[str, int]:
    r"""
    example: bytearray(b'\x03@\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00C')
    """
    return {
            "battery_level": packet[1],
            "charging": bool(packet[2]),
            }

def log_packet(packet: bytearray) -> None:
    print("received: ", packet)

# these are commands that we expect to have a response returned for
COMMAND_HANDLERS = {
        CMD_BATTERY: parse_battery,
        CMD_START_HEART_RATE: parse_heart_rate,
        CMD_STOP_HEART_RATE: empty_parse,
        CMD_GET_STEP_SOMEDAY: log_packet,
    }

async def get_heart_rate(client, rx_char, queues: dict[int, asyncio.Queue]) -> None:
    await send_packet(client, rx_char, START_HEART_RATE_PACKET)
    print("wrote HR reading packet, waiting...")

    valid_hr = []
    tries = 0
    while len(valid_hr) < 6 and tries < 20:
        try:
            data = await asyncio.wait_for(queues[CMD_START_HEART_RATE].get(), 2)
            if data["error_code"] == 1:
                print("No heart rate detected, probably not on")
                break
            if data["value"] != 0:
                valid_hr.append(data["value"])
        except TimeoutError:
            print(".")
            tries += 1
            await client.write_gatt_char(rx_char, CONTINUE_HEART_RATE_PACKET, response=False)

    await client.write_gatt_char(rx_char, STOP_HEART_RATE_PACKET, response=False)
    print(valid_hr)


async def get_spo2(client, rx_char) -> None:
    await client.write_gatt_char(rx_char, START_SPO2_PACKET, response=False)
    print("wrote SPO2 reading packet, waiting...")

    for _ in range(16):
        await asyncio.sleep(2)
        print(".")

    await client.write_gatt_char(rx_char, STOP_SPO2_PACKET, response=False)

async def get_battery(client, rx_char, queues: dict[int, asyncio.Queue]):
    await send_packet(client, rx_char, BATTERY_PACKET)
    return await queues[CMD_BATTERY].get()


async def get_device_info(client: BleakClient):
    data = {}
    device_info_service = client.services.get_service(DEVICE_INFO_UUID)
    assert device_info_service

    hw_info_char = device_info_service.get_characteristic(DEVICE_HW_UUID)
    assert hw_info_char
    hw_version = await client.read_gatt_char(hw_info_char)
    data["hw_version"] = hw_version.decode("utf-8")

    fw_info_char = device_info_service.get_characteristic(DEVICE_FW_UUID)
    assert fw_info_char
    fw_version = await client.read_gatt_char(fw_info_char)
    data["fw_version"] = fw_version.decode("utf-8")

    return data


async def main():
    print("Connecting...")

    queues = { cmd: asyncio.Queue() for cmd in COMMAND_HANDLERS.keys() }

    def handle_rx(_: BleakGATTCharacteristic, packet: bytearray):
        packet_type = packet[0]
        assert packet_type < 127, f"Packet has error bit set {packet}"

        if packet_type in COMMAND_HANDLERS:
            queues[packet_type].put_nowait(COMMAND_HANDLERS[packet_type](packet))
        else:
            print("Did not expect this packet")

    async with BleakClient(ADDRESS) as client:
        print("Connected")
        print("Device info: ", await get_device_info(client))

        nus = client.services.get_service(UART_SERVICE_UUID)
        assert nus
        rx_char = nus.get_characteristic(UART_RX_CHAR_UUID)
        assert rx_char

        await client.start_notify(UART_TX_CHAR_UUID, handle_rx)

        print("battery:", await get_battery(client, rx_char, queues))

        await get_heart_rate(client, rx_char, queues)

        await client.write_gatt_char(rx_char, GET_TODAY_STEPS_PACKET, response=False)
        await asyncio.sleep(2)



if __name__ == '__main__':
    asyncio.run(main())


