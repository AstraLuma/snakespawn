#!/usr/bin/env python3
"""
Lets you put your Python and pip requirements into your file.
"""
from dataclasses import dataclass
import itertools
import os
import re
import pathlib
import subprocess
import sys
import tempfile
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


def look_for_pythons(root):
    """
    Runs a glob, yields potential python binaries.
    """
    for item in itertools.chain(
        pathlib.Path(root).glob('python*'),
        (pathlib.Path(root) / 'bin').glob('python*'),
    ):
        if PYTHONISH.fullmatch(item.name) and item.is_file():
            yield item


def iter_pythons_path():
    """
    Finds all the pythons on $PATH
    """
    dirs = os.environ.get('PATH', os.defpath).split(os.pathsep)
    for pathdir in dirs:
        yield from look_for_pythons(pathdir)


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
    ]:
        yield from look_for_pythons(install)


def iter_pythons_manylinux():
    """
    Finds all the pythons from manylinux
    """
    for install in [
        entry.path
        for entry in safe_scan('/opt/python')
        if entry.is_dir()
    ]:
        yield from look_for_pythons(install)


def python_version(path):
    """
    Asks the python binary at the path for its version.

    Returns None on any error or if the output was unrecognized.
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
    """
    Scours the system for python installations and finds the ones that match
    the given version requirement.
    """
    potentials = itertools.chain(
        iter_pythons_path(),
        iter_pythons_manylinux(),
        iter_pythons_pyenv(),
        # TODO: Where else to look?
    )
    # TODO: Resolve symlinks and dedup
    pythons = list(filter(lambda i: bool(i[1]), (
        (path, python_version(path))
        for path in potentials
    )))
    # FIXME: Perform actual parsing & comparisons following PEP440
    # This is a minimal, half-assesed version of what I would like this to do
    if version:
        if not re.match(r'\d+(\.\d+)*', version):
            sys.exit(
                f"Currently only supports Python version spec of x.y.z (given {version!r})\n"
                "FIXME: Support full PEP440"
            )
        looking_for_version = [int(bit) for bit in version.split('.')]
        for pypath, pyver in pythons:
            if not pyver:
                continue
            pyver = [int(bit) for bit in pyver.split('.')]
            if pyver >= looking_for_version:
                yield pypath
    else:
        pythons = sorted(
            pythons,
            key=(lambda pv:
                 [int(bit) for bit in pv[1].split('.')] if pv[1] else []),
            reverse=True,
        )
        yield from (p for p, _ in pythons)


@ dataclass
class Args:
    filename: str
    scriptargs: typing.List[str]


def parse_args():
    """
    Parse CLI args
    """
    # FIXME: Handle --help, --version, other stuff
    # Any parameters after the filename must be handled as scriptargs
    if len(sys.argv) < 2:
        sys.exit(f"Usage: {sys.argv[0]} filename [args]")

    return Args(
        filename=sys.argv[1],
        scriptargs=sys.argv[2:],
    )


def get_venv(python, deps):
    """
    Returns the venv-ified Python binary to use.

    Either creates a venv or reuses a previously-existing one.
    """
    # FIXME: Use re-discoverable directory names
    # h = hashlib.shake_128('\n'.join(sorted(reqs)).encode('utf-8'))
    venvpath = tempfile.mkdtemp(prefix='snakespawn')
    subprocess.run([python, '-m', 'venv', venvpath], check=True)
    # FIXME: Handle Windows
    return f"{venvpath}/bin/python"


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
    python = get_venv(python, info.deps)

    # Exec
    os.execv(python, [python, args.filename] + args.scriptargs)


if __name__ == '__main__':
    main()
