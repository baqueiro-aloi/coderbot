"""Pregenerate the eight static, channel-friendly lifecycle illustrations.

Run at development time with rsvg-convert installed; the runtime needs no renderer.
"""
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape


STAGES = (
    ("exploring", "Explore"),
    ("proposing", "Propose"),
    ("approval", "Approve"),
    ("implementing", "Build"),
    ("verifying", "Verify"),
    ("archiving", "Archive"),
    ("pr_review", "PR review"),
    ("merged", "Merged"),
)
DEST = Path(__file__).resolve().parent.parent / "src" / "assets" / "milestones"


def svg(active: int) -> str:
    shapes = ['<line x1="74" y1="57" x2="926" y2="57" stroke="#94a3b8" stroke-width="4"/>']
    for i, (_key, name) in enumerate(STAGES):
        x = 74 + i * 852 / 7
        fill = "#155eef" if i == active else ("#16794a" if i < active else "#e2e8f0")
        text = "#ffffff" if i <= active else "#334155"
        shapes.extend((
            f'<circle cx="{x:.1f}" cy="57" r="25" fill="{fill}" '
            f'stroke="#ffffff" stroke-width="3"/>',
            f'<text x="{x:.1f}" y="64" text-anchor="middle" font-size="17" '
            f'font-weight="700" fill="{text}">{i + 1}</text>',
            f'<text x="{x:.1f}" y="112" text-anchor="middle" font-size="14" '
            f'font-weight="{700 if i == active else 400}" fill="#0f172a">'
            f'{escape(name)}</text>',
        ))
    title = f"Codebot progress: {STAGES[active][1]} (step {active + 1} of {len(STAGES)})"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="140" '
            f'viewBox="0 0 1000 140" role="img" aria-label="{escape(title)}">'
            f'<title>{escape(title)}</title>'
            '<rect width="1000" height="140" rx="12" fill="#f8fafc"/>'
            + "".join(shapes) + '</svg>\n')


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for i, (key, _label) in enumerate(STAGES):
        vector = DEST / f"{key}.svg"
        vector.write_text(svg(i), encoding="utf-8")
        subprocess.run(["rsvg-convert", "--output", str(DEST / f"{key}.png"), str(vector)],
                       check=True)


if __name__ == "__main__":
    main()
