#  Copyright 2024 Google LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""HTTP server and API handlers for the BeToCQ Test Explorer."""

import argparse
import atexit
import dataclasses
import email.parser
import enum
import http.server
import json
import os
import pkgutil
import shutil
import socket
import socketserver
import sys
import tempfile
import threading
from typing import Any
import urllib.parse
import webbrowser
import zipfile

# Bootstrap sys.path when running standalone .par binaries built with
# no_launcher. This allows standard zipimport to find third-party
# libraries (portpicker, yaml).
# stored inside the archive under google3/third_party/py/.
for _p in list(sys.path):
  _tp_path = os.path.join(_p, "google3/third_party/py")
  if _tp_path not in sys.path:
    sys.path.append(_tp_path)

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
  sys.path.append(_current_dir)
_repo_root = os.path.abspath(os.path.join(_current_dir, "../../.."))
if _repo_root not in sys.path:
  sys.path.append(_repo_root)

try:
  import portpicker  # pylint: disable=g-import-not-at-top
except ImportError:
  portpicker = None


class _DummyRpcError(Exception):
  """Fallback exception type when pywraprpc is not available."""


try:
  from google3.google.devtools.issuetracker.v1 import issuetracker_builders  # pylint: disable=g-import-not-at-top
  from google3.google.devtools.issuetracker.v1 import issuetracker_client  # pylint: disable=g-import-not-at-top
  from google3.net.rpc.python import pywraprpc  # pylint: disable=g-import-not-at-top

  _RpcException: type[Exception] = pywraprpc.RPCException
except ImportError:
  issuetracker_builders = None
  issuetracker_client = None
  pywraprpc = None
  _RpcException: type[Exception] = _DummyRpcError

from betocq.tools.test_explorer import mobly_parser  # pylint: disable=g-import-not-at-top


class ApiEndpoint(enum.StrEnum):
  """REST API endpoints supported by Test Explorer HTTP server."""

  INDEX = "/"
  RESULTS = "/api/results"
  ARTIFACT = "/api/artifact"
  DOWNLOAD = "/api/download"
  UPLOAD = "/api/upload"
  FILE_BUG = "/api/file_bug"


class ContentType(enum.StrEnum):
  """HTTP Content-Type header values."""

  JSON = "application/json"
  HTML = "text/html; charset=utf-8"
  OCTET_STREAM = "application/octet-stream"
  MULTIPART_FORM_DATA = "multipart/form-data"


@dataclasses.dataclass
class ArtifactResponse:
  """Payload structure for single artifact content response."""

  filename: str
  path: str
  content: str


@dataclasses.dataclass
class UploadResponse:
  """Payload structure for upload status response."""

  message: str
  data: dict[str, Any] | mobly_parser.ParseResult


@dataclasses.dataclass
class ErrorResponse:
  """Payload structure for error responses."""

  error: str


@dataclasses.dataclass
class FileBugResponse:
  """Payload structure for file bug status response."""

  success: bool
  message: str
  issue_id: str | None = None
  issue_url: str | None = None


PACKAGE_NAME = "google3.wireless.android.platform.testing.bettertogether.betocq.tools.test_explorer"
TEMPLATE_RESOURCE_PATH = "templates/index.html"
DEFAULT_COMPONENT_ID = "2105900"
_MAX_DESCRIPTION_URL_CHARS = 1800
_MAX_ARTIFACT_READ_BYTES = 2 * 1024 * 1024  # 2MB
_ISSUETRACKER_NEW_ISSUE_URL = "https://issuetracker.google.com/issues/new?"
_ISSUETRACKER_ISSUE_URL_PREFIX = "https://issuetracker.google.com/issues/"
_TEMP_DIR_PREFIX = "betocq_explorer_"
_BROWSER_OPEN_DELAY_SECONDS = 1.25

# In-memory store for MVP
TEST_RESULTS: dict[str, Any] | mobly_parser.ParseResult = {
    "summary": {},
    "test_classes": {},
}
UPLOAD_TEMP_DIRS: list[str] = []
BUG_FILING_LOCK = threading.Lock()


def cleanup_uploaded_temp_dirs() -> None:
  """Cleans up temporary directories created for uploaded zip files."""
  for temp_dir in UPLOAD_TEMP_DIRS:
    if os.path.exists(temp_dir):
      shutil.rmtree(temp_dir, ignore_errors=True)
  UPLOAD_TEMP_DIRS.clear()


atexit.register(cleanup_uploaded_temp_dirs)


def _read_template_from_zip(zip_candidate: str) -> bytes | None:
  """Reads index.html template from a candidate zip file."""
  if not zip_candidate or not os.path.isfile(zip_candidate):
    return None
  try:
    with zipfile.ZipFile(zip_candidate, "r") as z:
      for name in z.namelist():
        if name.endswith(TEMPLATE_RESOURCE_PATH):
          return z.read(name)
  except (OSError, zipfile.BadZipFile, KeyError):
    pass
  return None


def get_template_html() -> bytes:
  """Retrieves the index.html template from disk, par zip, or explicit pkgutil.

  Returns:
    The raw HTML template bytes, or an error HTML snippet if not found.
  """
  base_dir = os.path.dirname(os.path.abspath(__file__))
  candidate_template_paths = [
      os.path.join(base_dir, "templates", "index.html"),
      os.path.join(base_dir, "index.html"),
  ]
  for template_path in candidate_template_paths:
    if os.path.isfile(template_path):
      with open(template_path, "rb") as f:
        return f.read()

  candidate_zips = [
      os.environ.get("_PARFILE", ""),
      getattr(sys, "argv", [""])[0],
      __file__,
  ]
  for zip_candidate in candidate_zips:
    data = _read_template_from_zip(zip_candidate)
    if data:
      return data

  try:
    data = pkgutil.get_data(
        PACKAGE_NAME,
        TEMPLATE_RESOURCE_PATH,
    )
  except (OSError, ImportError, ValueError):
    data = None
  if data:
    return data

  return (
      b"<!DOCTYPE html><html><body><h1>Error: Template not"
      b" found</h1></body></html>"
  )


def _safe_extract_zip(zip_ref: zipfile.ZipFile, target_dir: str) -> bool:
  """Extracts zip archive entries verifying no member escapes target_dir."""
  return mobly_parser.safe_extract_zip(zip_ref, target_dir)


def parse_target_path(
    target_path: str,
) -> mobly_parser.ParseResult | dict[str, Any]:
  """Parses results from a directory or zip file path.

  Args:
    target_path: Path to the local results directory or zip archive file.

  Returns:
    A ParseResult object with parsed metrics and artifact info, or a dictionary
    containing an 'error' message if parsing fails.
  """
  parsed = mobly_parser.find_and_parse_results(target_path)
  if isinstance(parsed, mobly_parser.ParseResult) and os.path.isfile(
      target_path
  ):
    UPLOAD_TEMP_DIRS.append(parsed.results_dir)
  return parsed


def _extract_zip_payload(post_data: bytes, content_type: str) -> bytes | None:
  """Extracts uploaded zip payload from multipart request body."""
  msg_header = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
  msg = email.parser.BytesParser().parsebytes(msg_header + post_data)
  for part in msg.walk():
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
      filename = str(part.get_filename() or "")
      if filename.endswith(".zip") or payload.startswith(b"PK\x03\x04"):
        return payload
  return None


def _create_buganizer_issue(
    summary: str,
    description: str,
    component_id: str,
    attachment_paths: list[str],
    assignee: str = "",
) -> FileBugResponse:
  """Creates an Issue Tracker ticket sequentially and attaches specified files.

  Adheres to sequential execution and retention policy conflict rules.

  Args:
    summary: The issue summary/title.
    description: The issue body description.
    component_id: The Issue Tracker component ID.
    attachment_paths: List of file paths to attach to the issue.
    assignee: Optional user email to assign the issue to.

  Returns:
    A FileBugResponse instance containing status and issue metadata.
  """
  try:
    numeric_component_id = int(component_id)
  except ValueError:
    return FileBugResponse(
        success=False,
        message=f"Invalid component ID: {component_id!r}. Must be an integer.",
    )

  if issuetracker_builders is None or issuetracker_client is None:
    # External Partner Mode: No internal API credentials available
    params = {
        "component": component_id,
        "title": summary,
        "description": description[:_MAX_DESCRIPTION_URL_CHARS],
    }
    if assignee:
      params["assignee"] = assignee
    web_url = _ISSUETRACKER_NEW_ISSUE_URL + urllib.parse.urlencode(params)
    return FileBugResponse(
        success=True,
        message=(
            "External Partner Mode (No internal API access): Click below to"
            " open Google Issue Tracker with pre-populated failure details:"
        ),
        issue_url=web_url,
    )

  create = issuetracker_builders.CreateIssueRequestBuilder(numeric_component_id)
  create.SetTitle(summary)
  create.SetComment(description)
  if assignee:
    create.SetAssignee(assignee)

  for full_path in attachment_paths:
    if os.path.isfile(full_path):
      filename = os.path.basename(full_path)
      try:
        with open(full_path, "rb") as f:
          content_bytes = f.read()
      except OSError:
        continue
      if (
          filename.endswith(".txt")
          or filename.endswith(".log")
          or "logcat" in filename
      ):
        create.AddPlaintextAttachment(filename, content_bytes)
      else:
        create.AddAttachment(
            filename, ContentType.OCTET_STREAM.value, content_bytes
        )

  try:
    auth_helper = issuetracker_client.LocalOrBorgWithLoquat()
    client = issuetracker_client.Build(use_prod=True, auth_helper=auth_helper)
    issue = client.stub.CreateIssue(create.Build())
    write_requests = create.BuildAttachmentsWriteRequests(issue)
    if write_requests:
      issuetracker_client.WriteAttachments(client, write_requests)
  except _RpcException as e:
    err_str = str(e).lower()
    if "retention" in err_str:
      return FileBugResponse(
          success=False,
          message=(
              "Issue Tracker rejected due to conflicting data retention"
              " settings. Please re-file or check target component retention."
          ),
      )
    # External Partner Mode: No internal API credentials available
    params = {
        "component": component_id,
        "title": summary,
        "description": description[:_MAX_DESCRIPTION_URL_CHARS],
    }
    if assignee:
      params["assignee"] = assignee
    web_url = (
        _ISSUETRACKER_NEW_ISSUE_URL
        + urllib.parse.urlencode(params)
    )
    return FileBugResponse(
        success=True,
        message=(
            "External Partner Mode (No internal API access): Click below to"
            " open Google Issue Tracker with pre-populated failure details:"
        ),
        issue_url=web_url,
    )

  issue_id = str(issue.issue_id)
  return FileBugResponse(
      success=True,
      message=f"Successfully created Issue Tracker ticket {issue_id}",
      issue_id=issue_id,
      issue_url=f"{_ISSUETRACKER_ISSUE_URL_PREFIX}{issue_id}",
  )


class TestExplorerRequestHandler(http.server.BaseHTTPRequestHandler):
  """Request handler for serving the Test Explorer UI and API endpoints."""

  def _send_json(self, data: Any, status_code: int = 200) -> None:
    """Serializes data object or dataclass to JSON and sends HTTP response."""
    if dataclasses.is_dataclass(data) and not isinstance(data, type):
      data = dataclasses.asdict(data)
    body = json.dumps(data).encode("utf-8")
    self.send_response(status_code)
    self.send_header("Content-Type", ContentType.JSON.value)
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)

  def _get_safe_artifact_path(self) -> tuple[str, str] | None:
    """Parses path parameter and validates it stays inside results_dir."""
    parsed_url = urllib.parse.urlparse(self.path)
    params = urllib.parse.parse_qs(parsed_url.query)
    rel_path = params.get("path", [""])[0]
    if isinstance(TEST_RESULTS, mobly_parser.ParseResult):
      results_dir = TEST_RESULTS.results_dir
    else:
      results_dir = str(TEST_RESULTS.get("results_dir") or "")
    if not results_dir or not rel_path:
      return None

    full_path = os.path.abspath(os.path.join(results_dir, rel_path))
    results_dir_abs = os.path.abspath(results_dir)
    try:
      common_path = os.path.commonpath([full_path, results_dir_abs])
    except ValueError:
      return None

    if common_path != results_dir_abs:
      return None

    if os.path.isfile(full_path):
      return full_path, rel_path
    return None

  def _handle_index(self) -> None:
    """Serves the main HTML UI page."""
    html_bytes = get_template_html()
    self.send_response(200)
    self.send_header("Content-Type", ContentType.HTML.value)
    self.send_header("Content-Length", str(len(html_bytes)))
    self.end_headers()
    self.wfile.write(html_bytes)

  def _handle_artifact(self) -> None:
    """Serves text artifact file content for the viewer modal."""
    target = self._get_safe_artifact_path()
    if not target:
      self.send_error(404, "Artifact Not Found")
      return

    full_path, rel_path = target
    try:
      with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read(_MAX_ARTIFACT_READ_BYTES)
    except OSError as e:
      self._send_json(ErrorResponse(error=str(e)), 500)
      return

    self._send_json(
        ArtifactResponse(
            filename=os.path.basename(rel_path),
            path=rel_path,
            content=content,
        )
    )

  def _handle_download(self) -> None:
    """Serves artifact files as binary downloads."""
    target = self._get_safe_artifact_path()
    if not target:
      self.send_error(404, "Artifact Not Found")
      return

    full_path, rel_path = target
    filename = os.path.basename(rel_path)
    try:
      file_size = os.path.getsize(full_path)
    except OSError as e:
      self.send_error(500, f"Download error: {e}")
      return

    self.send_response(200)
    self.send_header("Content-Type", ContentType.OCTET_STREAM.value)
    self.send_header(
        "Content-Disposition", f'attachment; filename="{filename}"'
    )
    self.send_header("Content-Length", str(file_size))
    self.end_headers()
    try:
      with open(full_path, "rb") as f:
        shutil.copyfileobj(f, self.wfile)
    except OSError as e:
      self.send_error(500, f"Download error: {e}")

  def do_GET(self) -> None:  # pylint: disable=invalid-name
    """Handles HTTP GET requests."""
    if self.path == ApiEndpoint.INDEX.value or self.path.startswith("/?"):
      self._handle_index()
    elif self.path == ApiEndpoint.RESULTS.value:
      self._send_json(TEST_RESULTS)
    elif self.path.startswith(ApiEndpoint.ARTIFACT.value):
      self._handle_artifact()
    elif self.path.startswith(ApiEndpoint.DOWNLOAD.value):
      self._handle_download()
    else:
      self.send_error(404, "Not Found")

  def _handle_file_bug(self) -> None:
    """Handles POST requests to file an Issue Tracker ticket with attachments."""
    content_length = int(self.headers.get("Content-Length", 0))
    post_data = self.rfile.read(content_length)
    try:
      payload = json.loads(post_data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
      self._send_json(ErrorResponse(error=f"Invalid JSON payload: {e}"), 400)
      return

    summary = str(payload.get("summary", "")).strip()
    description = str(payload.get("description", "")).strip()
    component_id = str(payload.get("component_id") or "").strip()
    if not component_id:
      component_id = DEFAULT_COMPONENT_ID
    assignee = str(payload.get("assignee", "")).strip()
    is_shielded = payload.get("is_shielded", True)
    is_throughput = payload.get("is_throughput", False)
    rel_paths = payload.get("attachment_paths", [])

    if not summary:
      self._send_json(ErrorResponse(error="Summary is required."), 400)
      return

    try:
      int(component_id)
    except ValueError:
      self._send_json(
          ErrorResponse(
              error=(
                  f"Invalid component ID: {component_id!r}. Must be an integer."
              )
          ),
          400,
      )
      return

    # Check rule: Bug Filing for Throughput Issues
    if is_throughput and not is_shielded:
      self._send_json(
          FileBugResponse(
              success=False,
              message=(
                  "Ticket filing skipped: Throughput/transfer speed failures"
                  " in unshielded environments must not be filed as tickets."
              ),
          ),
          200,
      )
      return

    if isinstance(TEST_RESULTS, mobly_parser.ParseResult):
      results_dir = TEST_RESULTS.results_dir
    else:
      results_dir = str(TEST_RESULTS.get("results_dir") or "")

    attachment_paths: list[str] = []
    if results_dir and isinstance(rel_paths, list):
      results_dir_abs = os.path.abspath(results_dir)
      for rel_p in rel_paths:
        full_path = os.path.abspath(os.path.join(results_dir_abs, str(rel_p)))
        try:
          common_path = os.path.commonpath([full_path, results_dir_abs])
        except ValueError:
          continue
        if common_path == results_dir_abs and os.path.isfile(full_path):
          attachment_paths.append(full_path)

    with BUG_FILING_LOCK:
      response = _create_buganizer_issue(
          summary=summary,
          description=description,
          component_id=component_id,
          attachment_paths=attachment_paths,
          assignee=assignee,
      )

    status_code = 200 if response.success else 500
    self._send_json(response, status_code)

  def do_POST(self) -> None:  # pylint: disable=invalid-name
    """Handles HTTP POST requests for result uploads."""
    if self.path == ApiEndpoint.FILE_BUG.value:
      self._handle_file_bug()
      return
    if self.path != ApiEndpoint.UPLOAD.value:
      self.send_error(404, "Not Found")
      return

    content_type = self.headers.get("Content-Type", "")
    if ContentType.MULTIPART_FORM_DATA.value not in content_type:
      self._send_json(ErrorResponse(error="Expected multipart/form-data"), 400)
      return

    content_length = int(self.headers.get("Content-Length", 0))
    post_data = self.rfile.read(content_length)
    zip_payload = _extract_zip_payload(post_data, content_type)
    if zip_payload is None:
      self._send_json(
          ErrorResponse(error="No valid .zip file uploaded."), 400
      )
      return

    temp_dir = tempfile.mkdtemp(prefix=_TEMP_DIR_PREFIX)
    zip_path = os.path.join(temp_dir, mobly_parser.UPLOADED_ZIP_NAME)
    with open(zip_path, "wb") as f:
      f.write(zip_payload)

    try:
      with zipfile.ZipFile(zip_path, "r") as zip_ref:
        is_safe = _safe_extract_zip(zip_ref, temp_dir)
    except (zipfile.BadZipFile, OSError):
      shutil.rmtree(temp_dir, ignore_errors=True)
      self._send_json(ErrorResponse(error="Invalid ZIP file."), 400)
      return

    if not is_safe:
      shutil.rmtree(temp_dir, ignore_errors=True)
      self._send_json(
          ErrorResponse(error="Zip archive contains unsafe path entries."),
          400,
      )
      return

    parsed_data = mobly_parser.find_and_parse_results(temp_dir)
    if isinstance(parsed_data, dict) and "error" in parsed_data:
      shutil.rmtree(temp_dir, ignore_errors=True)
      self._send_json(parsed_data, 400)
      return

    # Clean up previous temporary upload directory to prevent disk leaks
    cleanup_uploaded_temp_dirs()

    global TEST_RESULTS
    TEST_RESULTS = parsed_data
    UPLOAD_TEMP_DIRS.append(temp_dir)

    self._send_json(
        UploadResponse(message="Successfully parsed", data=TEST_RESULTS)
    )

  def log_message(self, format_str: str, *args: Any) -> None:
    """Overrides BaseHTTPRequestHandler.log_message to suppress console log noise."""


def pick_unused_port() -> int:
  """Picks an unused TCP port using portpicker if available, otherwise stdlib socket."""
  if portpicker is not None:
    return portpicker.pick_unused_port()
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(("", 0))
    return int(s.getsockname()[1])


def main() -> None:
  """Parses CLI flags and launches the Test Explorer HTTP web server."""
  parser = argparse.ArgumentParser(description="BeToCQ Test Explorer")
  parser.add_argument(
      "results_path",
      nargs="?",
      default="",
      help="Path to local results directory or zip file",
  )
  parser.add_argument(
      "--results_dir",
      type=str,
      default="",
      help="Path to local results directory or zip file",
  )
  parser.add_argument(
      "--port",
      type=int,
      default=0,
      help="Port to run server on. If 0 or omitted, picks an available port.",
  )
  args = parser.parse_args()

  target_path = args.results_dir or args.results_path
  if target_path:
    print(f"[*] Started with results path: {target_path}")
    parsed = parse_target_path(target_path)
    if isinstance(parsed, mobly_parser.ParseResult):
      global TEST_RESULTS
      TEST_RESULTS = parsed
      print(f"[*] Successfully parsed {target_path}")
    elif isinstance(parsed, dict) and "error" in parsed:
      print(f"[!] Error parsing: {parsed['error']}")

  port = args.port or pick_unused_port()
  print(f"[*] Starting BeToCQ Test Explorer at http://localhost:{port}/ ...")
  threading.Timer(
      _BROWSER_OPEN_DELAY_SECONDS,
      lambda: webbrowser.open(f"http://localhost:{port}/"),
  ).start()

  class ReusableTCPServer(socketserver.TCPServer):
    """TCP server allowing immediate address reuse on restart."""

    allow_reuse_address = True

  with ReusableTCPServer(("", port), TestExplorerRequestHandler) as httpd:
    try:
      httpd.serve_forever()
    except KeyboardInterrupt:
      print("\n[*] Shutting down server.")


if __name__ == "__main__":
  main()
