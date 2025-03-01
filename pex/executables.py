# Copyright 2025 Pants project contributors (see CONTRIBUTORS.md).
# Licensed under the Apache License, Version 2.0 (see LICENSE).

from __future__ import absolute_import

import os
import re
import stat
import zipfile
from textwrap import dedent

from pex.os import WINDOWS, is_exe
from pex.typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import BinaryIO, Callable, Optional, Text, Tuple


def chmod_plus_x(path):
    # type: (Text) -> None
    """Equivalent of unix `chmod a+x path`"""
    path_mode = os.stat(path).st_mode
    path_mode &= int("777", 8)
    if path_mode & stat.S_IRUSR:
        path_mode |= stat.S_IXUSR
    if path_mode & stat.S_IRGRP:
        path_mode |= stat.S_IXGRP
    if path_mode & stat.S_IROTH:
        path_mode |= stat.S_IXOTH
    os.chmod(path, path_mode)


_SHEBANG_MAGIC = b"#!"


def is_script(
    path,  # type: Text
    pattern=None,  # type: Optional[bytes]
    check_executable=True,  # type: bool
    extra_check=None,  # type: Optional[Callable[[bytes, BinaryIO], bool]]
):
    # type: (...) -> bool
    """Determines if the given path is a script.

    A script is a file that starts with a shebang (#!...) line.

    :param path: The path to check.
    :param pattern: Optional pattern to match against the shebang line (excluding the leading #!
                    and trailing \n).
    :param check_executable: Check that the script is executable by the current user.
    :param extra_check: Optional callable accepting the shebang line (excluding the leading #! and
                        trailing \n) and a file opened for binary read pointing just after that
                        line.
    :return: True if the given path is a script.
    """
    path = os.path.realpath(path)
    if check_executable and not is_exe(path):
        return False
    elif not os.path.isfile(path):
        return False

    with open(path, "rb") as fp:
        if _SHEBANG_MAGIC != fp.read(len(_SHEBANG_MAGIC)):
            return False
        if not pattern:
            return True
        shebang_suffix = fp.readline().rstrip()
        if bool(re.match(pattern, shebang_suffix)):
            return True
        if extra_check:
            return extra_check(shebang_suffix, fp)
        return False


def create_sh_python_redirector_shebang(sh_script_content):
    # type: (str) -> Tuple[str, str]
    """Create a shebang block for a Python file that uses /bin/sh to find an appropriate Python.

    The script should be POSIX compliant sh and terminate on all execution paths with an
    explicit exit or exec.

    The returned shebang block will include the leading `#!` but will not include a trailing new
    line character.

    :param sh_script_content: A POSIX compliant sh script that always explicitly terminates.
    :return: A shebang line and trailing block of text that can be combined for use as a shebang
             header for a Python file.
    """
    # This trick relies on /bin/sh being ubiquitous and the concordance of:
    #
    # 1. Python: Has triple quoted strings plus allowance for free-floating string values in
    #    python files.
    # 2. sh: Any number of pairs of `'` evaluating away when followed immediately by a
    #    command string (`''command` -> `command`).
    # 3. sh: The `:` noop command which accepts and discards arbitrary args.
    #    See: https://pubs.opengroup.org/onlinepubs/009604599/utilities/colon.html
    # 4. sh: Lazy parsing allowing for invalid sh content immediately following an exit or exec
    #        line.
    #
    # The end result is a file that is both a valid sh script with a short shebang and a valid
    # Python program.
    return "#!/bin/sh", (
        dedent(
            """\
            '''': pshprs
            {sh_script_content}
            '''
            """
        )
        .format(sh_script_content=sh_script_content.rstrip())
        .strip()
    )


_PYTHON_SHEBANG_RE = br"""(?ix)
# The aim is to admit the common shebang forms:
# + python
# + /usr/bin/env (<args>)? <python bin name> (<args>)?
# + /absolute/path/to/<python bin name> (<args>)?
# The 1st corresponds to the special placeholder shebang #!python specified here:
# + https://peps.python.org/pep-0427
# + https://packaging.python.org/specifications/binary-distribution-format
(?:^|.*\W)

# Python executable names Pex supports (see PythonIdentity).
(?:
      python
    | pypy
)

# Optional Python version
(?:\d+(?:\.\d+)*)?

# Windows extension
(?:\.exe)?

# Support a shebang with an argument to the interpreter at the end.
(?:\s[^\s]|$)
"""


def is_python_script(
    path,  # type: Text
    check_executable=True,  # type: bool
):
    # type: (...) -> bool

    path = os.path.realpath(path)
    if is_script(
        path,
        pattern=_PYTHON_SHEBANG_RE,
        check_executable=check_executable,
        extra_check=lambda shebang, fp: shebang == b"/bin/sh" and fp.read(13) == b"'''': pshprs\n",
    ):
        return True

    if WINDOWS:
        # Check for the style of console scripts we create.
        from pex import windows

        if windows.is_script(path):
            return True

        # Check for the style of console scripts Pip creates.
        if not zipfile.is_zipfile(path):
            return False

        from pex.ziputils import Zip

        zip_script = Zip.load(path)
        with open(os.devnull, "wb") as fp:
            shebang = zip_script.isolate_header(fp, stop_at=_SHEBANG_MAGIC)
            if shebang:
                if bool(re.match(_PYTHON_SHEBANG_RE, shebang[len(_SHEBANG_MAGIC) :].strip())):
                    return True

    return False
