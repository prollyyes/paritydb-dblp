#!/usr/bin/env python3
"""Compatibility entry point for the containerized comparison command."""

import sys

from dm_project.demo import main


if __name__ == "__main__":
    sys.argv.insert(1, "compare")
    main()
