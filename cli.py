#!/usr/bin/python3
#
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


# This is just a frontend to run the CLI.  You get something similar installed
# automatically by pip, but if you're running the CLI from your git working
# directory, you want to use this script.

import sys

from flashkit.flashkit import main

if __name__ == '__main__':
    sys.argv[0] = 'flashkit'
    sys.exit(main())
