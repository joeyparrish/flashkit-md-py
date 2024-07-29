#!/usr/bin/env python3

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

# last sync with upstream C# version:
#   commit 8194b0d72ee0036447532c277778ec503bd8e4c6
#   Author: krikzz <biokrik@gmail.com>
#   Date:   Wed Dec 20 01:37:44 2023 +0100

"""
Drive the Krikzz FlashKit Programmer MD from the command-line to rewrite Sega
Genesis / MegaDrive flash carts.
"""

import argparse
import datetime
import hashlib
import math

from .device import FlashKitDevice
from .cart import Cart, TIME_REGISTER


READ_BLOCK_SIZE =        (32 << 10)  # 32 kB
WRITE_BLOCK_SIZE =        (4 << 10)  #  4 kB
ROM_SIZE_MULTIPLE =      (64 << 10)  # 64 kB
FLASH_ERASE_BLOCK_SIZE = (64 << 10)  # 64 kB

OPEN_EVERDRIVE_SIGNATURE = b"OPEN-EVERDRIVE"
OPEN_EVERDRIVE_SIGNATURE_OFFSET = 0x120
OPEN_EVERDRIVE_BANK_REGISTER = 0xA130E0
OPEN_EVERDRIVE_BANK_VALUE = 0x0404
OPEN_EVERDRIVE_DATETIME_OFFSET = 0x1c8


def __formatSize(size: int) -> str:
  if size < 1024:
    return str(size) + ' B'

  if size < 1024 * 1024:
    return str(math.ceil(size / 1024)) + ' kB'

  return str(math.ceil(size / 1024 / 1024)) + ' MB'


def __initOpenEverDrive(device: FlashKitDevice, rom: bytes) -> bytes:
  # Special logic for writing OpenEverDrive ROMs
  open_ed_start = OPEN_EVERDRIVE_SIGNATURE_OFFSET
  open_ed_end = open_ed_start + len(OPEN_EVERDRIVE_SIGNATURE)

  if rom[open_ed_start:open_ed_end] != OPEN_EVERDRIVE_SIGNATURE:
    return rom

  # Initialize the Open EverDrive ROM bank
  device.writeUint16(OPEN_EVERDRIVE_BANK_REGISTER, OPEN_EVERDRIVE_BANK_VALUE)

  # Apply the date and time to the ROM
  now = datetime.datetime.now()
  date = now.day | (now.month << 5) | ((now.year - 1980) << 9)
  time = (now.second // 2) | (now.minute << 5) | (now.hour << 11)

  datestamp_bytes = (
    (date & 0xff).to_bytes(1, 'big') +
    (date >> 8).to_bytes(1, 'big') +
    (time & 0xff).to_bytes(1, 'big') +
    (time >> 8).to_bytes(1, 'big')
  )

  return (
      rom[:OPEN_EVERDRIVE_DATETIME_OFFSET] +
      datestamp_bytes +
      rom[OPEN_EVERDRIVE_DATETIME_OFFSET + 4:]
  )


def __verify(data1: bytes, data2: bytes) -> bool:
  if data2 == data1:
    print('\rVerify complete!      ')
    print('MD5: ' + hashlib.md5(data1).hexdigest())
    return True

  print('\rVerify failed!        ')
  print('Original MD5: ' + hashlib.md5(data1).hexdigest())
  print('Cart MD5:     ' + hashlib.md5(data2).hexdigest())

  for i in range(len(data1)):
    if data1[i] != data2[i]:
      print('First failed byte offset {} is {:02x}, should be {:02x}'.format(
          i, data2[i], data1[i]))
      break
  return False


def check(port: str) -> bool:
  device = FlashKitDevice(port)
  cart = Cart(device)
  device.setDelay(1)

  name = cart.romName()
  if not name:
    print('Cart not found!')
    return False

  print('ROM name: ' + cart.romName())
  print('ROM chip size: ' + __formatSize(cart.romSize(trust_header=False)))
  print('ROM size: ' + __formatSize(cart.romSize(trust_header=True)))
  print('RAM size: ' + __formatSize(cart.ramSize()))
  return True


def readRom(port: str, path: str, rom_size: int) -> bool:
  device = FlashKitDevice(port)
  cart = Cart(device)
  device.setDelay(1)

  if not path:
    name = cart.romName()
    if not name:
      print('Cart not found!')
      return False

    path = name + '.bin'
    print('Default output: ' + path)

  if not rom_size:
    rom_size = cart.romSize(trust_header=True)
    print('Detected ROM size: ' + str(rom_size))

  device.writeUint16(TIME_REGISTER, 0x0000)
  device.setAddr(0)

  md5 = hashlib.md5()
  with open(path, 'wb') as f:
    for offset in range(0, rom_size, READ_BLOCK_SIZE):
      progress = offset / rom_size
      print('\rRead progress: {:.1f}%'.format(progress * 100), end='')

      block = device.read(READ_BLOCK_SIZE)
      md5.update(block)
      f.write(block)

  print('\rRead complete!      ')

  print('Read {} ROM'.format(__formatSize(rom_size)))
  print('MD5: ' + md5.hexdigest())

  return True


def __writeRom(device: FlashKitDevice, path: str) -> bool:
  device.setDelay(0)
  device.checkForFlash()

  with open(path, 'rb') as f:
    rom = f.read()

  rom_size = len(rom)
  rom_size_dangling = rom_size % ROM_SIZE_MULTIPLE

  # Pad out to a multiple of ROM_SIZE_MULTIPLE
  if rom_size_dangling != 0:
    rom_size_padding = ROM_SIZE_MULTIPLE - rom_size_dangling
    rom_size += rom_size_padding
    rom += bytes(rom_size_padding)

  print('Writing {} ROM from {}'.format(__formatSize(rom_size), path))

  rom = __initOpenEverDrive(device, rom)

  device.flashResetBypass()

  for offset in range(0, rom_size, FLASH_ERASE_BLOCK_SIZE):
    progress = offset / rom_size
    print('\rFlash erase progress: {:.1f}%'.format(progress * 100), end='')
    device.flashErase(offset)

  print('\rFlash erase complete!      ')

  device.flashUnlockBypass()
  device.setAddr(0)

  for offset in range(0, rom_size, WRITE_BLOCK_SIZE):
    progress = offset / rom_size
    print('\rWrite progress: {:.1f}%'.format(progress * 100), end='')
    device.flashWrite(rom[offset:offset + WRITE_BLOCK_SIZE])

  print('\rWrite complete!      ')

  device.flashResetBypass()
  device.setAddr(0)

  rom2 = b''
  for offset in range(0, rom_size, WRITE_BLOCK_SIZE):
    progress = offset / rom_size
    print('\rVerify progress: {:.1f}%'.format(progress * 100), end='')
    rom2 += device.read(WRITE_BLOCK_SIZE)

  return __verify(rom, rom2)


def writeRom(port: str, path: str) -> bool:
  # Separated error-handling from the work, for readability
  try:
    device = FlashKitDevice(port)
    return __writeRom(device, path)
  except Exception as e:
    try:
      device.flashResetBypass()
    except Exception:
      pass

    # After resetting the device, raise the original exception
    raise e


def readRam(port: str, path: str) -> bool:
  device = FlashKitDevice(port)
  cart = Cart(device)
  device.setDelay(1)

  name = cart.romName()
  if not name:
    print('Cart not found!')
    return False

  if not path:
    path = name + '.srm'
    print('Default output: ' + path)

  ram_size = cart.ramSize()  # bytes
  if ram_size == 0:
    print('RAM not detected!')
    return False

  print('RAM size: ' + __formatSize(ram_size))

  with open(path, 'wb') as f:
    ram = cart.readRam()
    f.write(ram)

  print('RAM dump complete')
  print('MD5: ' + hashlib.md5(ram).hexdigest())

  return True


def writeRam(port: str, path: str) -> bool:
  device = FlashKitDevice(port)
  cart = Cart(device)
  device.setDelay(1)

  ram_size = cart.ramSize()
  if ram_size == 0:
    print('RAM not detected!')
    return False

  with open(path, 'rb') as f:
    ram = f.read()

  copy_length = min(len(ram), ram_size)
  copy_length &= ~1  # Clip off any odd bytes

  cart.writeRam(ram[0:copy_length])
  print('RAM updated')

  ram2 = cart.readRam(copy_length)
  return __verify(ram, ram2)


def read16(port: str, addr: int) -> bool:
  device = FlashKitDevice(port)
  print('{:4x}'.format(device.readUint16(addr)))
  return True


def write16(port: str, addr: int, value: int) -> bool:
  device = FlashKitDevice(port)
  device.writeUint16(addr, value)
  return True


def write8(port: str, addr: int, value: int) -> bool:
  device = FlashKitDevice(port)
  device.writeUint8(addr, value)
  return True


def main() -> None:
  parser = argparse.ArgumentParser(
      prog='flashkit',
      description=__doc__,
      epilog='Use "flashkit <command> --help" to see options for each command.')
  parser.add_argument('-p', '--port',
      help='Serial port device to use; default is to autodetect')

  subparsers = parser.add_subparsers(
      title='available commands',
      metavar='command', dest='command')

  check_parser = subparsers.add_parser('check',
      help='Print info about the attached cart')
  check_parser.set_defaults(
      func=lambda args: check(args.port))

  read_rom_parser = subparsers.add_parser('read-rom',
      help='Read the ROM from the cart to a file')
  read_rom_parser.add_argument('-o', '--output',
      help='Output file; default is derived from the ROM name on the cart')
  read_rom_parser.add_argument('-s', '--size', type=int,
      help='ROM size; if given, won\'t attempt to detect ROM size in the cart')
  read_rom_parser.set_defaults(
      func=lambda args: readRom(args.port, args.output, args.size))

  write_rom_parser = subparsers.add_parser('write-rom',
      help='Write the ROM from a file to the cart')
  write_rom_parser.add_argument('-i', '--input', required=True,
      help='Input file; required')
  write_rom_parser.set_defaults(
      func=lambda args: writeRom(args.port, args.input))

  read_ram_parser = subparsers.add_parser('read-ram',
      help='Read the RAM from the cart to a file')
  read_ram_parser.add_argument('-o', '--output',
      help='Output file; default is derived from the ROM name on the cart')
  read_ram_parser.set_defaults(
      func=lambda args: readRam(args.port, args.output))

  write_ram_parser = subparsers.add_parser('write-ram',
      help='Write the RAM from a file to the cart')
  write_ram_parser.add_argument('-i', '--input', required=True,
      help='Input file; required')
  write_ram_parser.set_defaults(
      func=lambda args: writeRam(args.port, args.input))

  read_16_parser = subparsers.add_parser('read-16',
      help='Read a single word from a specific address to debug the cartridge')
  read_16_parser.add_argument('-a', '--address', required=True, type=int,
      help='The address')
  read_16_parser.set_defaults(
      func=lambda args: read16(args.port, args.address))

  write_16_parser = subparsers.add_parser('write-16',
      help='Write a single word to a specific address to debug the cartridge')
  write_16_parser.add_argument('-a', '--address', required=True, type=int,
      help='The address')
  write_16_parser.add_argument('-v', '--value', required=True, type=int,
      help='The word (16-bit value)')
  write_16_parser.set_defaults(
      func=lambda args: write16(args.port, args.address, args.value))

  write_8_parser = subparsers.add_parser('write-8',
      help='Write a single byte to a specific address to debug the cartridge')
  write_8_parser.add_argument('-a', '--address', required=True, type=int,
      help='The address')
  write_8_parser.add_argument('-v', '--value', required=True, type=int,
      help='The byte (8-bit value)')
  write_8_parser.set_defaults(
      func=lambda args: write8(args.port, args.address, args.value))

  args = parser.parse_args()

  if args.command:
    # Run the "func" associated with whichever subcommand was given:
    args.func(args)
  else:
    # Explicitly print help, instead of making command required.
    # This way, we see the full help instead of the short version
    parser.print_help()


if __name__ == '__main__':
  main()
