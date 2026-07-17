from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "install.sh"


def test_update_leaves_replaceable_install_tree_before_running_pip() -> None:
    script = INSTALLER.read_text(encoding="utf-8")
    do_install = script.index("do_install() {")
    create_work_dir = script.index('    mkdir -p "$WORK_DIR"', do_install)
    stable_cwd = script.index('    cd "$WORK_DIR"', do_install)
    replace_application = script.index('rm -rf "$INSTALL_DIR"/{application', do_install)
    pip_install = script.index('"$venv_python" -m pip install --upgrade pip', do_install)

    assert create_work_dir < stable_cwd < replace_application < pip_install


def test_update_uses_disk_backed_work_directory() -> None:
    script = INSTALLER.read_text(encoding="utf-8")

    assert 'WORK_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/$APP_NAME/tmp"' in script
    assert 'WORK_DIR="/var/cache/$APP_NAME/tmp"' in script
    assert 'local temp_tar="$WORK_DIR/$APP_NAME-latest.tar.gz"' in script
    assert '"$WORK_DIR/$APP_NAME-books-backup"' in script
    assert '"/tmp/$APP_NAME-books-backup"' not in script
    assert '"/tmp/$APP_NAME-latest.tar.gz"' not in script


def test_update_rebuilds_venv_and_uses_its_python_for_pip() -> None:
    script = INSTALLER.read_text(encoding="utf-8")

    assert 'rm -rf "$venv_path"' in script
    assert 'local venv_python="$venv_path/bin/python3"' in script
    assert '"$venv_path/bin/pip" install' not in script
    assert script.count('"$venv_python" -m pip install') == 3


def test_generated_update_wrapper_changes_to_stable_directory() -> None:
    script = INSTALLER.read_text(encoding="utf-8")
    update_case = script.index("    update|--update)")
    invoke_installer = script.index('bash "$INSTALL_DIR/install.sh" --update', update_case)
    create_work_dir = script.index('        mkdir -p "\\$WORK_DIR" || exit 1', update_case)
    stable_cwd = script.index('        cd "\\$WORK_DIR" || exit 1', update_case)

    assert create_work_dir < stable_cwd < invoke_installer
