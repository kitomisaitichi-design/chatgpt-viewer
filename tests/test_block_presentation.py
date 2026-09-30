import json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from viewer import Archive,block_presentation,parse_json,parse_md

PROGRAM='''# Produce delta relative to the original state
import json
changed_from_pass1 = []
for key in base:
    if result[key] != base[key]:
        changed_from_pass1.append(key)
# Match existing formatting style: UTF-8, four spaces, no terminal newline
with open(output_path, "w", encoding="utf-8") as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=4))
print("done")
'''

class BlockPresentationTests(unittest.TestCase):
    def test_incomplete_explicit_python_is_still_code(self):
        for code in ['def parse_prompts(text):\n    p1 = re.findall(pattern, text)\n    return len(p1', 'async def fetch(url):\n    await', 'class Reader:\n    def open(self):']:
            self.assertEqual(block_presentation(code,'assistant')['language'],'python')
        for prose in ['Define a parser for this text.', 'class is the word I am searching for.', '## Code example\n\ndef parser(x):']:
            self.assertEqual(block_presentation(prose,'assistant'),{})

    def test_shell_pipelines_without_heredocs_are_code(self):
        for script in ["bash -lc sed -n '1,260p' /tmp/main.lua && printf '\\n--- MAIN ---\\n' && grep -n -E 'mouse|drag|scene' /tmp/main.lua | head -n 160",'bash -lc command -v monodis || command -v ilspycmd || true',"sh -c 'echo hello'","zsh -lc 'pwd'"]:
            self.assertEqual(block_presentation(script,'assistant')['language'],'bash')
        self.assertEqual(block_presentation('Use bash -lc to inspect the file.','assistant'),{})
    def test_json_tool_call_retains_original_text_and_code_type(self):
        raw=json.dumps({'path':'/files/search','args':{'search_query':[{'q':'天気'}]},'counter':900719925474099312345},ensure_ascii=True)
        self.assertEqual(block_presentation(raw,'assistant')['language'],'json')
        for prose in ['[Example] is a link label.','{"incomplete":','42','"Just prose"']:
            self.assertEqual(block_presentation(prose,'assistant'),{})
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'data',background_process=False)
            try:
                p=Path(d)/'call.md';p.write_text('# Call\nConversation: https://chatgpt.com/c/json-tool\n## Assistant\n'+raw)
                a.store(parse_md(p.read_text(),p),p,'fp',Path(d),{})
                with a.connect() as db:db.execute("UPDATE messages SET extras='{}'")
                row=a.page('json-tool')['messages'][0]
                self.assertEqual(row['text'],raw)
                self.assertEqual(row['extras']['presentation']['language'],'json')
            finally:a.close()
    def test_shell_wrapped_python_script_has_code_presentation(self):
        script="bash -lc cat > /tmp/catalogue.py <<'PY'\n"+PROGRAM+"\nPY\npython /tmp/catalogue.py"
        self.assertEqual(block_presentation(script,'assistant'),{'kind':'code','language':'bash','origin':'inferred'})
        self.assertEqual(block_presentation("Use bash -lc to run the next command.",'assistant'),{})
    def test_unfenced_markdown_program_retains_code_semantics(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'chat.md';p.write_text('# Test\n## Assistant\n'+PROGRAM)
            m=parse_md(p.read_text(),p)['messages'][0]
            self.assertEqual(m['extras']['presentation'],{'kind':'code','language':'python','origin':'inferred'})
            self.assertEqual(m['text'],PROGRAM.strip())
    def test_saved_json_code_and_output_types_survive_parsing(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'chat.json'
            parsed=parse_json({'id':'blocks','messages':[{'role':'assistant','content':{'content_type':'code','language':'python','text':PROGRAM}},{'role':'tool','author':{'name':'python'},'content':{'content_type':'execution_output','text':'# This is output, not a heading\n    indented\n'}}]},p)
            self.assertEqual(parsed['messages'][0]['extras']['presentation']['language'],'python')
            self.assertEqual(parsed['messages'][1]['extras']['presentation']['kind'],'output')
            self.assertEqual(parsed['messages'][1]['text'],'# This is output, not a heading\n    indented\n')
    def test_prose_and_fenced_markdown_are_not_reclassified(self):
        for text in ['## Instructions\n\nUse this command next.\nprint("hello")','## Weather\n\nToday is cool.','Here is code:\n```python\nprint(1)\n```','hello\nworld']:
            self.assertEqual(block_presentation(text,'assistant'),{})
    def test_markdown_fences_inside_python_strings_remain_code(self):
        program = PROGRAM + '\nextra_tsv = r\'\'\'1001|Example|Lane\n1002|Another|Lane\'\'\'\nreport = "```python\\nprint(1)\\n```"\nseparator = "~~~"\nprint(report)\n'
        self.assertEqual(block_presentation(program,'assistant')['kind'],'code')
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'data',background_process=False)
            try:
                p=Path(d)/'chat.md';p.write_text('# Test\nConversation: https://chatgpt.com/c/embedded-fences\n## Assistant\n'+program)
                parsed=parse_md(p.read_text(),p)
                self.assertEqual(parsed['messages'][0]['text'],program.strip())
                a.store(parsed,p,'fp',Path(d),{})
                with a.connect() as db:db.execute("UPDATE messages SET extras='{}'")
                row=a.page('embedded-fences')['messages'][0]
                self.assertEqual(row['extras']['presentation']['language'],'python')
                self.assertEqual(row['text'],program.strip())
            finally:a.close()
    def test_older_index_is_presented_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'data',background_process=False)
            try:
                p=Path(d)/'chat.md';p.write_text('# Test\nConversation: https://chatgpt.com/c/cached-block\n## Assistant\n'+PROGRAM)
                a.store(parse_md(p.read_text(),p),p,'fp',Path(d),{})
                with a.connect() as db:db.execute("UPDATE messages SET extras='{}'")
                self.assertEqual(a.page('cached-block')['messages'][0]['extras']['presentation']['kind'],'code')
            finally:a.close()

    def test_reused_source_ids_resolve_for_the_exact_message(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'data',background_process=False)
            try:
                p=Path(d)/'chat.json';data={'id':'scope-links','messages':[{'role':'assistant','text':'First','metadata':{'content_references':[{'ref_id':'turn0search2','url':'https://example.org/first'}]}},{'role':'assistant','text':'Second','metadata':{'content_references':[{'ref_id':'turn0search2','url':'https://example.org/second'}]}}]};p.write_text(json.dumps(data))
                a.store(parse_json(data,p),p,'fp',Path(d),{})
                self.assertEqual(a.linked_sources('scope-links',['turn0search2'],seq=1)['turn0search2'][0]['url'],'https://example.org/second')
                self.assertEqual(a.linked_sources('scope-links',['turn0search2']),{})
            finally:a.close()
