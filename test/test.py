# render_local.py
import json
from pathlib import Path
from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined

def render(template_path="Resume_Template_Jinja2_ATS_Hybrid_v2.docx", json_path="test_data.json", out_path="test_output.docx"):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    doc = DocxTemplate(template_path)
    # Use a Jinja environment that trims block-generated newlines and leading spaces
    # jinja_env = Environment(trim_blocks=True, lstrip_blocks=True, newline_sequence="\n")

    jinja_env = Environment(
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )

    doc.render(data, jinja_env=jinja_env)
    try:
        doc.save(out_path)
    except PermissionError:
        # If the output is open in Word, save to a fallback name
        stem = Path(out_path).stem
        fallback = f"{stem}_new.docx"
        doc.save(fallback)
        out_path = fallback
    return str(Path(out_path).resolve())

if __name__ == "__main__":
    print(render())
