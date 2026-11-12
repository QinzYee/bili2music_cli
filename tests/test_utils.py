import unittest

from bili2music.utils import (avid_to_bvid, extract_bvid, parse_duration,
                              parse_favorite_ref, parse_selection,
                              sanitize_filename, strip_html)


class TestUtils(unittest.TestCase):
    def test_favorite_ref(self):
        self.assertEqual(parse_favorite_ref("https://space.bilibili.com/1/favlist?fid=123456"), "123456")
        self.assertEqual(parse_favorite_ref("https://www.bilibili.com/medialist/detail/ml99887"), "99887")
        self.assertEqual(parse_favorite_ref("media_id=4242&x=1"), "4242")
        self.assertEqual(parse_favorite_ref("123456"), "123456")
        self.assertEqual(parse_favorite_ref("abc"), "")

    def test_selection(self):
        self.assertEqual(parse_selection("1,3-5", 8), {1, 3, 4, 5})
        self.assertEqual(parse_selection("9, 2-3", 8), {2, 3})
        self.assertEqual(parse_selection("all", 3), {1, 2, 3})
        self.assertEqual(parse_selection("x", 3), set())

    def test_filename(self):
        self.assertEqual(sanitize_filename('  A/B:C*?  '), "A_B_C__".strip())
        self.assertTrue(sanitize_filename("CON"), "bili_CON")
        self.assertTrue(len(sanitize_filename("长" * 300)) <= 110)
        self.assertTrue(sanitize_filename(""))

    def test_duration(self):
        self.assertEqual(parse_duration("12:34"), 754)
        self.assertEqual(parse_duration("1:02:03"), 3723)
        self.assertEqual(parse_duration(90), 90)
        self.assertEqual(parse_duration("abc"), 0)

    def test_html_and_bvid(self):
        self.assertEqual(strip_html('周杰伦 <em class="keyword">现场</em> &amp; More'),
                         "周杰伦 现场 & More")
        self.assertEqual(extract_bvid("看下 https://www.bilibili.com/video/BV1xx411c7mD 这个"),
                         "BV1xx411c7mD")

    def test_avid_to_bvid(self):
        bv = avid_to_bvid(170001)
        self.assertTrue(bv.startswith("BV1"))
        self.assertEqual(len(bv), 12)
        self.assertEqual(avid_to_bvid(0), "")


if __name__ == "__main__":
    unittest.main()
