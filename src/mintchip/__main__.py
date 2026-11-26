"""``python -m mintchip``: the command line, for when ``mintchip`` is not on PATH."""

import sys

from .cli import main

sys.exit(main())
