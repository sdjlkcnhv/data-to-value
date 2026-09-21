"""Run with the initialized common runtime: python -m unittest discover -s tests -v."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from read_data import read_data
from runtime_probe import fixtures, run
from configure_preferences import PROFILES
import setup_environment as setup


class Compatibility(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='data-to-value-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, name, text):
        path = self.root / name
        path.write_bytes(text.encode('utf-8'))
        return path

    def test_common_fixtures_and_read_only(self):
        for suffix, path in fixtures(self.root, 'common').items():
            with self.subTest(format=suffix):
                before = hashlib.sha256(path.read_bytes()).hexdigest()
                result = read_data(path)
                self.assertEqual(result['status'], 'read', result)
                content = [unit.get('records', unit.get('text')) for unit in result['units']]
                self.assertIn('sample', json.dumps(content).lower())
                self.assertFalse(result['audit_complete'])
                self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_csv_duplicate_columns_multiline_and_sample(self):
        path = self.file('source.csv', 'a,a\n"two\nlines",001\nx,002\n')
        result = read_data(path, limit=1)
        self.assertEqual(result['status'], 'partial')
        unit = result['units'][0]
        self.assertEqual(unit['columns'], ['a','a'])
        self.assertEqual(unit['records'], [['two\nlines','001']])
        self.assertIsNone(unit['total_records'])

    def test_encoding_is_not_silently_guessed(self):
        path = self.root/'source.csv'
        path.write_bytes('名字,值\n测试,1\n'.encode('gb18030'))
        self.assertEqual(read_data(path)['status'], 'encoding_error')
        self.assertEqual(read_data(path, encoding='gb18030')['status'], 'read')

    def test_malformed_json_and_duplicate_keys(self):
        for text in ['{"a":1,"a":2}', '[NaN]', '{']:
            result = read_data(self.file('source.json', text))
            self.assertNotIn(result['status'], ['read','partial'])

    def test_limits_and_unsupported(self):
        self.assertEqual(read_data(self.file('a.json','[]'),max_bytes=1)['status'], 'size_limit')
        self.assertEqual(read_data(self.file('a.unknown','x'))['status'], 'unsupported_format')
        self.assertEqual(read_data(self.file('a.png','invalid'))['status'], 'needs_ocr')

    def test_corrupt_files_are_not_read(self):
        for suffix in ['.xlsx','.pdf','.docx','.parquet','.db']:
            self.assertEqual(read_data(self.file('a'+suffix,'corrupt'))['status'],'read_error')

    def test_missing_dependency_does_not_install(self):
        path = self.file('a.xlsx', 'fixture')
        with patch('read_data.importlib.import_module',side_effect=ImportError('missing')), patch('subprocess.run',side_effect=AssertionError('Must not install')):
            self.assertEqual(read_data(path)['status'],'missing_dependency')

    def test_xlsx_formulas_and_sheet_limit(self):
        import openpyxl
        workbook=openpyxl.Workbook()
        workbook.active.append(['=1+1',None,'001'])
        workbook.create_sheet('second').append(['extra'])
        path=self.root/'s.xlsx'; workbook.save(path); workbook.close()
        result=read_data(path,max_units=1)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['units'][0]['records'][0],['=1+1',None,'001'])
        self.assertEqual(result['unit_names'],['Sheet','second'])

    def test_sqlite_quoted_table_name_and_blobs(self):
        path=self.root/'s.sqlite'
        connection=sqlite3.connect(path)
        connection.execute('CREATE TABLE "a""b" (payload BLOB)')
        connection.execute('INSERT INTO "a""b" VALUES (?)',(b'\x00\xff',))
        connection.commit(); connection.close()
        result=read_data(path)
        self.assertEqual(result['status'],'read',result)
        self.assertEqual(result['units'][0]['records'],[[{'bytes_hex':'00ff'}]])

    def test_encrypted_and_blank_pdf(self):
        from pypdf import PdfWriter
        for encrypted in [False,True]:
            writer=PdfWriter();writer.add_blank_page(width=100,height=100)
            if encrypted: writer.encrypt('test-password')
            path=self.root/'s.pdf'
            with path.open('wb') as handle:writer.write(handle)
            self.assertEqual(read_data(path)['status'],'encrypted' if encrypted else 'needs_ocr_or_review')

    def test_xml_entities_are_rejected(self):
        path=self.file('a.xml','<!DOCTYPE foo [<!ENTITY x "secret">]><foo>&x;</foo>')
        self.assertEqual(read_data(path)['status'],'read_error')

    def test_declared_numpy_version_is_enforced(self):
        original=importlib.metadata.version
        with patch('importlib.metadata.version',side_effect=lambda name:'1.24.0' if name=='numpy' else original(name)):
            result=run('tabular')
        self.assertFalse(result['ready'])
        self.assertIn('numpy',result['error'])

    def test_profile_receipts_do_not_overwrite(self):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            setup.save_receipt(self.root,{'ready':True,'python':'common-python'},'common')
            setup.save_receipt(self.root,{'ready':True,'python':'core-python'},'core')
        self.assertEqual(json.loads((self.root/'runtime-common.json').read_text())['python'],'common-python')

    def test_failed_install_not_marked_ready(self):
        import contextlib,io
        with patch.object(sys,'argv',['setup','--install','--state-dir',str(self.root)]), patch.object(setup,'probe',return_value={'ready':False}), patch.object(setup.venv,'EnvBuilder'), patch.object(setup.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['pip'])), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.main(),2)
        self.assertFalse(json.loads((self.root/'runtime-common.json').read_text())['ready'])

    def test_ascii_console_and_confirmed_weight_transfer(self):
        env=dict(os.environ,PYTHONIOENCODING='ascii')
        for mode in ['academic','business']:
            output=self.root/('偏好-'+mode+'.html')
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/configure_preferences.py'),'--mode',mode,'--output',str(output)],capture_output=True,env=env)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(output.exists())
        dimensions=[dict(id=i,label=l,weight=w) for i,l,w,d in PROFILES['academic']]
        data=dict(title='test',mode='academic',decision='test',weight_basis='test',dimensions=dimensions,candidates=[dict(id='A',name='test',summary='test',data_basis='test',risks='test',time='test',cost='test',next_step='test',maturity='机会假设',eligibility='conditional',scores={d['id']:dict(value=3,reason='test',evidence='test',basis='假设') for d in dimensions})])
        source=self.file('scores.json',json.dumps(data))
        weights={d['id']:d['weight'] for d in dimensions};weights['novelty']=80
        preferences=self.file('preferences.json',json.dumps(dict(schema_version=1,mode='academic',confirmed=True,weights=weights)))
        output=self.root/'评分.html'
        command=[sys.executable,'-B',str(ROOT/'scripts/render_candidate_scores.py'),'--input',str(source),'--output',str(output),'--preferences-file',str(preferences)]
        result=subprocess.run(command,capture_output=True,env=env)
        self.assertEqual(result.returncode,0,result.stderr)
        import re
        report=json.loads(re.search(r'const report = (.*);',output.read_text(encoding='utf-8')).group(1))
        self.assertEqual(report['dimensions'][0]['weight'],80)
        self.assertEqual(report['candidates'],data['candidates'])
        bad=json.loads(preferences.read_text());bad['confirmed']=False
        preferences.write_text(json.dumps(bad))
        self.assertNotEqual(subprocess.run(command,capture_output=True,env=env).returncode,0)


if __name__ == '__main__':
    unittest.main()
