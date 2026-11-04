#!/usr/bin/env python3
"""Genera las muestras de prueba del contrato 5 de forma reproducible.

Sin dependencias externas: PNG y BMP se escriben a mano con la biblioteca estándar,
así que el resultado es idéntico en cualquier máquina y no depende de Pillow.
"""

from __future__ import annotations

import random
import struct
import zlib
from pathlib import Path

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
WIDTH = HEIGHT = 512
PAYLOAD = b"Mensaje oculto de prueba para el detector de esteganografia LSB. " * 40


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def write_png(path: Path, rows: list[bytearray]) -> None:
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def write_bmp(path: Path, rows: list[bytearray]) -> None:
    row_size = (WIDTH * 3 + 3) & ~3
    pixel_data = bytearray()
    for row in reversed(rows):
        line = bytearray()
        for x in range(WIDTH):
            r, g, b = row[x * 3], row[x * 3 + 1], row[x * 3 + 2]
            line += bytes((b, g, r))
        line += b"\x00" * (row_size - len(line))
        pixel_data += line

    file_header = struct.pack("<2sIHHI", b"BM", 14 + 40 + len(pixel_data), 0, 0, 54)
    info_header = struct.pack("<IiiHHIIiiII", 40, WIDTH, HEIGHT, 1, 24, 0, len(pixel_data), 2835, 2835, 0, 0)
    path.write_bytes(file_header + info_header + bytes(pixel_data))


def base_image() -> list[bytearray]:
    """Campo de ruido suavizado: se parece a una fotografía, no a un degradado.

    Un degradado sintético produce un histograma uniforme, cuyos pares (2k, 2k+1)
    ya son iguales antes de ocultar nada, y eso confunde a chi-cuadrado. El ruido
    suavizado da un histograma con forma real.
    """
    rng = random.Random(20261104)
    field = [[rng.randrange(256) for _ in range(WIDTH * 3)] for _ in range(HEIGHT)]

    for _ in range(3):
        blurred: list[list[int]] = [[0] * (WIDTH * 3) for _ in range(HEIGHT)]
        for y in range(HEIGHT):
            for channel in range(3):
                for x in range(WIDTH):
                    index = x * 3 + channel
                    total = 0
                    count = 0
                    for dy in (-2, -1, 0, 1, 2):
                        row = y + dy
                        if 0 <= row < HEIGHT:
                            for dx in (-1, 0, 1):
                                column = x + dx
                                if 0 <= column < WIDTH:
                                    total += field[row][column * 3 + channel]
                                    count += 1
                    blurred[y][index] = total // count
        for y in range(HEIGHT):
            for channel in range(3):
                for x in range(WIDTH):
                    field[y][x * 3 + channel] = blurred[y][x * 3 + channel]

    return [bytearray(row) for row in field]


def embed_lsb(rows: list[bytearray]) -> list[bytearray]:
    """Sustituye el LSB de los tres canales por un flujo pseudoaleatorio.

    Un mensaje de texto repetido deja estructura en el plano LSB y un detector
    chi-cuadrado puede no verlo; una herramienta real comprime o cifra antes de
    incrustar, así que el flujo es indistinguible de bits aleatorios.
    """
    rng = random.Random(4242)
    for row in rows:
        for index in range(len(row)):
            row[index] = (row[index] & 0xFE) | rng.randrange(2)
    return rows


def main() -> None:
    SAMPLES.mkdir(exist_ok=True)
    clean = base_image()
    write_png(SAMPLES / "sample-clean.png", [bytearray(row) for row in clean])
    write_bmp(SAMPLES / "sample-clean.bmp", [bytearray(row) for row in clean])
    write_png(SAMPLES / "sample-lsb.png", embed_lsb([bytearray(row) for row in clean]))

    corrupt = (SAMPLES / "sample-clean.png").read_bytes()
    (SAMPLES / "sample-corrupt.png").write_bytes(corrupt[: len(corrupt) // 3])

    jpeg_like = b"\xff\xd8\xff\xe0" + b"not-real-jpeg" * 100
    (SAMPLES / "sample-fake.png").write_bytes(jpeg_like)

    (SAMPLES / "sample-huge.png").write_bytes(
        (SAMPLES / "sample-clean.png").read_bytes() + b"\x00" * (6 * 1024 * 1024)
    )

    for path in sorted(SAMPLES.glob("sample-*")):
        print(f"{path.name:20} {path.stat().st_size:>9} bytes")


if __name__ == "__main__":
    main()
