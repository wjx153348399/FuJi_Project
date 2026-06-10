from pathlib import Path
import re

from rapidocr_onnxruntime import RapidOCR


def main() -> None:
    engine = RapidOCR()
    out = []
    for img in sorted(
        Path("docx_media").glob("image*.png"),
        key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)),
    ):
        result, _ = engine(str(img))
        out.append(f"## {img.name}")
        if not result:
            out.append("(no text)")
            out.append("")
            continue

        items = []
        for box, text, score in result:
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            items.append(
                {
                    "x": min(xs),
                    "y": min(ys),
                    "text": text,
                    "score": score,
                }
            )

        items.sort(key=lambda it: (round(it["y"] / 8), it["x"]))
        groups = []
        current = []
        current_y = None
        for it in items:
            y = it["y"]
            if current_y is None or abs(y - current_y) <= 10:
                current.append(it)
                current_y = y if current_y is None else (current_y + y) / 2
            else:
                groups.append(current)
                current = [it]
                current_y = y
        if current:
            groups.append(current)

        for g in groups:
            g.sort(key=lambda it: it["x"])
            out.append(" | ".join(f"{it['x']:.0f}:{it['text']}" for it in g))
        out.append("")

    Path("docx_ocr_dump.txt").write_text("\n".join(out), encoding="utf-8")
    print(Path("docx_ocr_dump.txt").resolve())


if __name__ == "__main__":
    main()
