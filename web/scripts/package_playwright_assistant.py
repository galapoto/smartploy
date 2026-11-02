"""SP110: deterministic allowlisted archive for reused local ObumAI Playwright fill.

This static archive contains no applicant data, cookies, remote code,
credentials or Playwright browser binaries. It does not grant server authority.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "browser-playwright"
DEFAULT_OUTPUT = ROOT / "web/public/smartploy-playwright-assistant.zip"
FILES = ("INSTALL.txt", "assistant.py", "bridge.py")
ZIP_TIMESTAMP = (2026, 10, 1, 0, 0, 0)
MAX_SOURCE_BYTES = 100_000

# SP113: compile the actual SP47 Chrome companion's self-contained receipt
# inspector into the Playwright ZIP. There is NO second receipt recognizer.
# The function itself verifies exact ATS job, receipt phrase/reference,
# sanitized confirmation URL and a stable SHA-256 DOM text digest.
RECEIPT_OWNER_SOURCE = ROOT / "browser-companion/popup.mjs"
RECEIPT_START = "async function inspectReceipt("
RECEIPT_END = "\n/* Ashby has NO"


def reviewed_receipt_script() -> bytes:
    original = RECEIPT_OWNER_SOURCE.read_text(encoding="utf-8")
    start = original.find(RECEIPT_START)
    end = original.find(RECEIPT_END, start)
    if start < 0 or end < start or original.count(RECEIPT_START) != 1:
        raise ValueError("Original Chrome receipt inspector is missing or ambiguous")
    function = original[start:end].strip()
    for gate in (
        "function exactReceiptPage(", "confirmation_page_sha256",
        "hasLiveSubmit()", "crypto.subtle.digest",
        "location.href !== here.href", "confirmed",
    ):
        if gate not in function:
            raise ValueError("Original read-only browser receipt policy changed")
    # JavaScript expression consumed by Playwright page.evaluate(expression, url).
    # Deliberately no browser clicks, cookies, network access or full popup.js.
    script = "(async (expectedApplicationUrl) => {\n" + function + (
        "\nreturn await inspectReceipt(expectedApplicationUrl);\n})\n"
    )
    if len(script.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Receipt inspector exceeded reviewed source limit")
    return script.encode("utf-8")


# SP114: DO NOT build another employer-question mapper. Recompile the original
# owner-reviewed MV3 logic.mjs, questions.mjs, page-questions.mjs and popup's
# inspectForm() into one deterministic self-contained Playwright expression.
QUESTION_LOGIC = ROOT / "browser-companion/logic.mjs"
QUESTION_POLICY = ROOT / "browser-companion/questions.mjs"
QUESTION_FILLER = ROOT / "browser-companion/page-questions.mjs"
FORM_START = "function inspectForm()"
FORM_END = "\n/* Strictly fill only"


def reviewed_questions_script() -> bytes:
    logic = QUESTION_LOGIC.read_text(encoding="utf-8")
    questions = QUESTION_POLICY.read_text(encoding="utf-8")
    filler = QUESTION_FILLER.read_text(encoding="utf-8")
    popup = RECEIPT_OWNER_SOURCE.read_text(encoding="utf-8")
    start = popup.find(FORM_START)
    end = popup.find(FORM_END, start)
    if start < 0 or end <= start or popup.count(FORM_START) != 1:
        raise ValueError("The original browser companion form inspector changed")
    form = popup[start:end].strip()
    importer = 'import { identifyField } from "./logic.mjs";'
    if questions.count(importer) != 1:
        raise ValueError("The original question policy dependencies changed")
    questions = questions.replace(importer, "")
    for source, checks in (
        (logic, ("export function identifyField(", "function unsafeContactMetadata(")),
        (questions, ("export function planReviewedQuestions(", "export function validateReviewedAnswers(")),
        (filler, ("export function fillReviewedAnswers(", "location.href !== inspectedUrl")),
        (form, ("function inspectForm()", "allElementsCount: all.length")),
    ):
        if any(gate not in source for gate in checks):
            raise ValueError("Original companion question security contract changed")
    # 'export ' is the ONLY allowed transformation. Preserve original rules
    # exactly; separate IIFEs prevent distinct modules' tidy() collisions.
    script = (
        "(request) => {\n"
        "  const identifyField = (() => {\n"
        + logic.replace("export ", "") + "\nreturn identifyField;\n})();\n"
        "  const rules = (() => {\n"
        + questions.replace("export ", "") +
        "\nreturn {planReviewedQuestions, validateReviewedAnswers};\n})();\n"
        + form + "\n"
        + filler.replace("export ", "") + "\n"
        "  if (!request || typeof request !== 'object' ||\n"
        "      location.href !== request.inspectedUrl) {\n"
        "    return {status:'blocked',filled:0,reason:'The reviewed employer form changed.'};\n"
        "  }\n"
        "  const current = inspectForm();\n"
        "  if (current.allElementsCount > 250 || current.url !== request.inspectedUrl) {\n"
        "    return {status:'blocked',filled:0,reason:'Employer fields changed or exceeded limit.'};\n"
        "  }\n"
        "  try {\n"
        "    const plan = rules.planReviewedQuestions(current.elements);\n"
        "    if (request.operation === 'inspect') {\n"
        "      return {status:'inspected', questions:plan.questions,\n"
        "              humanOnly:plan.humanOnly};\n"
        "    }\n"
        "    if (request.operation === 'fill' &&\n"
        "        Array.isArray(request.reviewedQuestions) &&\n"
        "        JSON.stringify(plan.questions) === JSON.stringify(request.reviewedQuestions)) {\n"
        "      const actions = rules.validateReviewedAnswers(plan, request.values);\n"
        "      return fillReviewedAnswers(actions, request.approvedUrl, request.inspectedUrl);\n"
        "    }\n"
        "    return {status:'blocked',filled:0,reason:'Reviewed employer questions changed.'};\n"
        "  } catch {\n"
        "    return {status:'blocked',filled:0,reason:'Review employer questions manually.'};\n"
        "  }\n"
        "}\n"
    )
    if len(script.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Compiled original question rules exceeded source limit")
    return script.encode("utf-8")


def reviewed_files() -> dict[str, bytes]:
    files = {}
    for name in FILES:
        item = SOURCE / name
        if (
            not item.is_file() or item.is_symlink()
            or not 100 <= item.stat().st_size <= MAX_SOURCE_BYTES
        ):
            raise ValueError(f"Unreviewed or invalid Playwright assistant asset: {name}")
        files[name] = item.read_bytes()
    files["receipt-inspector.js"] = reviewed_receipt_script()
    files["questions-review.js"] = reviewed_questions_script()
    if (
        b"def validate_packet(" not in files["assistant.py"]
        or b"def fill_reviewed_page(" not in files["assistant.py"]
        or b'if __name__ == "__main__":' not in files["assistant.py"]
        or b"def make_handler(" not in files["bridge.py"]
        or b"def main(" not in files["bridge.py"]
        or b"127.0.0.1" not in files["bridge.py"]
        or b"Playwright" not in files["INSTALL.txt"]
    ):
        raise ValueError("The reviewed browser assistant safety entrypoints are missing")
    return files


def make_zip(output: Path) -> str:
    files = reviewed_files()
    sums = "".join(
        f"{sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(files.items())
    )
    entries = {**files, "SHA256SUMS.txt": sums.encode("ascii")}
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output.parent, prefix=".playwright-", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        with zipfile.ZipFile(temp_path, "w", allowZip64=False) as archive:
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, data)
        with zipfile.ZipFile(temp_path) as check:
            if check.namelist() != sorted(entries) or check.testzip() is not None:
                raise ValueError("Invalid Playwright archive or asset allowlist")
        digest = sha256(temp_path.read_bytes()).hexdigest()
        os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)
    output.with_name(output.name + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii",
    )
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reviewed local Playwright assistant")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    digest = make_zip(args.output)
    print(f"Reviewed local Playwright assistant: {args.output.name} sha256={digest}")


if __name__ == "__main__":
    main()
