# Copyright 2026 The JAX Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Generates a GitHub Step Summary from JUnit XML test results and ResultStore links."""

import argparse
import glob
import os
import sys

# Add postprocess directory to sys.path so we can import xml2json
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "postprocess"))
import xml2json  # pylint: disable=g-import-not-at-top


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
      description="Generates a GitHub Step Summary from JUnit XMLs."
  )
  parser.add_argument(
      "description",
      type=str,
      help="Description of the Bazel invocation (e.g. 'CPU RBE tests').",
  )
  parser.add_argument(
      "artifacts_dir",
      type=str,
      help="Directory containing collected test.xml files.",
  )
  parser.add_argument(
      "invocation_id",
      type=str,
      help="The Bazel invocation ID for ResultStore.",
  )
  parser.add_argument(
      "bazel_exit_code",
      type=int,
      help="The exit code of the Bazel command.",
  )
  parser.add_argument(
      "action_type",
      type=str,
      nargs="?",
      default="test",
      help="The action type ('test' or 'build').",
  )
  return parser.parse_args()


def parse_junit_xmls(artifacts_dir: str):
  total_tests = 0
  passed_tests = 0
  failed_tests = 0
  skipped_tests = 0
  failures = []

  xml_files = glob.glob(os.path.join(artifacts_dir, "*.xml"))
  for xml_file in xml_files:
    for record in xml2json.iter_xml_records(xml_file):
      total_tests += 1
      status = record.get("status", "PASSED")
      if status in ("FAILED", "ERROR"):
        failed_tests += 1
      elif status == "SKIPPED":
        skipped_tests += 1
      else:
        passed_tests += 1

      if status in ("FAILED", "ERROR"):
        classname = record.get("classname") or ""
        name = record.get("name") or "UnknownTest"
        file_path = record.get("file_path") or ""

        if file_path:
          prefix = f"{file_path} :: "
        else:
          prefix = ""

        if classname:
          test_name = f"{prefix}{classname}.{name}"
        else:
          test_name = f"{prefix}{name}"

        message = (
            record.get("detail")
            or record.get("message")
            or record.get("system_err")
            or "No failure details provided."
        )
        if len(message) > 500:
          message = message[:500] + "\n... (truncated)"
        failures.append((test_name, message.strip()))

  return total_tests, passed_tests, failed_tests, skipped_tests, failures


def main():
  args = parse_args()
  url = f"https://source.cloud.google.com/results/invocations/{args.invocation_id}"

  lines = []
  status_emoji = "✅" if args.bazel_exit_code == 0 else "❌"
  lines.append(f"## {status_emoji} {args.description}")
  lines.append("")
  lines.append(f"**ResultStore Link:** [{url}]({url}) *(visible to Googlers only)*")
  lines.append("")

  if args.action_type == "build":
    if args.bazel_exit_code == 0:
      lines.append("**Build completed successfully.**")
    else:
      lines.append("> [!WARNING]")
      lines.append("> **Build failed.** Please check the workflow logs or ResultStore link for build errors.")
  else:
    total, passed, failed, skipped, failures = parse_junit_xmls(args.artifacts_dir)

    if total == 0 and args.bazel_exit_code != 0:
      lines.append("> [!WARNING]")
      lines.append("> **Build or setup failed before tests could finish running.** Please check the workflow logs or ResultStore link for build errors.")
    elif total > 0:
      lines.append("### 📊 Test Results")
      lines.append("| Total | Passed | Failed | Skipped |")
      lines.append("| :-: | :-: | :-: | :-: |")
      lines.append(f"| {total} | {passed} | {failed} | {skipped} |")
      lines.append("")

    if failures:
      lines.append(f"### ❌ Failing Tests ({len(failures)})")
      # Show at most 20 failures to avoid overflowing step summary limits
      for test_name, message in failures[:20]:
        lines.append(f"<details><summary><code>{test_name}</code></summary>")
        lines.append("")
        lines.append("```")
        lines.append(message)
        lines.append("```")
        lines.append("</details>")
        lines.append("")

      if len(failures) > 20:
        lines.append(f"*... and {len(failures) - 20} more failing test(s).*")
        lines.append("")

  summary_markdown = "\n".join(lines) + "\n"

  # Write to $GITHUB_STEP_SUMMARY if present
  step_summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
  if step_summary_file:
    try:
      with open(step_summary_file, "a", encoding="utf-8") as f:
        f.write(summary_markdown)
      print(f"Step summary written to {step_summary_file}", file=sys.stderr)
    except Exception as e:
      print(f"Error writing to GITHUB_STEP_SUMMARY: {e}", file=sys.stderr)
  else:
    print("GITHUB_STEP_SUMMARY environment variable not set. Printing summary to stdout:", file=sys.stderr)
    print(summary_markdown)


if __name__ == "__main__":
  main()
