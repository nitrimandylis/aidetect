"""
The count subcommand decides a number I hand to an examiner, so the rules it
applies are worth pinning down. Run with `python -m pytest tests/test_count.py`,
or just `python tests/test_count.py`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aidetect.count import count_docx, count_words  # noqa: E402


def test_citations_are_not_counted():
    # Harvard, with and without a page number, and the two Latin forms.
    assert count_words("The market grew sharply (Smith, 2024).") == 4
    assert count_words("The market grew sharply (Smith, 2024, p. 14).") == 4
    assert count_words("The market grew sharply (ibid.).") == 4
    assert count_words("The market grew sharply (Smith et al.).") == 4


def test_ordinary_parentheses_are_counted():
    # This is the whole reason the rule keys on a year rather than on brackets.
    assert count_words("The second option (the cheaper one) was chosen.") == 8


def test_year_in_running_prose_still_counts():
    # Only the parenthetical is stripped, not every year on the page.
    assert count_words("Revenue fell in 2024 across every region.") == 7


def test_count_never_imports_torch():
    """`aidetect count` must stay instant. A stray torch import in the chain
    from cli -> count -> text would add ~2s to counting words.

    Checked in a subprocess: asserting on sys.modules in-process would pass or
    fail depending on whether some other test file imported torch first.
    """
    import subprocess
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    env = dict(os.environ, PYTHONPATH=src)
    code = ("import sys, aidetect.cli, aidetect.count; "
            "sys.exit(1 if 'torch' in sys.modules else 0)")
    assert subprocess.run([sys.executable, "-c", code], env=env).returncode == 0


def build_fixture(path):
    import docx
    doc = docx.Document()
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph("This introduction runs to exactly seven words.")
    doc.add_heading("Analysis", level=1)
    doc.add_paragraph("Revenue rose over the period (Smith, 2024).")   # 5 counted
    doc.add_paragraph("“A block quote that must not count at all.”")
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Table cells must not count either."
    doc.add_heading("Bibliography", level=1)
    doc.add_paragraph("Smith, J. (2024). A Book That Must Not Count. Press.")
    doc.save(path)


def test_sections_quotes_tables_and_bibliography(tmp_path="/tmp"):
    path = os.path.join(tmp_path, "aidetect-count-fixture.docx")
    build_fixture(path)
    sections, total = count_docx(path)
    assert sections == [("Introduction", 7), ("Analysis", 5)], sections
    assert total == 12
    os.remove(path)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all count checks passed")
