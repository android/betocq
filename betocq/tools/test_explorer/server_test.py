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

"""Unit tests for BeToCQ Test Explorer HTTP server."""

import email.message
import io
import json
import os
import shutil
import tempfile
import zipfile

from absl.testing import absltest

from betocq.tools.test_explorer import server


class DummyRequestHandler(server.TestExplorerRequestHandler):

  rfile: io.BytesIO
  wfile: io.BytesIO

  def __init__(self, path: str = "/", headers: dict[str, str] | None = None):
    self.path = path
    msg = email.message.Message()
    if headers:
      for k, v in headers.items():
        msg[k] = v
    self.headers = msg
    self.rfile = io.BytesIO()
    self.wfile = io.BytesIO()
    self.response_status = 0
    self.response_headers: dict[str, str] = {}

  def send_response(self, code: int, message: str | None = None) -> None:
    self.response_status = code

  def send_header(self, keyword: str, value: str) -> None:
    self.response_headers[keyword] = value

  def end_headers(self) -> None:
    pass

  def send_error(
      self, code: int, message: str | None = None, explain: str | None = None
  ) -> None:
    self.response_status = code


class ServerTest(absltest.TestCase):

  def setUp(self) -> None:
    super().setUp()
    server.TEST_RESULTS = {"summary": {}, "test_classes": {}}

  def test_get_template_html(self) -> None:
    html_bytes = server.get_template_html()
    self.assertIsInstance(html_bytes, bytes)
    self.assertIn(b"<!DOCTYPE html>", html_bytes)
    self.assertIn(b"bg-white text-red-700", html_bytes)
    self.assertNotIn(b"bg-gray-900", html_bytes)
    self.assertIn(b"getIterationArtifacts", html_bytes)
    self.assertIn(b"Logcat", html_bytes)
    self.assertIn(b"Bugreport", html_bytes)

  def test_send_json(self) -> None:
    handler = DummyRequestHandler()
    data = {"status": "ok"}
    handler._send_json(data, 200)

    self.assertEqual(handler.response_status, 200)
    self.assertEqual(
        handler.response_headers.get("Content-Type"), "application/json"
    )

    output = json.loads(handler.wfile.getvalue().decode("utf-8"))
    self.assertEqual(output, {"status": "ok"})

  def test_handle_index(self) -> None:
    handler = DummyRequestHandler(path="/")
    handler._handle_index()

    self.assertEqual(handler.response_status, 200)
    self.assertIn("text/html", handler.response_headers.get("Content-Type", ""))
    self.assertNotEmpty(handler.wfile.getvalue())

  def test_handle_artifact_success(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      test_file = os.path.join(temp_dir, "sample.log")
      with open(test_file, "w", encoding="utf-8") as f:
        f.write("Test artifact content")

      server.TEST_RESULTS = {"results_dir": temp_dir}
      handler = DummyRequestHandler(path="/api/artifact?path=sample.log")
      handler._handle_artifact()

      self.assertEqual(handler.response_status, 200)
      output = json.loads(handler.wfile.getvalue().decode("utf-8"))
      self.assertEqual(output["filename"], "sample.log")
      self.assertEqual(output["content"], "Test artifact content")

  def test_handle_artifact_not_found_or_traversal(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      server.TEST_RESULTS = {"results_dir": temp_dir}

      # File does not exist
      handler = DummyRequestHandler(path="/api/artifact?path=nonexistent.log")
      handler._handle_artifact()
      self.assertEqual(handler.response_status, 404)

      # Path traversal attempt
      handler_traversal = DummyRequestHandler(
          path="/api/artifact?path=../../etc/passwd"
      )
      handler_traversal._handle_artifact()
      self.assertEqual(handler_traversal.response_status, 404)

      # Path traversal attempt with matching directory prefix
      sibling_dir = temp_dir + "-private"
      os.makedirs(sibling_dir, exist_ok=True)
      secret_file = os.path.join(sibling_dir, "secret.txt")
      with open(secret_file, "w", encoding="utf-8") as f:
        f.write("secret")
      try:
        rel_path = f"../{os.path.basename(sibling_dir)}/secret.txt"
        handler_prefix = DummyRequestHandler(
            path=f"/api/artifact?path={rel_path}"
        )
        handler_prefix._handle_artifact()
        self.assertEqual(handler_prefix.response_status, 404)
      finally:
        shutil.rmtree(sibling_dir, ignore_errors=True)

  def test_handle_download_success(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      test_file = os.path.join(temp_dir, "data.bin")
      with open(test_file, "wb") as f:
        f.write(b"\x00\x01\x02\x03")

      server.TEST_RESULTS = {"results_dir": temp_dir}
      handler = DummyRequestHandler(path="/api/download?path=data.bin")
      handler._handle_download()

      self.assertEqual(handler.response_status, 200)
      self.assertIn(
          'attachment; filename="data.bin"',
          handler.response_headers.get("Content-Disposition", ""),
      )
      self.assertEqual(handler.wfile.getvalue(), b"\x00\x01\x02\x03")

  def test_handle_download_not_found(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      server.TEST_RESULTS = {"results_dir": temp_dir}
      handler = DummyRequestHandler(path="/api/download?path=missing.bin")
      handler._handle_download()
      self.assertEqual(handler.response_status, 404)

  def test_extract_zip_payload(self) -> None:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    content_type = f"multipart/form-data; boundary={boundary}"
    zip_bytes = b"PK\x03\x04mockzipcontent"

    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="test.zip"\r\n'
        "Content-Type: application/zip\r\n\r\n"
    ).encode("utf-8") + zip_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    payload = server._extract_zip_payload(body, content_type)
    self.assertEqual(payload, zip_bytes)

  def test_do_post_invalid_content_type(self) -> None:
    handler = DummyRequestHandler(
        path="/api/upload", headers={"Content-Type": "application/json"}
    )
    handler.do_POST()
    self.assertEqual(handler.response_status, 400)
    output = json.loads(handler.wfile.getvalue().decode("utf-8"))
    self.assertEqual(output["error"], "Expected multipart/form-data")

  def test_do_post_invalid_path(self) -> None:
    handler = DummyRequestHandler(
        path="/invalid_endpoint",
        headers={"Content-Type": "multipart/form-data"},
    )
    handler.do_POST()
    self.assertEqual(handler.response_status, 404)

  def test_cleanup_uploaded_temp_dirs(self) -> None:
    temp_dir = tempfile.mkdtemp()
    self.assertTrue(os.path.exists(temp_dir))
    server.UPLOAD_TEMP_DIRS.append(temp_dir)

    server.cleanup_uploaded_temp_dirs()

    self.assertFalse(os.path.exists(temp_dir))
    self.assertEmpty(server.UPLOAD_TEMP_DIRS)

  def test_do_post_bad_zip_cleans_up_temp_dir(self) -> None:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    content_type = f"multipart/form-data; boundary={boundary}"
    corrupted_zip = b"invalid_zip_content"

    header = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="test.zip"\r\n'
        "Content-Type: application/zip\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + corrupted_zip + footer

    handler = DummyRequestHandler(
        path="/api/upload", headers={"Content-Type": content_type}
    )
    handler.rfile = io.BytesIO(body)
    handler.headers["Content-Length"] = str(len(body))

    handler.do_POST()
    self.assertEqual(handler.response_status, 400)
    self.assertEmpty(server.UPLOAD_TEMP_DIRS)

  def test_do_post_zip_slip_rejected(self) -> None:
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
      zf.writestr("../../evil.txt", "malicious content")
    zip_bytes = zip_buf.getvalue()

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    content_type = f"multipart/form-data; boundary={boundary}"
    header = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="test.zip"\r\n'
        "Content-Type: application/zip\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + zip_bytes + footer

    handler = DummyRequestHandler(
        path="/api/upload", headers={"Content-Type": content_type}
    )
    handler.rfile = io.BytesIO(body)
    handler.headers["Content-Length"] = str(len(body))

    handler.do_POST()
    self.assertEqual(handler.response_status, 400)
    output = json.loads(handler.wfile.getvalue().decode("utf-8"))
    self.assertIn("unsafe path", output["error"])
    self.assertEmpty(server.UPLOAD_TEMP_DIRS)

  def test_parse_target_path_zip(self) -> None:
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "test.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
      zf.writestr(
          "test_summary.yaml",
          "Type: Record\nTest Class: C\nTest Name: T\nResult: PASS\n",
      )

    try:
      parsed = server.parse_target_path(zip_path)
      self.assertIsInstance(parsed, server.mobly_parser.ParseResult)
      self.assertIn(parsed.results_dir, server.UPLOAD_TEMP_DIRS)
    finally:
      shutil.rmtree(temp_dir, ignore_errors=True)

  def test_parse_target_path_directory(self) -> None:
    temp_dir = tempfile.mkdtemp()
    with open(
        os.path.join(temp_dir, "test_summary.yaml"), "w", encoding="utf-8"
    ) as f:
      f.write("Type: Record\nTest Class: C\nTest Name: T\nResult: PASS\n")

    try:
      parsed = server.parse_target_path(temp_dir)
      self.assertIsInstance(parsed, server.mobly_parser.ParseResult)
      self.assertEmpty(server.UPLOAD_TEMP_DIRS)
    finally:
      shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
  absltest.main()
