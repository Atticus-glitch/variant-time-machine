#!/usr/bin/env python3
"""Future command-line entry point for documented data downloads."""

from variant_time_machine.download import download_clinvar_release

if __name__ == "__main__":
    download_clinvar_release()
