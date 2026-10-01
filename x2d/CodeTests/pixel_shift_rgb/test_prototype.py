"""离线算法契约；所有数据为模拟数据。"""
import unittest
from prototype import merge_rows, simulate, synthetic_scene, OFFSETS, PATTERNS


class ReconstructionTests(unittest.TestCase):
    def test_color_edges_and_reordered_frames(self):
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                frames = simulate(25, 19, pattern)
                rows = list(merge_rows(frames, pattern=pattern))
                expected = [[c for x in range(1,25) for c in synthetic_scene(x,y)]
                            for y in range(1,19)]
                self.assertEqual([list(r) for r in rows], expected)
                self.assertEqual(list(merge_rows(frames[::-1], OFFSETS[::-1], pattern)),rows)

    def test_green_average_and_no_overflow(self):
        frames = [[[65535]*3 for _ in range(3)] for _ in OFFSETS]
        self.assertTrue(all(v==65535 for row in merge_rows(frames) for v in row))
        frames = [[[n]*3 for _ in range(3)] for n in (100,101,104,200)]
        self.assertEqual(list(next(merge_rows(frames)))[:3], [200,103,100])

    def test_reject_invalid_input(self):
        cases = [(simulate(4,4,'RGGB'), ((0,0),)*4, 'RGGB'),
                 (simulate(1,1,'RGGB'), OFFSETS, 'RGGB'),
                 (simulate(4,4,'RGGB'), OFFSETS, 'BAD')]
        frames = simulate(4,4,'RGGB'); frames[1][0].pop()
        cases.append((frames,OFFSETS,'RGGB'))
        frames = simulate(4,4,'RGGB'); frames[0][0][0]=-1
        cases.append((frames,OFFSETS,'RGGB'))
        for frames,offsets,pattern in cases:
            with self.subTest(pattern=pattern,offsets=offsets):
                with self.assertRaises(ValueError): list(merge_rows(frames,offsets,pattern))


if __name__ == '__main__': unittest.main()
