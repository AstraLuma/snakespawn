#!/usr/bin/env python3
"""
Lets you put your Python and pip requirements into your file.
"""
from dataclasses import dataclass
import itertools
import os
import re
import subprocess
import sys
import typing


def scan_metadata_lines(lines):
    """
    Low-level parsing of #| lines
    Generates (prefix, text) tuples.
    """
    for line in lines:
        if line.startswith('#|') and ':' in line:
            before, after = line[2:].split(':', 1)
            yield before.strip(), after.strip()
        # Ignore #| lines without a colon


@dataclass
class ReqsInfo:
    python: typing.Optional[str]
    deps: typing.List[str]

    @classmethod
    def read_file(cls, fileobj):
        self = cls(python=None, deps=[])
        for key, value in scan_metadata_lines(fileobj):
            if key == 'python':
                self.python = value
            elif key == 'pip':
                self.deps.append(value)
        return self


# Just don't bother matching Python2
PYTHONISH = re.compile(r'^python(3(\.\d+)?)?$')


def safe_scan(path):
    """
    Wraps os.scandir() and turns FileNotFoundError into an empty iterable.
    """
    try:
        return os.scandir(path)
    except FileNotFoundError:
        return ()


def iter_pythons_path():
    """
    Finds all the pythons on $PATH
    """
    dirs = os.environ.get('PATH', os.defpath).split(os.pathsep)
    for pathdir in dirs:
        for entry in safe_scan(pathdir):
            if entry.is_file() and PYTHONISH.fullmatch(entry.name):
                yield entry.path


def iter_pythons_pyenv():
    """
    Finds all the pythons in pyenv
    """
    # FIXME: Check sudo user's home
    # FIXME: Support non-standard pyenv setups
    pyenv_home = os.path.expanduser('~/.pyenv/versions')
    for install in [
        entry.path
        for entry in safe_scan(pyenv_home)
        if entry.is_dir()
        if os.path.exists(os.path.join(entry.path, 'bin'))
    ]:
        for entry in os.scandir(os.path.join(install, 'bin')):
            if entry.is_file() and PYTHONISH.fullmatch(entry.name):
                yield entry.path


def iter_pythons_manylinux():
    """
    Finds all the pythons from manylinux
    """
    for install in [
        entry.path
        for entry in safe_scan('/opt/python')
        if entry.is_dir()
        if os.path.exists(os.path.join(entry.path, 'bin'))
    ]:
        for entry in safe_scan(os.path.join(install, 'bin')):
            if entry.is_file() and PYTHONISH.fullmatch(entry.name):
                yield entry.path


def python_version(path):
    """
    Asks the python binary at the path for its version
    """
    try:
        proc = subprocess.run(
            [path, '-V'],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,  # idk, enough for slow filesystems
        )
    except subprocess.TimeoutExpired:
        return
    if proc.returncode == 0:
        out = proc.stdout.strip()
        prog, ver = out.split(' ', 1)
        if prog in ('Python',):
            return ver


def resolve_python(version):
    potentials = itertools.chain(
        iter_pythons_path(),
        iter_pythons_manylinux(),
        iter_pythons_pyenv(),
        # TODO: Where else to look?
    )
    # TODO: Resolve symlinks and dedup
    pythons = [
        (path, python_version(path))
        for path in potentials
    ]
    print(pythons)
    # FIXME: Perform comparison against the passed-in version
    yield from ()


@ dataclass
class Args:
    filename: str
    scriptargs: typing.List[str]


def parse_args():
    # FIXME: Handle --help, --version, other stuff
    # Any parameters after the filename must be handled as scriptargs
    if len(sys.argv) < 2:
        sys.exit(f"Usage: {sys.argv[0]} filename [args]")

    return Args(
        filename=sys.argv[1],
        scriptargs=sys.argv[2:],
    )


def main():
    args = parse_args()
    with open(args.filename, 'rt') as fo:
        info = ReqsInfo.read_file(fo)

    # Discover Python
    try:
        python = next(resolve_python(info.python))
    except StopIteration:
        sys.exit(f"Could not find a Python matching {info.python}")

    # Build Venv

    # Exec


if __name__ == '__main__':
    main()
