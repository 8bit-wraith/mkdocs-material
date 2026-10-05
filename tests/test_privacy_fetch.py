import ast
import errno
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class FetchTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).parents[1] / 'src/plugins/privacy/plugin.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PrivacyPlugin')
        fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_fetch')
        self.requests = SimpleNamespace(get=Mock())
        scope = dict(os=os, errno=errno, log=Mock(), requests=self.requests,
                     File=object, MkDocsConfig=object, extensions={'text/css': '.css'})
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'plugin.py', 'exec'), scope)
        self.fetch = scope['_fetch']
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = SimpleNamespace(abs_src_path=self.temp.name+'/asset.css',
            abs_dest_path=self.temp.name+'/site/asset.css', src_uri='asset.css',
            dest_uri='assets/asset.css', url='https://example.invalid/asset.css')
        self.plugin = SimpleNamespace(config=SimpleNamespace(cache=True),
            _save_to_file=Mock(side_effect=lambda p, data: Path(p).write_bytes(data)),
            _parse_media=Mock(return_value=[]))
        self.response = SimpleNamespace(headers={'content-type':'text/css'},
            content=b'body {}', raise_for_status=Mock())
        self.requests.get.return_value = self.response

    def test_success_has_finite_timeout_and_caches(self):
        self.fetch(self.plugin, self.file, None)
        timeout = self.requests.get.call_args.kwargs.get('timeout')
        self.assertIsNotNone(timeout)
        self.assertTrue(all(0 < n <= 60 for n in timeout))
        self.response.raise_for_status.assert_called_once_with()
        self.assertEqual(Path(self.file.abs_src_path).read_bytes(), b'body {}')

    def test_http_error_never_caches(self):
        self.response.raise_for_status.side_effect = RuntimeError('HTTP 503')
        with self.assertRaisesRegex(RuntimeError, '503'):
            self.fetch(self.plugin, self.file, None)
        self.plugin._save_to_file.assert_not_called()
        self.assertFalse(Path(self.file.abs_src_path).exists())

    def test_timeout_never_caches(self):
        self.requests.get.side_effect = TimeoutError('read timeout')
        with self.assertRaises(TimeoutError):
            self.fetch(self.plugin, self.file, None)
        self.plugin._save_to_file.assert_not_called()

    def test_cache_hit_avoids_network(self):
        Path(self.file.abs_src_path).write_bytes(b'cached')
        self.fetch(self.plugin, self.file, None)
        self.requests.get.assert_not_called()
        self.assertEqual(Path(self.file.abs_src_path).read_bytes(), b'cached')


if __name__ == '__main__':
    unittest.main()
