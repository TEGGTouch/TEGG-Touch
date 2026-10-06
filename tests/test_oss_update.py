"""No network, desktop input or installer execution. python -m unittest tests.test_oss_update"""

import copy
from dataclasses import replace
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
import zipfile

from PyQt6.QtWidgets import QApplication, QWidget
from core import update_checker as checker
from core import update_installer as installer
from core.update_manifest import (OSS_BASE, LATEST_URL, ReleaseInfo, parse_manifest,
                                   is_newer, validate_archive, open_update_url, _NoRedirect)
from scripts import publish_release as publisher


def zip_bytes(entries=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in (entries or {"TEGGTouch.exe": b"test executable", "_internal/runtime.dll": b"runtime"}).items():
            archive.writestr(name, data)
    return stream.getvalue()


def manifest(data=None, version="0.5.2"):
    data = zip_bytes() if data is None else data
    return {"schema": 1, "product": "TEGGTouch", "channel": "stable", "version": version,
            "released": "2026-10-07", "notes": "test release", "host": {
                "name": f"TEGGTouch_v{version}.zip", "url": OSS_BASE + f"TEGGTouch_v{version}.zip",
                "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}}


def response(data, length=None):
    stream = io.BytesIO(data)
    stream.headers = {} if length is None else {"Content-Length": str(length)}
    return stream


class ManifestTests(unittest.TestCase):
    def test_contract_and_version_order(self):
        self.assertEqual(parse_manifest(manifest()).version, "0.5.2")
        for remote, local, expected in (("0.5.2", "0.5.1", True), ("v0.5.2", "0.5.2-preview.2", True),
            ("0.5.1", "0.5.2-preview.2", False), ("0.5.2", "0.5.2", False),
            ("0.5.2", "0.5.2+build-tag", False), ("0.5.2-preview.3", "0.5.1", False),
            ("oops", "0.5.1", False), ("0.5.2", "bad", False)):
            with self.subTest(remote=remote, local=local):
                self.assertEqual(is_newer(remote, local), expected)

    def test_invalid_manifest_is_never_latest(self):
        for key, value in (("schema", True), ("schema", 2), ("product", "inpuTEGG"),
                           ("channel", "preview"), ("version", "0.5.2-preview.2"),
                           ("released", "bad-date"), ("host", None), ("notes", [])):
            data = manifest()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_manifest(data)
        for key, value in (("sha256", ""), ("sha256", None), ("size", True), ("size", 0),
            ("size", "123"), ("size", 2**31), ("name", "wrong.zip"),
            ("url", "https://github.com/a.zip"), ("url", OSS_BASE + "../bad.zip")):
            data = manifest()
            data["host"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_manifest(data)

    def test_untrusted_source_and_redirect_never_followed(self):
        with patch("urllib.request.build_opener") as opener:
            for url in ("http://example.com", "https://github.com", LATEST_URL + "?token=x"):
                with self.assertRaises(ValueError):
                    open_update_url(url)
            opener.assert_not_called()
        request = Mock(full_url=LATEST_URL)
        with self.assertRaises(HTTPError):
            _NoRedirect().redirect_request(request, None, 302, "redirect", {}, "https://example.com")

    def test_zip_layout_and_windows_paths(self):
        for entries in ({"../TEGGTouch.exe": b"x"}, {"C:/TEGGTouch.exe": b"x"},
            {"TEGGTouch.exe": b"x", "test:ads": b"x"}, {"TEGGTouch.exe": b"x", "a/../x": b"x"},
            {"TEGGTouch.exe": b"x", "file.": b"x"}, {"nested/deep/TEGGTouch.exe": b"x"},
            {"one/TEGGTouch.exe": b"x", "two/TEGGTouch.exe": b"x"}):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                validate_archive(io.BytesIO(zip_bytes(entries)))
        validate_archive(io.BytesIO(zip_bytes({"TEGGTouch_v0.5.2/TEGGTouch.exe": b"x"})))


class CheckerTests(unittest.TestCase):
    def test_network_parse_errors_emit_failure_not_up_to_date(self):
        for error in (TimeoutError("offline"), ValueError("bad json")):
            worker, failed, none = checker.UpdateChecker(force=True), Mock(), Mock()
            worker.check_failed.connect(failed)
            worker.no_update_available.connect(none)
            with patch.object(checker, "fetch_latest", side_effect=error), patch.object(checker, "_save_check_timestamp") as save:
                worker.run()
            failed.assert_called_once()
            none.assert_not_called()
            save.assert_not_called()

    def test_check_only_reads_oss_and_preserves_metadata(self):
        data, result = manifest(), []
        worker = checker.UpdateChecker(force=True)
        worker.update_available.connect(result.append)
        with patch.object(checker, "open_update_url", return_value=response(json.dumps(data).encode())) as fetch, \
             patch.object(checker, "APP_VERSION", "0.5.1"), patch.object(checker, "_save_check_timestamp"):
            worker.run()
        fetch.assert_called_once_with(LATEST_URL)
        self.assertEqual(result, [parse_manifest(data)])

    def test_bad_or_oversized_response(self):
        for raw in (b"not json", b"{}", b" " * (checker.MAX_MANIFEST_BYTES + 1)):
            with patch.object(checker, "open_update_url", return_value=response(raw)), self.assertRaises(ValueError):
                checker.fetch_latest()

    def test_old_cooldown_migrates_and_force_bypasses_new_cooldown(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(checker, "_COOLDOWN_FILE", str(Path(directory) / "check.json")):
            Path(checker._COOLDOWN_FILE).write_text(json.dumps({"last_check": time.time()}))
            self.assertTrue(checker._should_check())
            checker._save_check_timestamp()
            self.assertFalse(checker._should_check())
            with patch.object(checker, "fetch_latest", return_value=parse_manifest(manifest())) as fetch:
                checker.UpdateChecker().run()
                fetch.assert_not_called()
                checker.UpdateChecker(force=True).run()
                fetch.assert_called_once()


class DownloadTests(unittest.TestCase):
    def download(self, data, release=None, length=None, cancelled=None):
        release = release or parse_manifest(manifest(data))
        with tempfile.TemporaryDirectory() as directory:
            dest = str(Path(directory) / "update.zip")
            with patch.object(installer, "open_update_url", return_value=response(data, length)) as fetch:
                try:
                    installer.download_release(release, dest, cancelled=cancelled)
                except Exception:
                    self.assertFalse(Path(dest).exists())
                    self.assertFalse(Path(dest + ".part").exists())
                    raise
            fetch.assert_called_once_with(release.url, timeout=30)
            self.assertEqual(Path(dest).read_bytes(), data)
            self.assertFalse(Path(dest + ".part").exists())

    def test_complete_download_with_and_without_content_length(self):
        data = zip_bytes()
        self.download(data)
        self.download(data, length=len(data))

    def test_bad_checksum_size_partial_html_and_cancel(self):
        data = zip_bytes()
        release = parse_manifest(manifest(data))
        for payload, expected, length, cancel in ((data, replace(release, sha256="0" * 64), None, None),
            (data[:-8], release, None, None), (data + b"extra", release, None, None),
            (data, release, 1, None), (b"<html>not a zip</html>", None, None, None),
            (data, release, None, lambda: True)):
            with self.subTest(length=length, size=len(payload)), self.assertRaises(installer.UpdateError):
                self.download(payload, expected, length, cancel)

    def test_missing_digest_never_starts_network(self):
        release = replace(parse_manifest(manifest()), sha256="")
        with patch.object(installer, "open_update_url") as fetch, self.assertRaises(ValueError):
            installer.download_release(release, "unused.zip")
        fetch.assert_not_called()


class PublisherTests(unittest.TestCase):
    def test_preview_rejected_and_manifest_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            for version in ("0.5.2", "0.5.2-preview.2"):
                path = Path(directory) / f"TEGGTouch_v{version}.zip"
                path.write_bytes(zip_bytes())
                if "preview" in version:
                    with self.assertRaises(ValueError):
                        publisher.make_manifest(path, version, "notes")
                else:
                    self.assertEqual(parse_manifest(publisher.make_manifest(path, version, "notes")).version, version)

    def test_downgrade_and_same_version_replacement_rejected(self):
        with self.assertRaises(ValueError):
            publisher.check_promotion(manifest(version="0.5.1"), manifest())
        with self.assertRaises(ValueError):
            publisher.check_promotion(manifest(b"different bytes"), manifest())
        publisher.check_promotion(manifest(), None)
        publisher.check_promotion(manifest(), manifest())

    def test_publish_verifies_asset_before_promoting_latest(self):
        calls, data = [], manifest()
        def upload(path, key, **kwargs):
            calls.append(key)
        def verify(release, allow_missing=False):
            calls.append("check-existing" if allow_missing else "verify-zip")
            return not allow_missing
        with patch.object(publisher, "current_manifest", side_effect=[None, None, data]), \
             patch.object(publisher, "upload", side_effect=upload), \
             patch.object(publisher, "verify_remote", side_effect=verify):
            publisher.publish(Path("TEGGTouch_v0.5.2.zip"), data)
        self.assertEqual(calls, ["check-existing", "TEGGTouch_v0.5.2.zip", "verify-zip", "latest.json"])

    def test_failed_asset_verification_never_promotes(self):
        with patch.object(publisher, "current_manifest", return_value=None), \
             patch.object(publisher, "upload") as upload, \
             patch.object(publisher, "verify_remote", side_effect=[False, ValueError("bad zip")]), \
             self.assertRaises(ValueError):
            publisher.publish(Path("TEGGTouch_v0.5.2.zip"), manifest())
        self.assertEqual(upload.call_count, 1)
        self.assertEqual(upload.call_args.args[1], "TEGGTouch_v0.5.2.zip")


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_auto_manual_share_digest_and_single_active_dialog(self):
        from views.update_dialog import start_update_flow
        parent, release = QWidget(), parse_manifest(manifest())
        self.app._active_update_dialog = None
        with patch.object(installer, "UpdateInstaller") as worker:
            dlg = start_update_flow(parent, release)
            self.assertIs(start_update_flow(parent, release), dlg)
            dlg._on_install_clicked()
            dlg._on_install_clicked()
            worker.assert_called_once_with(release, parent=parent)
            self.assertFalse(dlg.close())
            dlg.on_failed("test failure")
            self.assertTrue(dlg.close())
        self.app._active_update_dialog = None
        parent.close()


if __name__ == "__main__":
    unittest.main()
