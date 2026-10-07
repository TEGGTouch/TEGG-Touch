"""Regression checks for development credentials accidentally copied into releases."""

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.check_release_config import check_release_config
from scripts.publish_release import make_manifest


class ReleaseConfigTests(unittest.TestCase):
    def package(self, directory, entries):
        path = Path(directory) / 'TEGGTouch_v0.5.3.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('TEGGTouch.exe', b'test executable')
            for name, content in entries.items():
                archive.writestr(name, content)
        return path

    def test_legacy_agent_config_is_rejected_even_with_empty_keys(self):
        for prefix in ('', 'TEGGTouch_v0.5.3/', 'TEGGTouch_v0.5.3\\'):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as directory:
                path = self.package(directory, {prefix + 'settings/agent.json': b'{"api_key":""}'})
                with self.assertRaisesRegex(ValueError, 'Credential file'):
                    check_release_config(path)

    def test_private_fields_in_allowed_settings_or_profiles_prevent_manifest_creation(self):
        secret = 'development' + ' credential'
        for name, config in [
            ('settings/hotkeys.json', {'nested': {'api_key': secret}}),
            ('profiles/demo.json', {'config': {'asr_api_key': secret}}),
            ('profiles/demo.json', {'accessKeySecret': secret}),
            ('profiles/demo.json', {'auth': [{'refresh-token': secret}]}),
        ]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = self.package(directory, {name: json.dumps(config)})
                with self.assertRaises(ValueError) as caught:
                    make_manifest(path, '0.5.3', 'UI changes')
                self.assertNotIn(secret, str(caught.exception))

    def test_runtime_caches_and_credential_files_are_rejected_before_zip_creation(self):
        for name in ('settings/apps_cache.json', 'settings/last_update_check.json',
                     '.git/config', '.env.production', 'private.key'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                file = Path(directory) / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('{}', encoding='utf-8')
                with self.assertRaises(ValueError):
                    check_release_config(directory)

    def test_default_controls_hotkeys_and_public_ca_certificate_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.package(directory, {
                'settings/hotkeys.json': json.dumps({'stop': 'F12', 'language': 'zh-CN'}),
                'profiles/demo.json': json.dumps({'buttons': [{'key': 'space', 'name': 'Jump'}]}),
                '_internal/certifi/cacert.pem': b'-----BEGIN CERTIFICATE-----\npublic CA\n',
            })
            check_release_config(path)
            result = make_manifest(path, '0.5.3', 'UI changes')
            self.assertEqual(result['version'], '0.5.3')

    def test_private_key_content_is_rejected_without_printing_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.package(directory, {'_internal/certifi/cacert.pem':
                b'-----BEGIN ' + b'PRIVATE KEY-----\nprivate material\n'})
            with self.assertRaisesRegex(ValueError, 'Credential material'):
                check_release_config(path)


if __name__ == '__main__':
    unittest.main()
