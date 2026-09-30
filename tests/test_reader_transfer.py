import json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from test_viewer import fixture
from viewer import Archive, bounded_message_page, source_links

class ReaderTransferTests(unittest.TestCase):
    def page(self,n=25):
        return dict(messages=[dict(seq=i,text=('😀\\\n\t' * 7000),extras={}) for i in range(n)],older=0,newer=0,total=n,first=0)
    def test_latest_and_next_batches_are_bounded_without_missing_messages(self):
        p=self.page();latest=bounded_message_page(p)
        self.assertLess(len(json.dumps(latest,ensure_ascii=False,separators=(',',':')).encode()),32768)
        self.assertEqual(latest['messages'][-1]['seq'],24)
        self.assertEqual(latest['older'],25-len(latest['messages']))
        forward=bounded_message_page(p,forward=True);self.assertEqual(forward['first'],0)
        around=bounded_message_page(p,8192,around=12);self.assertIn(12,[m['seq'] for m in around['messages']])
        self.assertLess(len(json.dumps(around,ensure_ascii=False).encode()),8192)
    def test_fragment_roundtrip_preserves_unicode_and_json_escapes(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'data',background_process=False)
            try:
                f=Path(d)/'chat.json';data=fixture(n=2);text='😀\\\n\t' * 18000;data['mapping']['n1']['message']['content']['parts']=[text];f.write_text(json.dumps(data))
                a.store(next(a.read_items(f)),f,'fingerprint',Path(d),{})
                partial=bounded_message_page(a.page(data['conversation_id']))['messages'][-1]
                rebuilt=partial['text'];offset=partial['text_next']
                while offset<len(text):
                    part=a.message_fragment(data['conversation_id'],1,offset)
                    self.assertLess(len(json.dumps(part,ensure_ascii=False).encode()),25000)
                    rebuilt+=part['text'];self.assertGreater(part['next_offset'],offset);offset=part['next_offset']
                self.assertEqual(rebuilt,text)
            finally:a.close()
    def test_explicit_source_urls_and_group_refs_are_retained(self):
        metadata={'content_references':[{'refs':[{'turn_index':3,'ref_index':1}], 'items':[{'id':'source-a','url':'https://example.org/a','title':'Example','favicon_path':'icons/site.png'}, {'url':'https://example.net/b'}]}, {'ref_id':'no-url'}]}
        links=source_links(metadata);self.assertEqual(len(links['turn3search1']),2)
        self.assertEqual(links['turn3search1'][0]['icon'],'icons/site.png');self.assertNotIn('no-url',links)
    def test_named_file_references_do_not_need_invented_urls(self):
        metadata={'content_references':[{'type':'file_citation','ref_id':'turn0file0','filename':'Project_Notes.md','id':'file_saved_notes'}, {'type':'file_citation','ref_id':'turn0file1','name':'Linked_Notes.md','url':'https://example.org/notes'}]}
        links=source_links(metadata)
        self.assertEqual(links['turn0file0'],[{'title':'Project_Notes.md','kind':'file','file_id':'file_saved_notes'}])
        self.assertEqual(links['turn0file1'][0]['title'],'Linked_Notes.md')
        self.assertNotIn('url',links['turn0file0'][0])
    def test_file_pointer_and_nested_context_citations_keep_names(self):
        metadata={'content_references':[{'type':'file_citation','turn_index':2,'ref_index':3,'title':'Forecast.md'}],'conversation_context_citation_metadata':[{'citation_uuid':'saved-citation','citation':{'category':'files','type':'grouped_webpages','title':'Appendix.pdf','url':'file://my_files/file_saved'}}]}
        links=source_links(metadata)
        self.assertEqual(links['turn2file3'][0]['title'],'Forecast.md')
        self.assertEqual(links['saved-citation'][0]['kind'],'file')
        self.assertNotIn('url',links['saved-citation'][0])
    def test_unchanged_selected_chat_uses_index_even_after_header_discovery(self):
        with tempfile.TemporaryDirectory() as d:
            a=Archive(Path(d)/'data',background_process=False)
            try:
                f=Path(d)/'chat.md';f.write_text('# Cached chat\nConversation: https://chatgpt.com/c/example\n## You\nQuestion\n## Assistant\nAnswer')
                st=f.stat();fp=f'{st.st_mtime_ns}:{st.st_size}';a.store(next(a.read_items(f)),f,fp,Path(d),{});a.enable_ui_cache()
                deadline=time.monotonic()+3
                while a.ui_cache['loading'] and time.monotonic()<deadline:time.sleep(.01)
                a.announce_source(f,Path(d));a.publish_sources(list(a.live_sources.values()))
                with patch.object(a,'read_source_page',side_effect=AssertionError('Unchanged chat must not be reparsed')):
                    self.assertEqual(a.foreground_page('example')['total'],2)
            finally:a.close()
