# render_local.py
import json
from pathlib import Path
from docxtpl import DocxTemplate

# from jinja2 import Environment
# env = Environment(trim_blocks=True, lstrip_blocks=True, newline_sequence="\n")

def render(template_path="ResumeTemplate_R1.docx", json_path="resume.json", out_path="out.docx"):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    doc = DocxTemplate(template_path)
    doc.render(data)
    doc.save(out_path)
    return str(Path(out_path).resolve())

if __name__ == "__main__":
    print(render())
