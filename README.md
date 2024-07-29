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
 - Offers debug methods and arguments, which helped in the development of my
   own flash cart


## Installation

```
python3 -m pip install flashkit
```


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
