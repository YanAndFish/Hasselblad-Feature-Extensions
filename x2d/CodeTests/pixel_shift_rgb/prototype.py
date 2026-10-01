"""离线四张整数像素位移原型；不连接相机，不解码 3FR。

约定：frame[y][x] 对应场景 (x+dx,y+dy)，CFA 固定在传感器坐标。
真实 X2D 的位移方向、相位和有效区域尚未映射到此约定。
"""
from array import array
from pathlib import Path
import argparse
import json
import sys

PATTERNS = {"RGGB": ((0, 1), (1, 2)), "BGGR": ((2, 1), (1, 0)),
            "GRBG": ((1, 0), (2, 1)), "GBRG": ((1, 2), (0, 1))}
OFFSETS = ((0, 0), (1, 0), (0, 1), (1, 1))


def merge_rows(frames, offsets=OFFSETS, pattern="RGGB"):
    """逐行输出四帧交集 RGB16；两次绿色测量四舍五入平均。

    输入已经解码且校正到相同线性尺度；当前仅接受四个规定相位。
    输出原点为场景 (1,1)，尺寸为 (width-1,height-1)。
    """
    if pattern not in PATTERNS:
        raise ValueError("Unknown CFA pattern")
    if len(frames) != 4 or len(offsets) != 4 or set(offsets) != set(OFFSETS):
        raise ValueError("Four distinct integer phases required")
    h = len(frames[0]); w = len(frames[0][0]) if h else 0
    if h < 2 or w < 2:
        raise ValueError("Frames too small")
    for frame in frames:
        if len(frame) != h or any(len(row) != w for row in frame):
            raise ValueError("Mismatched frame dimensions")
        for row in frame:
            if any(type(v) is not int or not 0 <= v <= 65535 for v in row):
                raise ValueError("Expected unsigned 16-bit integer samples")
    cfa = PATTERNS[pattern]
    for y in range(1, h):
        rgb = array('H')
        for x in range(1, w):
            sums = [0, 0, 0]; counts = [0, 0, 0]
            for frame, (dx, dy) in zip(frames, offsets):
                sx, sy = x-dx, y-dy
                channel = cfa[sy % 2][sx % 2]
                sums[channel] += frame[sy][sx]; counts[channel] += 1
            if counts != [1, 2, 1]:
                raise ValueError("Incomplete RGB coverage")
            rgb.extend((sums[0], (sums[1]+1)//2, sums[2]))
        yield rgb


def synthetic_scene(x, y):
    # 不同通道的斜坡和硬边用于检出错位、串色，数值留在 16 位范围内。
    return (1000 + x*97 + (y % 7)*901,
            2000 + y*113 + (x % 9)*701,
            3000 + (x+y)*53 + (12000 if (x//8+y//8) % 2 else 0))


def simulate(width, height, pattern):
    cfa = PATTERNS[pattern]
    return [[[synthetic_scene(x+dx, y+dy)[cfa[y % 2][x % 2]]
              for x in range(width)] for y in range(height)] for dx, dy in OFFSETS]


def write_ppm(path, width, height, rows):
    """PPM RGB16 是验证容器，不是 RAW / 3FR / 3F。"""
    with Path(path).open('wb') as stream:
        stream.write(f'P6\n{width} {height}\n65535\n'.encode('ascii'))
        count = 0
        for row in rows:
            if len(row) != width*3:
                raise ValueError("Wrong RGB row length")
            output = array('H', row)
            if sys.byteorder == 'little':
                output.byteswap()
            stream.write(output.tobytes()); count += 1
        if count != height:
            raise ValueError("Wrong RGB row count")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    w, h = 129, 97
    frames = simulate(w, h, 'RGGB')
    rows = list(merge_rows(frames))
    max_error = max(abs(row[x*3+c]-synthetic_scene(x+1,y+1)[c])
                    for y,row in enumerate(rows) for x in range(w-1) for c in range(3))
    if max_error:
        raise AssertionError("Synthetic reconstruction mismatch")
    write_ppm(args.output/'synthetic-rgb16.ppm', w-1, h-1, rows)
    report = {'source': 'synthetic_only', 'camera_access': False,
              'input_size': [w,h], 'output_size': [w-1,h-1],
              'scene_origin': [1,1], 'max_absolute_channel_error': max_error,
              'output_format': 'PPM RGB16, not RAW',
              'limitations': ['X2D real phase mapping unverified', 'No 3FR decoder',
                              'No black-level or gain calibration', 'No motion correction',
                              'No real-camera or full-resolution performance validation']}
    (args.output/'synthetic-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
