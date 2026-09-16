"""Archive tracked source and the already published Windows release, without rebuilding it."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(ROOT))
assert os.environ.get('CI_COMMIT_REF_NAME', 'main') == 'main'
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
constants = subprocess.check_output(['git', 'show', 'HEAD:core/constants.py']).decode()
version = re.search(r'^APP_VERSION\s*=\s*[\'"]([0-9]+\.[0-9]+\.[0-9]+)[\'"]', constants, re.M).group(1)
tag = 'v' + version
asset_name = 'TEGGTouch_' + tag + '.zip'
api_url = 'https://api.github.com/repos/TEGGTouch/TEGG-Touch/releases/tags/' + tag

def request(url):
    return urlopen(Request(url, headers={'User-Agent': 'TEGGTouch-release-archive'}), timeout=45)

release = None
for attempt in range(3):
    try:
        with request(api_url) as response:
            release = json.load(response)
        break
    except HTTPError as error:
        if error.code == 404:
            break  # A development version can have source archived before its release exists.
        if attempt == 2:
            raise
        time.sleep(2)
    except OSError:
        if attempt == 2:
            raise
        time.sleep(2)

with tempfile.TemporaryDirectory(prefix='teggtouch-archive-') as work:
    work = Path(work)
    source = work / ('source-' + commit + '.tar.gz')
    subprocess.check_call(['git', 'archive', '--format=tar.gz', '--output=' + str(source), commit])
    manifest = {'sourceCommit': commit, 'branch': 'main', 'buildNumber': int(os.environ.get('BUILD_NUMBER', '0')),
                'applicationVersion': version, 'binaryArchived': False, 'files': {}}
    if release is not None:
        assert release['tag_name'] == tag and not release['draft']
        asset = next(a for a in release['assets'] if a['name'] == asset_name)
        expected = asset.get('digest', '')
        assert re.fullmatch(r'sha256:[0-9a-f]{64}', expected), 'Published GitHub asset has no SHA256 digest'
        binary = work / asset_name
        urls = ['https://sea-of-time.oss-cn-shanghai.aliyuncs.com/teggtouch/' + asset_name,
                asset['browser_download_url']]
        verified = False
        for url in urls:
            try:
                digest = hashlib.sha256()
                size = 0
                with request(url) as response, binary.open('wb') as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                assert size == asset['size'], 'Release size mismatch'
                assert digest.hexdigest() == expected.split(':', 1)[1], 'Release checksum mismatch'
                verified = True
                break
            except (OSError, AssertionError) as error:
                print('Release mirror unavailable or failed verification: ' + type(error).__name__)
        assert verified, 'Could not obtain a verified published Windows release'
        with zipfile.ZipFile(str(binary)) as package:
            assert any(Path(name).name.lower() == 'teggtouch.exe' for name in package.namelist())
        tag_commit = subprocess.check_output(['git', 'rev-parse', tag + '^{commit}']).decode().strip()
        manifest.update({'binaryArchived': True, 'publishedTag': tag, 'publishedTagCommit': tag_commit,
                         'githubRelease': release['html_url'], 'binarySha256': expected.split(':', 1)[1]})
    else:
        manifest['binaryStatus'] = 'No GitHub release for this version yet; rerun after publishing it.'
    for file in work.iterdir():
        digest = hashlib.sha256()
        with file.open('rb') as source_file:
            for chunk in iter(lambda: source_file.read(1024 * 1024), b''):
                digest.update(chunk)
        manifest['files'][file.name] = {'sha256': digest.hexdigest(), 'bytes': file.stat().st_size}
    (work / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    with tarfile.open(str(ROOT / 'teggtouch-desktop-archive.tar.gz'), 'w:gz') as archive:
        for file in work.iterdir():
            archive.add(str(file), arcname=file.name)
    print(json.dumps(manifest, indent=2))

