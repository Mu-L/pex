# SPDX-License-Identifier: MIT

if "attrs" in __import__("os").environ.get("__PEX_UNVENDORED__", ""):
    from attr.converters import *  # vendor:skip
else:
    from pex.third_party.attr.converters import *
  # noqa
