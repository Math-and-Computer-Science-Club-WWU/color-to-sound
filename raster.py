from dataclasses import dataclass


@dataclass(frozen=True)
class Raster:
    width: int
    height: int
    data: bytes  # R,G,B,R,G,B,... row by row

    def __post_init__(self):
        if len(self.data) != self.width * self.height * 3:
            raise ValueError("data must hold width * height RGB triples")

    def pixels(self):
        d = self.data
        return zip(d[0::3], d[1::3], d[2::3])  # pixel i is the i-th (r, g, b)


def write_values(raster, path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{raster.width} {raster.height}\n")
        f.writelines(f"{r} {g} {b}\n" for r, g, b in raster.pixels())


def read_values(path):
    with open(path, encoding="utf-8") as f:
        width, height = map(int, f.readline().split())
        data = bytes(int(v) for line in f for v in line.split())
    return Raster(width, height, data)