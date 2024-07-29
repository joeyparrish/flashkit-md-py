# FlashKit MD Python Client
#
# Copyright (C) 2024 Joey Parrish
#
# Derived from https://github.com/krikzz/flashkit/, also under GPLv3
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


import serial
import serial.tools.list_ports

from typing import Optional

# The original C# version used SerialPort() without a baud rate.  Microsoft
# defaults to 9600 8N1 in that case, so we do the same here, but we do it
# explicitly.
DEFAULT_BAUD_RATE = 9600
DEFAULT_DATA_BITS = serial.EIGHTBITS
DEFAULT_PARITY    = serial.PARITY_NONE
DEFAULT_STOP_BITS = serial.STOPBITS_ONE

# Constants below are taken from
# https://github.com/krikzz/flashkit/blob/master/flashkit-md/flashkit-md/Device.cs
# I have been unable to determine the origin ofssome of their names, so I have
# left them as they originally were.  This is a direct port from C# GUI to
# command-line Python.

# Command enum
CMD_ADDR  = 0
CMD_LEN   = 1
CMD_RD    = 2
CMD_WR    = 3
CMD_RY    = 4
CMD_DELAY = 5

# Command parameter bits
PAR_MODE8  =  16
PAR_DEV_ID =  32
PAR_SINGE  =  64
PAR_INC    = 128

IO_BLOCK_SIZE = 0x10000

# The literal bytes 'Q', 'R', 'Y', as words
CFI_EXPECTED_DATA = b'\x00\x51\x00\x52\x00\x59'

# NOTE: Krikzz Flash Cart MD uses a M29W320ET chip.
# Weird sequences of writes are commands from table 4 at the end of section 4:
# https://www.digikey.com/en/htmldatasheets/production/258014/0/0/1/m29w320db-m29w320dt
# These families of chip appear to be compatible with the official Krikzz carts:
#  - S29 series from Cypress / Infineon
#  - IS29 series from ISSI
# These are NOT compatible:
#  - MX29 series from Macronix (missing bypass mode)
#  - AS29 series from Alliance Memory (missing bypass mode)


class FlashKitNotFoundException(Exception):
  def __init__(self, device_path: Optional[str] = None) -> None:
    if device_path:
      message = 'FlashKit MD not found at {}'.format(device_path)
    else:
      message = 'FlashKit MD not found on any serial port!'
    super().__init__(message)


class FlashChipNotFoundException(Exception):
  def __init__(self) -> None:
    message = 'CFI failed, flash not detected!'
    super().__init__(message)


class FlashKitDevice(object):
  device_path: str
  serial: serial.Serial

  def __init__(self, device_path: Optional[str] = None):
    if device_path:
      self.__connect(device_path)

    else:
      for comport_description in serial.tools.list_ports.comports():
        device_path = comport_description[0]
        try:
          self.__connect(device_path)
          return
        except FlashKitNotFoundException:
          # This wasn't it. Try the next one.
          pass

      # None of them worked, so raise a general exception without a path.
      raise FlashKitNotFoundException()

  def __connect(self, device_path: str) -> None:
    self.device_path = device_path
    self.serial = serial.Serial(
        port=self.device_path,
        baudrate=DEFAULT_BAUD_RATE, bytesize=DEFAULT_DATA_BITS,
        parity=DEFAULT_PARITY, stopbits=DEFAULT_STOP_BITS)
    self.serial.timeout = 0.2  # seconds
    self.serial.write_timeout = 0.2  # seconds

    # Get the FlashKit programmer's device ID.
    id = self.__getID()
    if (id & 0xff) == (id >> 8) and id != 0:
      # A valid ID.
      self.id = '{:02X}'.format(id)  # id in hex
      self.serial.timeout = 2  # seconds
      self.serial.write_timeout = 2  # seconds
      self.setDelay(0)
    else:
      raise FlashKitNotFoundException(self.device_path)

  def checkForFlash(self) -> None:
    # Check Common Flash Interface (CFI) to ensure we can speak through the
    # FlashKit programmer to the flash chip on the cartridge.
    self.flashQueryMode()
    self.setAddr(0x20)

    cfi_data = self.read(6)

    # Reset to normal read mode.
    self.flashReset()

    if cfi_data != CFI_EXPECTED_DATA:
      raise FlashChipNotFoundException()

  def disconnect(self) -> None:
    self.serial.close()

  def setDelay(self, delay: int) -> None:
    self.__write2(CMD_DELAY, delay & 0xff)

  def readUint16(self, addr: int) -> int:
    self.setAddr(addr)
    self.__write1(CMD_RD | PAR_SINGE)
    return self.__read2()

  def writeUint16(self, addr: int, value: int) -> None:
    self.setAddr(addr)
    self.__write1(CMD_WR | PAR_SINGE)
    self.__writeWord(value)

  def writeUint8(self, addr: int, value: int) -> None:
    self.setAddr(addr)
    self.__write1(CMD_WR | PAR_SINGE | PAR_MODE8)
    self.__write1(value)

  def read(self, length: int) -> bytes:
    data = b''

    while length > 0:
      read_bytes = min(length, IO_BLOCK_SIZE)
      read_words = read_bytes >> 1
      self.__write2(CMD_LEN, read_words >> 8)
      self.__write2(CMD_LEN, read_words)
      self.__write1(CMD_RD | PAR_INC)

      while read_bytes > 0:
        next_chunk = self.serial.read(read_bytes)
        if len(next_chunk) < read_bytes:
          raise RuntimeError('Short read: {} vs {}'.format(
              len(next_chunk), read_bytes))
        read_bytes -= len(next_chunk)
        length -= len(next_chunk)
        data += next_chunk

    return data

  def write(self, data: bytes) -> None:
    length = len(data)
    offset = 0

    while length > 0:
      write_bytes = min(length, IO_BLOCK_SIZE)
      write_words = write_bytes >> 1
      self.__write2(CMD_LEN, write_words >> 8)
      self.__write2(CMD_LEN, write_words)
      self.__write1(CMD_WR | PAR_INC)

      end_offset = offset + write_bytes
      written = self.serial.write(data[offset:end_offset])
      assert written is not None

      if written < write_bytes:
        raise RuntimeError('Short write: {} vs {}'.format(
            written, write_bytes))

      length -= write_bytes
      offset += write_bytes

  def setAddr(self, addr: int) -> None:
    addr >>= 1  # byte to word
    self.__write2(CMD_ADDR, addr >> 16)
    self.__write2(CMD_ADDR, addr >> 8)
    self.__write2(CMD_ADDR, addr)

  def flashErase(self, addr: int) -> None:
    self.writeUint16(0x555 * 2, 0xaa)
    self.writeUint16(0x2aa * 2, 0x55)
    self.writeUint16(0x555 * 2, 0x80)
    self.writeUint16(0x555 * 2, 0xaa)
    self.writeUint16(0x2aa * 2, 0x55)

    for i in range(8):
      self.setAddr(addr)
      self.__write2(CMD_WR | PAR_SINGE | PAR_MODE8, 0x30)
      addr += 8192

    self.flashRY()

  def flashRY(self) -> None:
    # Boy, I would love to know what this does.
    self.__write2(CMD_RY, CMD_RD | PAR_SINGE)
    self.__read2()

  def flashUnlockBypass(self) -> None:
    self.writeUint8(0x555 * 2, 0xaa)
    self.writeUint8(0x2aa * 2, 0x55)
    self.writeUint8(0x555 * 2, 0x20)

  def flashResetBypass(self) -> None:
    self.flashReset()
    self.writeUint8(0, 0x90)
    self.writeUint8(0, 0x00)

  def flashQueryMode(self) -> None:
    self.writeUint8(0x55 * 2, 0x98)

  def flashReset(self) -> None:
    self.writeUint16(0, 0xf0)

  def flashWrite(self, data: bytes) -> None:
    # NOTE: This is much simpler than the original, and does not suffer in
    # speed.
    for i in range(0, len(data), 2):
      self.__write2(CMD_WR | PAR_SINGE | PAR_MODE8, 0xA0)
      self.__write1(CMD_WR | PAR_SINGE | PAR_INC)
      self.serial.write(data[i:i + 2])
      self.__write1(CMD_RY)

  def __getID(self) -> int:
    self.__write1(CMD_RD | PAR_SINGE | PAR_DEV_ID)
    return self.__read2()

  def __write1(self, int_val: int) -> None:
    int_val &= 0xff
    self.serial.write(int_val.to_bytes(1, 'big'))

  def __write2(self, int_val1: int, int_val2: int) -> None:
    int_val1 &= 0xff
    int_val2 &= 0xff
    int_val = (int_val1 << 8) | int_val2
    self.__writeWord(int_val)

  def __writeWord(self, int_val: int) -> None:
    int_val &= 0xffff
    self.serial.write(int_val.to_bytes(2, 'big'))

  def __read1(self) -> int:
    return int.from_bytes(self.serial.read(1), 'big', signed=False)

  def __read2(self) -> int:
    return int.from_bytes(self.serial.read(2), 'big', signed=False)
