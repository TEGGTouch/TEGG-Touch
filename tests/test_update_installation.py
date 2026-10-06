"""Exercise the real PowerShell/robocopy updater in isolated folders, never start the app."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from core.update_installer import _UPDATER_PS1


@unittest.skipUnless(os.name == 'nt', 'Windows updater integration')
class InstallationTests(unittest.TestCase):
    def test_embedded_and_shipped_script_match(self):
        template = Path(__file__).resolve().parents[1] / 'scripts/updater_template.ps1'
        def code(text):
            return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        self.assertEqual(code(_UPDATER_PS1), code(template.read_text(encoding='utf-8-sig')))

    def run_update(self, nested=False, fail_copy=False):
        with tempfile.TemporaryDirectory(prefix='teggtouch-install-test-') as folder:
            root = Path(folder)
            installed = root / '中文 folder with spaces'
            installed.mkdir()
            sentinels = {'config.json': b'old config', 'config.json.bak': b'old backup',
                         'profiles/mine.json': b'old profile', 'settings/hotkeys.json': b'old settings',
                         'logs/user.log': b'old log'}
            for name, data in sentinels.items():
                target = installed / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            (installed / 'TEGGTouch.exe').write_bytes(b'old program')
            package = root / 'update.zip'
            with zipfile.ZipFile(package, 'w') as archive:
                prefix = 'TEGGTouch_v0.5.2/' if nested else ''
                archive.writestr(prefix + 'TEGGTouch.exe', b'new program')
                archive.writestr(prefix + '_internal/new.dll', b'new dependency')
                for name in sentinels:
                    archive.writestr(prefix + name, b'must not overwrite')
            # No interactive window or real executable. Only robocopy runs for real.
            script = _UPDATER_PS1.replace('$splash.Show()', '$splash.Hide()')
            script = script.replace('$LogPath = Join-Path $env:TEMP "teggtouch_updater.log"',
                                    '$LogPath = Join-Path $InstallDir "test-updater.log"')
            intercept = '''
function Start-Process {
    param($FilePath, $ArgumentList, [switch]$NoNewWindow, [switch]$PassThru, [switch]$Wait, $WorkingDirectory)
    if ($FilePath -eq 'robocopy') {
        COPY_COMMAND
    } else {
        Set-Content -LiteralPath (Join-Path $WorkingDirectory 'test-started') -Value 'started'
    }
}
'''
            copy_command = ('return [PSCustomObject]@{ExitCode=8}' if fail_copy else
                'Microsoft.PowerShell.Management\\Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -NoNewWindow -PassThru -Wait')
            script = script.replace('$ErrorActionPreference = "Continue"',
                                    intercept.replace('COPY_COMMAND', copy_command) + '\n$ErrorActionPreference = "Continue"')
            path = root / 'test.ps1'
            path.write_text(script, encoding='utf-8-sig')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-WindowStyle', 'Hidden', '-File', str(path), '-WaitPid', '99999999', '-ZipPath', str(package),
                '-InstallDir', str(installed), '-ExePath', str(installed / 'TEGGTouch.exe')],
                capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 4 if fail_copy else 0, result.stderr.decode(errors='replace'))
            for name, data in sentinels.items():
                self.assertEqual((installed / name).read_bytes(), data)
            self.assertEqual((installed / 'TEGGTouch.exe').read_bytes(), b'old program' if fail_copy else b'new program')
            self.assertEqual((installed / '.update_applied').exists(), not fail_copy)
            self.assertEqual((installed / 'test-started').exists(), not fail_copy)
            self.assertEqual(package.exists(), fail_copy)

    def test_flat_package_preserves_profiles_and_settings(self):
        self.run_update()

    def test_nested_package_and_chinese_space_path(self):
        self.run_update(nested=True)

    def test_copy_failure_never_marks_success_or_restarts(self):
        self.run_update(fail_copy=True)


if __name__ == '__main__':
    unittest.main()
