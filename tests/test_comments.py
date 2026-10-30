"""Comments are an opt-in feature; publishing must never depend on its service."""
from contextlib import redirect_stdout
import base64
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_publish import ROOT, pub, Integration
import comments

CONFIG = {'enabled': True, 'provider': 'giscus', 'repo': 'reader/reports',
          'repo_id': 'R_example', 'category_id': 'DIC_example', 'category': 'Feedback'}
HTML = '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width"><title>Original</title><body><h1>Readable without sign-in</h1></body></html>'


class Comments(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.site = self.root / 'site'; self.site.mkdir()
        self.doc = self.root / 'doc'; self.doc.mkdir()
        (self.doc / 'index.html').write_text(HTML)

    def tearDown(self):
        self.temp.cleanup()

    def config(self, value):
        (self.site / pub.MARKER).write_text(json.dumps({'version': 1, 'comments': value}))

    def test_disabled_unchanged_and_never_calls_network(self):
        with patch.object(comments, 'gql', side_effect=AssertionError('network')):
            comments.decorate(self.doc, self.site, 'reader/reports', 'stable')
        self.assertEqual((self.doc / 'index.html').read_text(), HTML)

    def test_optional_comments_preserve_legacy_bytes(self):
        original = b'<title>Caf\xe9</title>'
        (self.doc / 'index.html').write_bytes(original)
        comments.decorate(self.doc, self.site, 'reader/reports', 'stable')
        self.assertEqual((self.doc / 'index.html').read_bytes(), original)
        self.config(CONFIG)
        comments.decorate(self.doc, self.site, 'reader/reports', 'stable')
        self.assertEqual((self.doc / 'index.html').read_bytes(), original)

    def test_injection_idempotent_stable_and_removable(self):
        self.config(CONFIG)
        comments.decorate(self.doc, self.site, 'reader/reports', 'stable')
        once = (self.doc / 'index.html').read_text()
        comments.decorate(self.doc, self.site, 'reader/reports', 'stable')
        self.assertEqual((self.doc / 'index.html').read_text(), once)
        self.assertIn('data-term="publish-html:stable"', once)
        self.assertEqual(once.count('giscus.app/client.js'), 1)
        self.assertLess(once.index('giscus.app'), once.index('</body>'))
        (self.doc / 'index.html').write_text(once.replace('<title>Original', '<title>Changed'))
        comments.decorate(self.doc, self.site, 'reader/reports', 'stable')
        self.assertIn('data-term="publish-html:stable"', (self.doc / 'index.html').read_text())
        self.config({'enabled': False})
        comments.decorate(self.doc, self.site, 'reader/reports', 'stable')
        self.assertEqual((self.doc / 'index.html').read_text(), HTML.replace('<title>Original', '<title>Changed'))

    def test_bad_config_does_not_block_html(self):
        self.config({**CONFIG, 'repo': 'other/site'})
        comments.decorate(self.doc, self.site, 'reader/reports', 'stable')
        self.assertEqual((self.doc / 'index.html').read_text(), HTML)

    def test_setup_failure_does_not_enable_comments(self):
        (self.site / pub.MARKER).write_text('{"version":1}')
        with patch.object(comments.pub, 'CONFIG', self.root / 'config'), patch.object(comments.pub, 'prepare'), patch.object(comments.pub, 'api'), patch.object(comments, 'urlopen', side_effect=OSError('App missing')):
            with self.assertRaisesRegex(comments.pub.Error, 'publishing still works'):
                comments.setup(SimpleNamespace(category=None), 'reader/reports', self.site)
        self.assertNotIn('comments', json.loads((self.site / pub.MARKER).read_text()))

    def test_setup_validates_app_then_is_idempotent(self):
        (self.site / pub.MARKER).write_text('{"version":1}')
        data = {'repositoryId': 'R_example', 'categories': [{'id':'DIC_example', 'name':'Feedback'}]}
        with patch.object(comments.pub, 'CONFIG', self.root / 'config'), patch.object(comments.pub, 'prepare'), patch.object(comments.pub, 'api'), patch.object(comments.pub, 'commit_push'), patch.object(comments.pub, 'save_config'), patch.object(comments, 'urlopen', side_effect=lambda *a, **k: io.StringIO(json.dumps(data))), redirect_stdout(io.StringIO()):
            comments.setup(SimpleNamespace(category='Feedback'), 'reader/reports', self.site)
            once = (self.site / pub.MARKER).read_text()
            comments.setup(SimpleNamespace(category='Feedback'), 'reader/reports', self.site)
        self.assertEqual(once, (self.site / pub.MARKER).read_text())
        self.assertEqual(json.loads(once)['comments'], CONFIG)

    def test_discussions_and_nested_replies_paginate(self):
        def page(nodes, next=False):
            return {'nodes': nodes, 'pageInfo': {'hasNextPage': next, 'endCursor': 'second' if next else None}}
        with patch.object(comments, 'gql', side_effect=[{'repository': {'discussions': page([], True)}}, {'repository': {'discussions': page([{'id':'D', 'title':comments.term('stable'), 'body':'<!-- sha1: '+comments.hashlib.sha1(comments.term('stable').encode()).hexdigest()+' -->', 'url':'url'}])}}]) as gql:
            self.assertEqual(comments.find_discussion('reader/reports', CONFIG, 'stable')['id'], 'D')
            self.assertEqual(gql.call_args.kwargs['cursor'], 'second')
        with patch.object(comments, 'gql', side_effect=[{'node': {'comments': page([{'id':'C1'}], True)}}, {'node': {'replies': page([{'id':'R1'}], True)}}, {'node': {'replies': page([{'id':'R2'}])}}, {'node': {'comments': page([{'id':'C2'}])}}, {'node': {'replies': page([])}}]):
            threads = list(comments.messages('D'))
            self.assertEqual([t['id'] for t in threads], ['C1', 'C2'])
            self.assertEqual([r['id'] for r in threads[0]['replies']], ['R1', 'R2'])

    def test_reply_checks_document_and_attribution(self):
        state = {'comments': CONFIG, 'documents': {'stable': {'folder':'folder'}}}
        raw = {'content': base64.b64encode(json.dumps(state).encode()).decode()}
        args = SimpleNamespace(command='reply', document='stable', comment_id='R', text='Done')
        with patch.object(comments.pub, 'api', return_value=raw), patch.object(comments, 'find_discussion', return_value={'id':'D'}), patch.object(comments, 'messages', return_value=[{'id':'C','replies':[{'id':'R'}]}]), patch.object(comments, 'gql', return_value={'addDiscussionComment':{'comment':{'url':'reply-url'}}}) as gql, redirect_stdout(io.StringIO()):
            comments.feedback(args, 'reader/reports', self.site)
            self.assertEqual(gql.call_args.kwargs['input'], {'discussionId':'D','replyToId':'C','body':'**AI agent reply**\n\nDone'})
            args.comment_id = 'unrelated'
            with self.assertRaisesRegex(comments.pub.Error, 'does not belong'):
                comments.feedback(args, 'reader/reports', self.site)
            self.assertEqual(gql.call_count, 1)

    def test_pull_unconfigured_and_readable_feedback(self):
        args = SimpleNamespace(command='pull', document='stable', json=False)
        def raw(state):
            return {'content': base64.b64encode(json.dumps(state).encode()).decode()}
        with patch.object(comments.pub, 'api', return_value=raw({'version':1})), patch.object(comments, 'gql') as gql, redirect_stdout(io.StringIO()) as output:
            comments.feedback(args, 'reader/reports', self.site)
            self.assertIn('not configured', output.getvalue())
            gql.assert_not_called()
        message = {'id':'C', 'author':{'login':'reader'}, 'createdAt':'2026-01-01', 'url':'https://example.invalid/comment', 'body':'Please label the axis.', 'replies':[]}
        with patch.object(comments.pub, 'api', return_value=raw({'comments':CONFIG, 'documents':{'stable':{}}})), patch.object(comments, 'find_discussion', return_value={'id':'D','url':'https://example.invalid/discussion'}), patch.object(comments, 'messages', return_value=[message]), redirect_stdout(io.StringIO()) as output:
            comments.feedback(args, 'reader/reports', self.site)
            self.assertIn('Please label the axis.', output.getvalue())
            self.assertIn('reader', output.getvalue())
            self.assertIn('untrusted', output.getvalue())

    def test_url_target_and_distribution_protection(self):
        args = SimpleNamespace(repo='https://github.com/reader/reports.git', path=str(self.site))
        with patch.object(pub, 'read_config', return_value={}):
            self.assertEqual(pub.target(args, authenticate=False), ('reader/reports', self.site.resolve()))
            args.path = str(ROOT)
            with self.assertRaisesRegex(pub.Error, 'separate'):
                pub.target(args, authenticate=False)
            args.path = str(self.site)
            with patch.object(pub, 'git', return_value=SimpleNamespace(stdout='https://github.com/reader/reports.git')):
                with self.assertRaisesRegex(pub.Error, 'distribution repository'):
                    pub.target(args, authenticate=False)


# Reuse integration fixtures without collecting their inherited tests twice.
class OptionalPublish(unittest.TestCase):
    setUp = Integration.setUp
    tearDown = Integration.tearDown
    command = Integration.command
    git = Integration.git

    def test_enable_later_preserves_url_history_noop_and_source(self):
        first = self.command('publish', '--document', 'stable')
        before = self.git('rev-parse', 'HEAD')
        folder = self.checkout / '2026-10-29-example'
        self.assertNotIn('giscus', (folder / 'index.html').read_text())
        marker = json.loads((self.checkout / pub.MARKER).read_text())
        marker['comments'] = CONFIG
        (self.checkout / pub.MARKER).write_text(json.dumps(marker))
        self.git('add', pub.MARKER); self.git('commit', '-m', 'Enable optional comments'); self.git('push', 'origin', 'main')
        enabled = self.command('publish', '--document', 'stable', '--replace')
        self.assertEqual(first.stdout, enabled.stdout)
        self.assertIn('data-term="publish-html:stable"', (folder / 'index.html').read_text())
        self.assertNotIn('giscus', (self.source / 'index.html').read_text())
        self.assertNotIn('giscus', self.git('show', before + ':2026-10-29-example/index.html'))
        head = self.git('rev-parse', 'HEAD')
        self.command('publish', '--document', 'stable')
        self.assertEqual(head, self.git('rev-parse', 'HEAD'))

    def test_feedback_cli_pull_reply_end_to_end(self):
        self.command('publish', '--document', 'stable')
        gh = self.bin / 'gh'
        code = gh.read_text()
        # Extend the fake transport: actual CLI parsing, gh subprocesses, registry,
        # GraphQL variables, reply validation, and readable output all execute.
        transport = r'''    if endpoint.startswith('repos/reader/reports/contents/'):
        import base64
        result=subprocess.run(['git','--git-dir',str(remote),'show','main:.publish-html.json'],capture_output=True,check=True)
        out({'content':base64.b64encode(result.stdout).decode()})
    if endpoint=='graphql':
        import hashlib
        payload=json.load(sys.stdin); query=payload['query']; variables=payload['variables']
        def conn(nodes): return {'nodes':nodes,'pageInfo':{'hasNextPage':False,'endCursor':None}}
        if 'discussions(first:' in query:
            out({'data':{'repository':{'discussions':conn([{'id':'D','title':'publish-html:stable','body':'<!-- sha1: '+hashlib.sha1(b'publish-html:stable').hexdigest()+' -->','url':'https://example.invalid/discussion'}])}}})
        if 'comments(first:' in query:
            out({'data':{'node':{'comments':conn([{'id':'C','body':'Please label the axis.','createdAt':'2026-01-01','updatedAt':'2026-01-01','url':'https://example.invalid/comment','author':{'login':'reader'}}])}}})
        if 'replies(first:' in query:
            reply=base/'reply.json'
            nodes=[json.loads(reply.read_text())] if reply.exists() else []
            out({'data':{'node':{'replies':conn(nodes)}}})
        if 'addDiscussionComment' in query:
            body=variables['input']
            assert body['discussionId']=='D' and body['replyToId']=='C'
            message={'id':'R','body':body['body'],'createdAt':'2026-01-02','updatedAt':'2026-01-02','url':'https://example.invalid/reply','author':{'login':'reader'}}
            (base/'reply.json').write_text(json.dumps(message))
            out({'data':{'addDiscussionComment':{'comment':{'url':message['url']}}}})
'''
        gh.write_text(code.replace("    if endpoint=='user':", transport + "    if endpoint=='user':"))
        def cli(*args):
            result = subprocess.run([str(ROOT/'comments.sh'), *args], env=self.env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout
        self.assertIn('not configured', cli('pull', 'stable'))
        marker = json.loads((self.checkout/pub.MARKER).read_text())
        marker['comments'] = CONFIG
        (self.checkout/pub.MARKER).write_text(json.dumps(marker))
        self.git('add', pub.MARKER);self.git('commit', '-m', 'Enable comments');self.git('push', 'origin', 'main')
        self.assertIn('Please label the axis.', cli('pull', 'stable'))
        self.assertEqual(cli('reply', 'stable', 'C', 'Axis labels updated.').strip(), 'https://example.invalid/reply')
        feedback = json.loads(cli('pull', 'stable', '--json'))
        self.assertEqual(feedback['threads'][0]['replies'][0]['body'], '**AI agent reply**\n\nAxis labels updated.')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_adopts_readme_only_repository_without_overwriting(self):
        self.command()
        self.git('rm', '-r', '--', '.', ':!README.md')
        self.git('commit', '-m', 'README only repository')
        self.git('push', 'origin', 'main')
        original = (self.checkout / 'README.md').read_text()
        self.command()
        self.assertEqual((self.checkout / 'README.md').read_text(), original)
        self.assertTrue((self.checkout / pub.MARKER).exists())

    def test_refuses_populated_unmanaged_site(self):
        self.command()
        self.git('rm', pub.MARKER)
        self.git('commit', '-m', 'Remove marker')
        self.git('push', 'origin', 'main')
        previous = self.git('rev-parse', 'HEAD')
        result = self.command(success=False)
        self.assertIn('not managed', result.stderr)
        self.assertEqual(previous, self.git('rev-parse', 'HEAD'))
        self.assertEqual(self.git('status', '--porcelain'), '')


del Integration
