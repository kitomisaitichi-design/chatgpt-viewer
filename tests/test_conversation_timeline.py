import unittest
from conversation_timeline import build_timeline


class TimelineIndexTests(unittest.TestCase):
    def test_empty_and_single(self):
        self.assertEqual(build_timeline([]), {'total': 0, 'items': []})
        item = {'seq': 13, 'role': 'assistant', 'channel': 'commentary', 'time': None, 'text': 'First\nupdate'}
        out = build_timeline([item])
        self.assertEqual(out['items'][0]['preview'], 'First update')
        self.assertEqual(out['items'][0]['seq'], 13)

    def test_large_thread_preserves_first_last_and_indices(self):
        rows = [{'seq': i*3, 'role': 'user' if i%7==0 else 'assistant', 'channel': '',
                 'time': i, 'text': 'A longer preview sentence'} for i in range(10015)]
        out = build_timeline(rows)
        self.assertEqual(out['total'], len(rows))
        self.assertEqual(out['items'][0]['index'], 0)
        self.assertEqual(out['items'][-1]['index'], len(rows)-1)
        self.assertLessEqual(len(out['items']), 480)
        self.assertEqual(sorted({x['seq'] for x in out['items']}), [x['seq'] for x in out['items']])

    def test_bounded_previews_do_not_include_full_message(self):
        rows = [{'seq': 2, 'role': 'user', 'channel': '', 'time': 42,
                 'text': 'Visible\nwords ' + 'a'*3000}]
        out = build_timeline(rows)['items'][0]
        self.assertLessEqual(len(out['preview']), 200)
        self.assertNotIn('\n', out['preview'])


if __name__ == '__main__':
    unittest.main()
