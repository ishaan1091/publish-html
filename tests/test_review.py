"""Regression checks for concrete external-review findings."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_publish import pub, installer, ROOT

HTML='<html lang="en"><meta name="viewport" content="width=device-width"><title>Evidence report</title>{}</html>'


class Review(unittest.TestCase):
    def test_staging_htm_and_ambiguous_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'index.htm').write_text(HTML.format(''))
            with pub.stage_source(root) as (_,stage,title,manifest):
                self.assertEqual(title,'Evidence report');self.assertIn('index.html',manifest)
                self.assertFalse((stage/'index.htm').exists())
            (root/'index.html').write_text(HTML.format(''))
            with self.assertRaises(pub.Error):
                with pub.stage_source(root): pass

    def test_large_secret_and_chunk_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'large.bin'
            path.write_bytes(b'x'*(6*1024*1024-5)+('ghp_'+'A'*30).encode())
            self.assertTrue(pub.static_check.has_secret(path))
            with self.assertRaises(pub.Error): pub.inspect_source(root)
            path.write_bytes(b'x'*65532+('ghp_'+'A'*30).encode())
            self.assertTrue(pub.static_check.has_secret(path))

    def test_catalog_roots_legacy_encoding_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);doc=root/'2026-10-29-report';(doc/'sub').mkdir(parents=True)
            (doc/'index.html').write_bytes(b'<title>Caf\xe9</title>')
            (doc/'sub/index.html').write_text('<title>Nested</title>')
            (root/'site.json').write_text(json.dumps({'title':'My research','description':'Evidence','accent':'bad CSS'}))
            self.assertEqual(pub.catalog.generate(root),1)
            result=(root/'index.html').read_text()
            self.assertIn('My research',result);self.assertNotIn('Nested',result)
            self.assertIn('1 document<',result);self.assertIn('datetime="2026-10-29"',result)
            self.assertIn('Caf',result);self.assertNotIn('--accent:bad CSS',result)

    def test_checker_refs_fragments_accessibility_and_css(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'style.css').write_text('a{background:url(missing.png)}')
            (root/'Image.svg').write_text('<svg/>')
            (root/'index.html').write_text(HTML.format('<link href="style.css" rel="stylesheet"><img src="Image.svg"><a href="#absent">x</a><p id="same"></p><p id="same"></p><img alt="x" src="/img.png">'))
            codes={x['code'] for x in pub.static_check.check(root)}
            self.assertTrue({'E001','E003','E004','E005','E009'}.issubset(codes))
            (root/'index.html').write_text(HTML.format('<img alt="x" src="image.svg">'))
            codes={x['code'] for x in pub.static_check.check(root)}
            # Case-sensitive hosts report missing; case-insensitive hosts report exact-case error.
            self.assertTrue({'E001','E002'} & codes)

    def test_pages_failure_after_push_saves_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'config';config.mkdir()
            with patch.object(pub,'CONFIG',config),patch.object(pub,'pages',side_effect=pub.Error('HTTP 403')):
                with self.assertRaisesRegex(pub.Error,'Pushed successfully; Pages configuration failed'):
                    pub.deployed_base('reader/reports',Path(tmp)/'checkout')
            self.assertEqual(json.loads((config/'config.json').read_text())['repo'],'reader/reports')

    def test_bounded_get_retry_and_no_retry_permission_error(self):
        error=subprocess.CompletedProcess([],1,'','HTTP 503')
        okay=subprocess.CompletedProcess([],0,'{"ok":true}','')
        with patch.object(pub,'run',side_effect=[error,error,okay]) as run,patch.object(pub.time,'sleep') as sleep:
            self.assertEqual(pub.api('user'),{'ok':True});self.assertEqual(run.call_count,3);self.assertEqual(sleep.call_count,2)
        with patch.object(pub,'run',return_value=subprocess.CompletedProcess([],1,'','HTTP 403')) as run:
            with self.assertRaises(pub.Error): pub.api('user')
            self.assertEqual(run.call_count,1)

    def test_asset_verification_reads_every_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'index.html').write_text('page');(root/'data.csv').write_text('data')
            with patch.object(pub,'verify') as verify:
                pub.verify_tree('https://example.invalid/report/',root,10)
            self.assertEqual({call.args[0] for call in verify.call_args_list},{'https://example.invalid/report/index.html','https://example.invalid/report/data.csv'})

    def test_generic_install_uninstall_and_windows_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);link=home/'custom-harness/publish-html'
            with redirect_stdout(io.StringIO()):
                installer.install(None,home,link);installer.install(None,home,link)
                self.assertEqual(link.resolve(),ROOT)
                installer.install(None,home,link,True)
            self.assertFalse(link.is_symlink())
            with patch.object(pub,'fcntl',None),self.assertRaisesRegex(pub.Error,'native Windows'):
                with pub.lock('reader/reports'): pass

    def test_document_registration_survives_date_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / pub.MARKER).write_text('{"version":1}')
            pub.register_document(root, 'stable', '2026-10-01-original', 'Original')
            class LaterDate(pub.dt.date):
                @classmethod
                def today(cls): return cls(2030, 1, 1)
            with patch.object(pub.dt, 'date', LaterDate):
                self.assertEqual(pub.document_target(root, 'New title', document='stable'), ('stable', '2026-10-01-original'))
            with self.assertRaises(pub.Error):
                pub.document_target(root, 'New title', folder='another-folder', document='stable')

    def test_all_starters_pass_static_check(self):
        for kind in ('report','deck','dashboard'):
            with tempfile.TemporaryDirectory() as tmp:
                destination=Path(tmp)/'draft'
                subprocess.run([sys.executable,str(ROOT/'scripts/new.py'),str(destination),'--type',kind,'--title','My <report>'],check=True,capture_output=True)
                self.assertIn('My &lt;report&gt;', (destination/'index.html').read_text())
                self.assertFalse([x for x in pub.static_check.check(destination) if x['level']=='error'])
