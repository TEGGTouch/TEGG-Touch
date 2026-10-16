"""Public historical OSS download index. No bucket listing is exposed to browsers."""
import json
import re
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from core.update_manifest import OSS_BASE, open_update_url

HISTORY_URL = OSS_BASE + 'releases.json'
MAX_HISTORY_BYTES = 1024 * 1024
MAX_NOTES_CHARS = 20000
VERSION = r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'


def validate_history(data):
    if (not isinstance(data, dict) or type(data.get('schema')) is not int or data['schema'] != 1
            or data.get('product') != 'TEGGTouch' or not isinstance(data.get('releases'), list)
            or len(data['releases']) > 5000):
        raise ValueError('Invalid release history')
    seen = set()
    for item in data['releases']:
        if not isinstance(item, dict) or not isinstance(item.get('version'), str) or not re.fullmatch(VERSION, item['version']):
            raise ValueError('Only stable versions belong in release history')
        if item['version'] in seen:
            raise ValueError('Duplicate historical version')
        seen.add(item['version'])
        if (item.get('url') != OSS_BASE + 'TEGGTouch_v' + item['version'] + '.zip'
                or type(item.get('size')) is not int or not 0 < item['size'] < 2**31):
            raise ValueError('Invalid historical download')
        # Optional release notes (plain Markdown text, rendered as text by the website) and date.
        if 'notes' in item and (not isinstance(item['notes'], str) or len(item['notes']) > MAX_NOTES_CHARS):
            raise ValueError('Invalid historical release notes')
        if 'released' in item and (not isinstance(item['released'], str)
                                   or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', item['released'])):
            raise ValueError('Invalid historical release date')
    return data


def fetch_history():
    try:
        with open_update_url(HISTORY_URL, timeout=30) as response:
            raw = response.read(MAX_HISTORY_BYTES + 1)
        if len(raw) > MAX_HISTORY_BYTES:
            raise ValueError('Release history is too large')
        return validate_history(json.loads(raw))
    except HTTPError as error:
        if error.code == 404:
            return {'schema': 1, 'product': 'TEGGTouch', 'releases': []}
        raise


def merge_history(existing, items):
    validate_history(existing)
    validate_history({'schema': 1, 'product': 'TEGGTouch', 'releases': items})
    entries = {entry['version']: entry for entry in existing['releases']}
    for item in items:
        old = entries.get(item['version'])
        if old and (old['url'] != item['url'] or old['size'] != item['size']):
            raise ValueError('Historical versions cannot be replaced')
        entries[item['version']] = dict(old or {}, **item)  # keep notes not supplied again
    return validate_history({'schema': 1, 'product': 'TEGGTouch', 'releases': sorted(
        entries.values(), key=lambda entry: tuple(map(int, entry['version'].split('.'))), reverse=True)})


def list_oss_history():
    """One-time/import maintenance: list only this product's versioned ZIP prefix."""
    entries, token, seen_tokens = [], None, set()
    while True:
        command = ['ossutil', 'api', 'list-objects-v2', '--bucket', 'sea-of-time',
                   '--prefix', 'teggtouch/TEGGTouch_v', '--max-keys', '1000', '--output-format', 'json']
        if token:
            command += ['--continuation-token', token]
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        # ossutil 2.x appends a timing line after the JSON document on stdout.
        page, _ = json.JSONDecoder().raw_decode(result.stdout.lstrip())
        for item in page.get('Contents') or []:
            match = re.fullmatch(r'teggtouch/TEGGTouch_v(' + VERSION + r')\.zip', item['Key'])
            if match:
                entries.append({'version': match.group(1), 'url': OSS_BASE + item['Key'].split('/')[-1],
                                'size': int(item['Size'])})
        if page.get('IsTruncated') not in (True, 'true'):
            break
        token = page.get('NextContinuationToken')
        if not token or token in seen_tokens:
            raise ValueError('Invalid OSS listing continuation')
        seen_tokens.add(token)
    return merge_history({'schema': 1, 'product': 'TEGGTouch', 'releases': []}, entries)


def import_notes(existing, notes):
    """Attach notes/dates ({version: {'notes', 'released'}}) to versions already in history."""
    validate_history(existing)
    entries = {entry['version']: entry for entry in existing['releases']}
    unknown = sorted(set(notes) - set(entries))
    if unknown:
        raise ValueError('Notes for versions not in history: ' + ', '.join(unknown))
    items = []
    for version, extra in notes.items():
        item = dict(entries[version])
        item.update({key: extra[key] for key in ('notes', 'released') if key in extra})
        items.append(item)
    return merge_history(existing, items)


def verify_history_links(data):
    for entry in validate_history(data)['releases']:
        with urlopen(Request(entry['url'], method='HEAD'), timeout=30) as response:
            if response.geturl() != entry['url'] or int(response.headers.get('Content-Length', '-1')) != entry['size']:
                raise ValueError('Historical ZIP is not publicly available: ' + entry['version'])
