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


from typing import Optional

from .device import FlashKitDevice


# FlashKit upstream only accepts these characters in a ROM's name field
VALID_ROM_NAME_CHARACTERS = (
    b""" !()_-:/.[]|&'`""" +
    b'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
)

# Bank-switching happens by writing to addresses in this space.  It corresponds
# to the /TIME pin on the cartridge.
TIME_REGISTER = 0xA13000

# Normally SRAM lives at this address, but it can overlap with ROM if
# bank-switching is used.
SRAM_BASE = 0x200000

SECTOR_SIZE = 512
SIXTY_FOUR_K = (64 * 1024)

HALF_MB  =  0x80000
ONE_MB   = 0x100000
TWO_MB   = 0x200000
THREE_MB = 0x300000
FOUR_MB  = 0x400000


class Cart(object):
  def __init__(self, device: FlashKitDevice):
    self.device: FlashKitDevice = device

  def romName(self) -> str:
    self.device.setAddr(0)
    header = self.device.read(512)

    name = self.__parseRomName(header, 0x120)
    if name is None:
      name = self.__parseRomName(header, 0x150)
    if name is None:
      name = 'Unknown'
    name += ' (' + self.__parseRomRegion(header) + ')'
    return name

  def ramAvailable(self) -> bool:
    # Activates SRAM in the cart's mapper, if available
    self.device.writeUint16(TIME_REGISTER, 0xffff)

    # Read from this address.
    first_word = self.device.readUint16(SRAM_BASE)
    # Write the inverse to this address, then read it back.
    modified_word = first_word ^ 0xffff
    self.device.writeUint16(SRAM_BASE, modified_word)
    stored_word = self.device.readUint16(SRAM_BASE)

    # Now restore the original, so we don't break a saved game.
    self.device.writeUint16(SRAM_BASE, first_word)

    # Now we compare only the low byte, since SRAM may only be 8-bits wide.
    first_byte = first_word & 0xff
    stored_byte = stored_word & 0xff

    # If it's SRAM, we expect stored_byte to be the inverse of first_byte.
    return stored_byte == first_byte ^ 0xff

  def romSize(self, trust_header: bool) -> int:
    self.device.setAddr(0)
    header = self.device.read(512)

    rom_end_address = int.from_bytes(header[0x1a4:0x1a8], 'big')

    has_ram = False
    has_extra_rom = False

    if self.ramAvailable():
      has_ram = True
      has_extra_rom = self.__detectExtraRom()

    max_rom_size = FOUR_MB
    if has_ram and not has_extra_rom:
      max_rom_size = TWO_MB

    # I would love an explanation of this logic, too.  I ported it directly.
    # It appears to be some magic to understand the length of a ROM when
    # bank-switching is in use.
    length = self.__checkRomSize(0, max_rom_size)
    if length == FOUR_MB:
      length = TWO_MB
      length2 = self.__checkRomSize(TWO_MB, TWO_MB)

      if length2 == TWO_MB:
        length2 = self.__checkRomSize(THREE_MB, ONE_MB)
        if length2 >= HALF_MB:
          length2 = TWO_MB
        else:
          length2 = ONE_MB

      if length2 > HALF_MB:
        length += length2

    if trust_header and rom_end_address < length:
      return rom_end_address + 1

    return length

  def ramSize(self) -> int:
    if not self.ramAvailable():
      return 0

    # Read the first word of SRAM
    first_word = self.device.readUint16(SRAM_BASE)
    first_byte = first_word & 0xff

    # Look for a place where SRAM wraps around
    ram_size = 256
    while ram_size < ONE_MB:
      # Read the word at this offset
      original_word = self.device.readUint16(SRAM_BASE + ram_size)
      original_byte = original_word & 0xff

      # Store back the inverse
      modified_word = original_word ^ 0xffff
      self.device.writeUint16(SRAM_BASE + ram_size, modified_word)

      # See what we wrote to this offset, and to the first word in SRAM
      stored_word = self.device.readUint16(SRAM_BASE + ram_size)
      stored_byte = stored_word & 0xff
      stored_first_word = self.device.readUint16(SRAM_BASE)
      stored_first_byte = stored_first_word & 0xff

      # Restore the original contents of this offset, to avoid breaking a save
      self.device.writeUint16(SRAM_BASE + ram_size, original_word)

      # Break the search if the data you wrote wasn't reflected back.
      # This indicates we reached an address that isn't SRAM.
      if stored_byte != original_byte ^ 0xff:
        break

      # Break the search if we changed the first byte of SRAM.
      # This indicates we wrapped around in SRAM address space.
      # FIXME: There seems to be a flaw in the original logic here.
      # If original_byte == first_byte ^ 0xff, then the modified byte we wrote
      # at this address will happen to match the original first byte, and this
      # check will not know we actually wrapped around.
      if stored_first_byte != first_byte:
        break

      ram_size *= 2

    # NOTE: Deviation from the original: we return full bytes in the address
    # space here, rather than cutting it in half.  The original either treats
    # the SRAM as only storing 8 bits per word or returns number of words for
    # some reason.  It is unclear what the original thinking was.
    return ram_size

  def readRam(self, max_size: Optional[int] = None) -> bytes:
    # Unused in the original (getRam in Cart.cs), but ported for and used here
    # to keep some of these details out of flashkit.py commands.  Untested.

    ram_size = self.ramSize()
    if max_size:
      ram_size = min(ram_size, max_size)

    self.device.writeUint16(TIME_REGISTER, 0xffff)
    self.device.setAddr(SRAM_BASE)
    return self.device.read(ram_size)

  def writeRam(self, ram: bytes) -> None:
    self.device.writeUint16(TIME_REGISTER, 0xffff)
    self.device.setAddr(SRAM_BASE)
    self.device.write(ram)

  def __parseRomName(self, header: bytes, offset: int) -> Optional[str]:
    # Strip off trailing spaces
    name = header[offset:offset + 48].strip(b' \x00\xff')

    # Reject characters not in the valid ROM name set
    for x in name:
      if x not in VALID_ROM_NAME_CHARACTERS:
        raise RuntimeError('Invalid ROM name: ' + name.hex())

    return name.decode('utf-8') or None

  def __parseRomRegion(self, header: bytes) -> str:
    # NOTE: This diverges from the original, which was undocumented, hard to
    # follow, and hacky.  There were no comments whatsoever in the original.
    # The original version called any multi-region ROM a "World" ROM with code
    # "W", whereas we return the actual list (e.g. "JU", "JUE", etc).
    # We also parse entries missed by the original.
    # https://plutiedev.com/rom-header#region

    # The old format is one-to-three bytes, with values "J" (Japan), "U"
    # (America), or "E" (Europe), in any order, padded with nul or space.
    old_regions = header[0x1f0:0x1f3].strip(b'\x00 ')
    old_format = True
    for x in old_regions:
      if x not in b'JUE':
        old_format = False
        break

    if old_format:
      return old_regions.decode('ascii')

    # The new format is a single-byte which encodes combinations of all three
    # regions.  The byte is an ascii character with a single hex digit.
    regions_char = chr(header[0x1f0])
    regions_int = int(regions_char, 16)

    japan = regions_int & 1
    americas = regions_int & 4
    europe = regions_int & 8

    # A string like "J", "U", "E", "JUE", etc.
    regions = (
      ('J' if japan else '') +
      ('U' if americas else '') +
      ('E' if europe else '')
    )

    if not regions:
      return 'X'  # Unknown

    return regions

  def __checkRomSize(self, base_addr: int, max_length: int) -> int:
    base_length = 0x8000
    length = 0x8000

    # Disable bank-switching?
    self.device.writeUint16(TIME_REGISTER, 0x0000)

    # Read the first sector.
    # NOTE: The original read 256 bytes here, but 512 elsewhere.
    # I standardized on sector size of 512.
    self.device.setAddr(base_addr)
    sector0 = self.device.read(SECTOR_SIZE)

    while True:
      self.device.setAddr(base_addr + length)
      sector = self.device.read(SECTOR_SIZE)
      # If this sector matches the first sector, we wrapped around in the ROM's
      # actual address space.  So this is the length of the ROM.
      if sector == sector0:
        break

      # Double the distance from the base and check again.
      length *= 2
      if length >= max_length:
        break

    # If the ROM wrapped after just one check, return 0.
    # It's unclear why we need this check.
    if length == base_length:
      return 0

    return length

  def __detectExtraRom(self) -> bool:
    # I can't find any explanation of this logic, nor does it align with any
    # docs I can find on Sega carts, SRAM, or bank switching.  I assume for
    # now it's logic specific to Krikzz flashkit, so I have ported it
    # faithfully.  But it seems fishy.

    self.device.writeUint16(TIME_REGISTER, 0x0000)

    self.device.setAddr(SRAM_BASE)
    sector0 = self.device.read(SECTOR_SIZE)

    self.device.setAddr(SRAM_BASE)
    sector = self.device.read(SECTOR_SIZE)

    has_extra_rom = True

    if sector != sector0:
      has_extra_rom = False

    if has_extra_rom:
      has_extra_rom = False
      self.device.setAddr(SRAM_BASE + SIXTY_FOUR_K)
      sector = self.device.read(SECTOR_SIZE)  # [sic]

      self.device.writeUint16(TIME_REGISTER, 0x0000)
      self.device.setAddr(SRAM_BASE)
      sector = self.device.read(SECTOR_SIZE)  # [sic]

      # NOTE: Both reads above go to "sector" in the original code by Krikzz,
      # even though it seems like one should probably be "sector0".  Because
      # the logic and purpose is unclear, I can't tell if this is a bug or
      # not.

      if sector != sector0:
        has_extra_rom = True

    return has_extra_rom
