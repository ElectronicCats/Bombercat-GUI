#!/usr/bin/env python3
"""Punto de entrada de conveniencia. La CLI vive en `cardsec.cli`."""
import sys

from cardsec.cli import main

if __name__ == "__main__":
    sys.exit(main())
