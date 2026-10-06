import json
import unittest
from unittest.mock import Mock, patch

from core.update_manifest import OSS_BASE
from scripts import release_history as history
from scripts import publish_release as publisher


def entry(version, size=100):
    return {'version': version, 'url': OSS_BASE + 'TEGGTouch_v' + version + '.zip', 'size': size}


def index(items=None):
    return {'schema': 1, 'product': 'TEGGTouch', 'releases': items or []}


class HistoryTests(unittest.TestCase):
    def test_merge_preserves_old_versions_and_sorts_numerically(self):
        result = history.merge_history(index([entry('0.5.2'), entry('0.4.8')]), [entry('0.5.10')])
        self.assertEqual([i['version'] for i in result['releases']], ['0.5.10', '0.5.2', '0.4.8'])
        self.assertEqual(history.merge_history(result, [entry('0.5.2')]), result)

    def test_rejects_preview_duplicate_foreign_url_and_replacement(self):
        for entries in ([entry('0.5.3-preview.1')], [entry('0.5.2'), entry('0.5.2')],
                        [dict(entry('0.5.2'), url='https://example.com/a.zip')]):
            with self.assertRaises(ValueError):
                history.validate_history(index(entries))
        with self.assertRaises(ValueError):
            history.merge_history(index([entry('0.5.2')]), [entry('0.5.2', 200)])

    def test_listing_pagination_skips_unrelated_and_preview_objects(self):
        pages = [
            {'Contents': [{'Key': 'teggtouch/TEGGTouch_v0.5.2.zip', 'Size': '100'},
                          {'Key': 'teggtouch/TEGGTouch_v0.5.3-preview.1.zip', 'Size': '100'}],
             'IsTruncated': 'true', 'NextContinuationToken': 'next'},
            {'Contents': [{'Key': 'teggtouch/TEGGTouch_v0.4.8.zip', 'Size': '100'}], 'IsTruncated': 'false'}]
        with patch.object(history.subprocess, 'run', side_effect=[Mock(stdout=json.dumps(p) + '\n0.42(s) elapsed\n') for p in pages]) as run:
            result = history.list_oss_history()
        self.assertEqual([i['version'] for i in result['releases']], ['0.5.2', '0.4.8'])
        self.assertIn('--continuation-token', run.call_args.args[0])

    def test_sync_does_not_publish_latest_or_change_binaries(self):
        data = index([entry('0.5.2')])
        with patch.object(publisher, 'fetch_history', return_value=index()), \
             patch.object(publisher, 'list_oss_history', return_value=data), \
             patch.object(publisher, 'verify_history_links') as verify, \
             patch.object(publisher, 'publish_history') as publish, \
             patch.object(publisher, 'current_manifest') as latest:
            self.assertEqual(publisher.sync_history(), data)
        verify.assert_called_once_with(data)
        publish.assert_called_once_with(data)
        latest.assert_not_called()

    def test_unavailable_history_link_never_publishes_index(self):
        with patch.object(publisher, 'fetch_history', return_value=index()), \
             patch.object(publisher, 'list_oss_history', return_value=index([entry('0.5.2')])), \
             patch.object(publisher, 'verify_history_links', side_effect=ValueError('404')), \
             patch.object(publisher, 'publish_history') as publish, self.assertRaises(ValueError):
            publisher.sync_history()
        publish.assert_not_called()

    def test_failed_history_write_does_not_promote_latest(self):
        from tests.test_oss_update import manifest
        from pathlib import Path
        with patch.object(publisher, 'current_manifest', return_value=None), \
             patch.object(publisher, 'verify_remote', return_value=True), \
             patch.object(publisher, 'fetch_history', return_value=index()), \
             patch.object(publisher, 'publish_history', side_effect=ValueError('upload failed')), \
             patch.object(publisher, 'upload') as upload, self.assertRaises(ValueError):
            publisher.publish(Path('TEGGTouch_v0.5.2.zip'), manifest())
        upload.assert_not_called()


if __name__ == '__main__':
    unittest.main()
