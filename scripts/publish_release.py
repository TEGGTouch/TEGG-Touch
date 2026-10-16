"""Explicit OSS publication. Default is dry-run; credentials stay in ossutil config."""

import argparse
import ast
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.update_manifest import (LATEST_URL, OSS_BASE, MAX_MANIFEST_BYTES,
                                  is_newer, open_update_url, parse_manifest, validate_archive)
from scripts.release_history import (fetch_history, merge_history, list_oss_history, verify_history_links,
                                     import_notes, HISTORY_URL)
from scripts.check_release_config import check_release_config


def app_version():
    tree = ast.parse((ROOT / "core/constants.py").read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "APP_VERSION" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("APP_VERSION missing")


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_manifest(zip_path, version, notes, released=None):
    if zip_path.name != f"TEGGTouch_v{version}.zip":
        raise ValueError("ZIP filename and APP_VERSION differ")
    if not notes.strip():
        raise ValueError("Release notes are required")
    check_release_config(zip_path)
    data = {"schema": 1, "product": "TEGGTouch", "channel": "stable", "version": version,
            "released": released or date.today().isoformat(), "notes": notes.strip(),
            "host": {"name": zip_path.name, "url": OSS_BASE + zip_path.name,
                     "size": zip_path.stat().st_size, "sha256": file_sha256(zip_path)}}
    parse_manifest(data)  # rejects preview releases, invalid size/date/URLs
    validate_archive(zip_path)
    return data


def current_manifest():
    try:
        with open_update_url(LATEST_URL, timeout=30) as response:
            raw = response.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError("Remote manifest is too large")
        data = json.loads(raw)
        parse_manifest(data)
        return data
    except HTTPError as error:
        if error.code == 404:
            return None  # first migration only; all other failures must abort
        raise


def check_promotion(data, current):
    if current is None:
        return
    new, old = parse_manifest(data), parse_manifest(current)
    if is_newer(old.version, new.version):
        raise ValueError("Refusing to downgrade latest.json")
    if old.version == new.version and (old.sha256 != new.sha256 or old.size != new.size):
        raise ValueError("A published version cannot be replaced with different bytes")


def verify_remote(release, allow_missing=False):
    digest, size = hashlib.sha256(), 0
    try:
        with open_update_url(release.url, timeout=60) as response:
            length = response.headers.get("Content-Length")
            if length is not None and int(length) != release.size:
                raise ValueError("Published ZIP size mismatch")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > release.size:
                    raise ValueError("Published ZIP is too large")
                digest.update(chunk)
    except HTTPError as error:
        if allow_missing and error.code == 404:
            return False
        raise
    if size != release.size or digest.hexdigest() != release.sha256.lower():
        raise ValueError("Published ZIP SHA256/size mismatch; refusing promotion")
    return True


def upload(path, key, *, manifest=False):
    # No keys/tokens on the command line. ossutil reads the existing local config.
    command = ["ossutil", "api", "put-object", "--bucket", "sea-of-time",
               "--key", "teggtouch/" + key, "--body", "file://" + str(Path(path).resolve()),
               "--object-acl", "public-read", "--cache-control",
               "no-cache" if manifest else "public, max-age=31536000, immutable"]
    if manifest:
        command += ["--content-type", "application/json; charset=utf-8"]
    else:
        command += ["--forbid-overwrite"]
    subprocess.run(command, check=True)


def publish_history(data):
    with tempfile.TemporaryDirectory(prefix='teggtouch-history-') as directory:
        path = Path(directory) / 'releases.json'
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        upload(path, 'releases.json', manifest=True)
    if fetch_history() != data:
        raise ValueError('Public releases.json differs from the expected history')


def sync_history():
    data = merge_history(fetch_history(), list_oss_history()['releases'])
    if not data['releases']:
        raise ValueError('No public stable releases found')
    verify_history_links(data)
    publish_history(data)
    return data


def publish(zip_path, data):
    release = parse_manifest(data)
    check_promotion(data, current_manifest())
    if not verify_remote(release, allow_missing=True):
        upload(zip_path, zip_path.name)
        verify_remote(release)
    # Recheck immediately before promotion; do not publish concurrently.
    check_promotion(data, current_manifest())
    history = merge_history(fetch_history(), [
        {'version': release.version, 'url': release.url, 'size': release.size,
         'notes': data['notes'], 'released': data['released']}])
    publish_history(history)  # verified ZIP -> history -> latest, never advertise missing files
    with tempfile.TemporaryDirectory(prefix="teggtouch-publish-") as directory:
        manifest = Path(directory) / "latest.json"
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        upload(manifest, "latest.json", manifest=True)
    if current_manifest() != data:
        raise ValueError("Public latest.json does not match this release")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path)
    parser.add_argument("--notes", type=Path)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--publish", action="store_true", help="Upload, append history and promote stable")
    actions.add_argument("--sync-history", action="store_true", help="Index existing public OSS ZIPs; does not change latest.json")
    actions.add_argument("--import-notes", type=Path, metavar="JSON",
                         help="Attach {version: {notes, released}} to existing history; does not change latest.json")
    args = parser.parse_args()
    if args.import_notes:
        data = import_notes(fetch_history(), json.loads(args.import_notes.read_text(encoding="utf-8-sig")))
        publish_history(data)
        print('Published notes for {} historical releases: {}'.format(
            sum('notes' in entry for entry in data['releases']), HISTORY_URL))
        return
    if args.sync_history:
        data = sync_history()
        print('Published {} historical releases: {}'.format(len(data['releases']), HISTORY_URL))
        return
    version = app_version()
    zip_path = args.zip or ROOT / "dist" / f"TEGGTouch_v{version}.zip"
    notes_path = args.notes or ROOT / "docs/release-notes" / f"{version}.md"
    data = make_manifest(zip_path, version, notes_path.read_text(encoding="utf-8-sig"))
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.publish:
        publish(zip_path, data)
        print("Published and verified:", LATEST_URL)
    else:
        print("DRY RUN: nothing uploaded. Use --publish only for an approved stable release.")


if __name__ == "__main__":
    main()
