# FlashKit MD Python Client

This is a Python command-line tool to drive the Krikzz FlashKit Programmer MD.
It allows you to rewrite Sega Genesis / MegaDrive flash carts from the command
line, as opposed to the original software which require .NET and a GUI.

 - Original C# GUI tool and hardware design:
   - https://github.com/krikzz/flashkit
 - Purchase the hardware from the designer:
   - https://krikzz.com/our-products/accessories/flashkitmd.html
   - https://krikzz.com/our-products/cartridges/flashkitmd.html

Main motivations for this rewrite:

 - Command-line operation
 - Runs everywhere with Python 3 instead of .NET/Mono

Functional improvements over the original:

 - ROM region code parsing is more detailed, accurate, and readable
 - Can tell the difference between ROM size and Flash chip size,
   avoiding oversized ROM dumps from flash carts
 - Uses CFI to establish successful communication with flash before writing
   (saves time if something is very wrong with your cart)
 - Offers debug methods and arguments, which helped in the development of my
   own flash cart
 - Optional per-sector erase for bottom-boot flash chips (see below)


## Installation

```
python3 -m pip install flashkit --upgrade
```


## Usage

```
flashkit check                        # Print info about the attached cart
flashkit read-rom -o dump.bin         # Read the ROM from the cart to a file
flashkit write-rom -i game.bin        # Erase flash and write a ROM to the cart
flashkit erase-rom -s 4194304         # Erase flash without writing
flashkit read-ram -o save.srm         # Read the save RAM to a file
flashkit write-ram -i save.srm        # Write a file to the save RAM
```

Use `-p <port>` before the command to choose a serial port instead of
autodetecting it, and `flashkit <command> --help` to see all options for a
command.

For `erase-rom`, `-s` is the number of bytes to erase from the start of flash,
rounded up to a multiple of 64 kB.


### Bottom-boot flash chips

Some flash chips (common in clone and reproduction carts) are "bottom-boot":
the first 64 kB is split into small boot sectors (as small as 8 kB) instead of
one 64 kB sector.  By default, the erase step sends one unlock sequence per
64 kB and then queues several sector-erase commands 8 kB apart, which covers
those boot sectors on chips that accept queued erase commands.  Some chips
ignore the queued commands, so only part of the first 64 kB gets erased and
the write fails verification near the start of the ROM.

If that happens, add `--bottom-boot` to `write-rom` or `erase-rom`:

```
flashkit write-rom -i game.bin --bottom-boot
flashkit erase-rom -s 65536 --bottom-boot
```

This erases each 8 kB step of the first 64 kB with its own unlock sequence and
waits for each erase to finish.  On chips with larger boot sectors, some
sectors are erased more than once, which is harmless.  The rest of the flash
is erased as usual.


## License

Released under GPL v3.  See [LICENSE.md](LICENSE.md).

Derived from the original software by Krikzz, which was also released under GPL
v3.


## Dependencies

 - Python 3
   - argparse library (included with Python)
   - datetime library (included with Python)
   - hashlib library (included with Python)
   - typing library (included with Python)
   - serial library (Ubuntu package `python3-serial` or
                     `python3 -m pip install pyserial` for development)
