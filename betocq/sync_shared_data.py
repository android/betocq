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

"""CLI tool to sync data filed to the BeToCQ directory."""

from collections.abc import Sequence
import os
import pathlib
import shutil
import subprocess

from betocq import resource_utils

_BETOCQ_REPO = 'https://github.com/android/betocq'
_BETOCQ_SYNCED_RESOURCE_DIR = 'betocq/synced_resource_data'


def _verify_in_workspace() -> None:
  """Verifies that the current working directory is within a workspace."""
  if not os.getcwd().startswith('/google/src/cloud/'):
    raise RuntimeError('This script must be run from within a workspace.')
  if not os.getcwd().endswith('/google3'):
    raise RuntimeError('This script must be run from the root of a workspace.')


def _resolve_output_files(config: resource_utils.SharedData) -> Sequence[str]:
  """Resolves output files for the given shared data dependency."""
  if config.data_type == 'source':
    return [config.target.replace('//', '').replace(':', '/')]
  command = config.build_command()
  print(f'Building: {" ".join(command)}')
  build = subprocess.run(command, check=True, capture_output=True)
  output_lines = build.stderr.decode('utf-8').strip().split('\n')
  trimmed_lines = [line.strip() for line in output_lines]
  sponge_lines = [line for line in trimmed_lines if 'sponge' in line]
  print(sponge_lines[0])  # Print the Sponge link for reference.
  return [line for line in trimmed_lines if line.startswith('blaze-bin/')]


def _copy_output(
    output_file: str, root: str, data_config: resource_utils.SharedData
) -> None:
  """Copies the given output file to the specified root directory."""
  print(f'Copying {output_file} to outputs')
  src_dirname = os.path.dirname(output_file)
  if data_config.data_type == 'output':
    # Output files have blaze-bin as a prefix, which needs to be removed for
    # the final destination path.
    if not output_file.startswith('blaze-bin/'):
      raise AssertionError(
          f'Unexpected output file: {output_file} does not start with'
          ' blaze-bin/'
      )
    dest_dirname = os.path.join(root, src_dirname.replace('blaze-bin/', '', 1))
  else:
    dest_dirname = os.path.join(root, src_dirname)
  os.makedirs(dest_dirname, exist_ok=True)
  shutil.copy(output_file, dest_dirname)


def _generate_data_files(dest_dir: str) -> None:
  """Generates data files and copies them to the specified directory."""
  os.makedirs(dest_dir, exist_ok=True)
  for data_config in resource_utils.shared_data_configs():
    output_files = _resolve_output_files(data_config)
    for output_file in output_files:
      _copy_output(output_file, dest_dir, data_config)


def _get_sync_cl() -> int:
  """Returns the CL # the client is synced to."""
  return int(
      subprocess.run(['srcfs', 'get_readonly'], check=True, capture_output=True)
      .stdout.decode('utf-8')
      .strip()
  )


def _setup_repo(cl: int) -> str:
  """Clones the BeToCQ repo and prepares a new branch for the sync.

  Args:
    cl: The currently synced CL.

  Returns:
    The path to the cloned repo.
  """
  home = pathlib.Path.home()
  cl_tag = f'cl{cl}'
  repo_parent = os.path.join(home, 'betocq-shared-data-sync', cl_tag)
  shutil.rmtree(repo_parent, ignore_errors=True)  # Remove any previous result.
  os.makedirs(repo_parent)
  subprocess.run(
      [
          'git',
          'clone',
          '--depth',
          '1',
          _BETOCQ_REPO,
      ],
      check=True,
      cwd=repo_parent,
  )
  branch_name = f'betocq-shared-data-sync-{cl_tag}'
  repo_dir = os.path.join(repo_parent, 'betocq')
  subprocess.run(
      ['git', 'checkout', '-b', branch_name],
      check=True,
      cwd=repo_dir,
  )
  # Delete existing resources from the new branch as they will be replaced.
  branch_resource_dir = os.path.join(repo_dir, _BETOCQ_SYNCED_RESOURCE_DIR)
  shutil.rmtree(branch_resource_dir, ignore_errors=True)
  print(f'Cloned {_BETOCQ_REPO} at {repo_dir} and set up branch {branch_name}')
  return repo_dir


def _commit_changes(repo_root: str):
  """Commits the changes to the BeToCQ repo."""

  def _run_git_command(command: list[str]) -> None:
    subprocess.run(['git'] + command, check=True, cwd=repo_root)

  _run_git_command(['add', '--all'])
  _run_git_command(['commit', '-m', 'Update BeToCQ shared data.'])
  _run_git_command(['--no-pager', 'show', '--summary'])
  print('Successfully built and committed artifacts!')
  print(f'`cd {repo_root}`, review the changes, and `git push` to sync.')


def main() -> None:
  _verify_in_workspace()
  cl = _get_sync_cl()
  repo_root = _setup_repo(cl)
  output_root = os.path.join(repo_root, _BETOCQ_SYNCED_RESOURCE_DIR, 'google3')
  _generate_data_files(output_root)
  _commit_changes(repo_root)


if __name__ == '__main__':
  main()
