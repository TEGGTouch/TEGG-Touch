"""Reject development credentials and runtime caches before packaging or publishing.

Usage: python scripts/check_release_config.py <build directory or ZIP>
Error messages identify files, never credential values.
"""

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


_CREDENTIAL_FIELDS = re.compile(
    r'(?:^|_)(?:api_?key|access_?key(?:_?(?:id|secret))?|secret(?:_?key)?|'
    r'(?:auth|access|refresh|security|sts|bearer)_?token|token|password)(?:$|_)', re.I)
_PRIVATE_KEY = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----')
_TOKEN = re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b')
_TEXT_EXTENSIONS = {'.json', '.ini', '.conf', '.cfg', '.toml', '.txt', '.pem',
                    '.env', '.yaml', '.yml', '.bat', '.ps1', '.py'}
_MAX_CONFIG_BYTES = 4 * 1024 * 1024


def _contains_credential(data):
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = re.sub(r'([a-z])([A-Z])', r'\1_\2', key).replace('-', '_')
            if _CREDENTIAL_FIELDS.search(normalized) and value:
                return True
            if _contains_credential(value):
                return True
    elif isinstance(data, list):
        return any(_contains_credential(value) for value in data)
    return False


def _check_path(name):
    path = PurePosixPath(name.replace('\\', '/'))
    parts = [part.casefold() for part in path.parts]
    if any(part == '.git' or part.startswith('.env') or part.startswith('.ossutilconfig')
           for part in parts):
        raise ValueError(f'Development configuration in release: {name}')
    if path.name.casefold() in {'agent.json', 'id_rsa', 'id_ed25519', 'yunxiao-token.txt'}:
        raise ValueError(f'Credential file in release: {name}')
    if path.suffix.casefold() in {'.key', '.pfx', '.p12'}:
        raise ValueError(f'Private key container in release: {name}')
    if 'settings' in parts and parts[parts.index('settings') + 1:] != ['hotkeys.json']:
        raise ValueError(f'Runtime settings or cache in release: {name}')
    return path


def _check_content(name, content):
    if _PRIVATE_KEY.search(content) or _TOKEN.search(content):
        raise ValueError(f'Credential material in release: {name}')
    if PurePosixPath(name).suffix.casefold() == '.json':
        try:
            data = json.loads(content)
        except (ValueError, UnicodeError) as error:
            raise ValueError(f'Invalid JSON configuration in release: {name}') from error
        if _contains_credential(data):
            raise ValueError(f'Nonempty credential field in release: {name}')


def check_release_config(source):
    """Inspect the build tree or ZIP, including nested credential fields in profiles."""
    source = Path(source)
    if source.is_dir():
        for file in source.rglob('*'):
            if file.is_dir():
                continue
            name = file.relative_to(source).as_posix()
            path = _check_path(name)
            if file.is_symlink():
                raise ValueError(f'Symlink in release: {name}')
            if path.suffix.casefold() in _TEXT_EXTENSIONS:
                if file.stat().st_size > _MAX_CONFIG_BYTES:
                    raise ValueError(f'Configuration too large to audit: {name}')
                _check_content(name, file.read_bytes())
    else:
        with zipfile.ZipFile(source) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                path = _check_path(item.filename)
                if path.suffix.casefold() in _TEXT_EXTENSIONS:
                    if item.file_size > _MAX_CONFIG_BYTES:
                        raise ValueError(f'Configuration too large to audit: {item.filename}')
                    _check_content(item.filename, archive.read(item))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    try:
        check_release_config(args.source)
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f'Release configuration check failed: {error}\n')
    print('Release configuration check passed.')


if __name__ == '__main__':
    main()
