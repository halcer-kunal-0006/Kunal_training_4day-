"""Allow ``python -m ticket_pipeline``."""

import sys

from .cli import main

sys.exit(main())
