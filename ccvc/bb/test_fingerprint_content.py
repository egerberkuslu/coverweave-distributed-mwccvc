"""code_fingerprint hashes code content: touch and copy leave it, byte edits move it."""
import os
import shutil

from ccvc.bb import sweep as S

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(S.__file__))))


def _copy_tree(dst):
    for rel in S.measurement_files(ROOT):
        os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), os.path.join(dst, rel))
    return str(dst)


def test_file_set_is_the_measurement_path_without_tests_or_reporting():
    files = S.measurement_files(ROOT)
    names = {os.path.basename(f)[:-3] for f in files}
    for must in ("sweep", "bbcvc", "simnet", "validate", "anneal", "bridge", "central"):
        assert must in names, must
    assert "ccvc/greedy/distributed.py" in files
    assert not any(n.startswith("test_") for n in names)
    reporting = {m.rsplit(".", 1)[-1] for m in S.REPORTING_MODULES}
    assert not names & reporting
    assert list(files) == sorted(files)


def test_copy_and_touch_keep_it_and_byte_edits_move_it(tmp_path):
    live = S.code_fingerprint()
    assert len(live) == 12
    root = _copy_tree(tmp_path)
    assert S.code_fingerprint(root) == live, "a copy of the same bytes must match"

    simnet = os.path.join(root, "ccvc", "bb", "simnet.py")
    st = os.stat(simnet)
    os.utime(simnet, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert S.code_fingerprint(root) == live, "mtime is not content"

    with open(simnet, "ab") as fh:
        fh.write(b"\n")
    assert S.code_fingerprint(root) != live, "one byte changed, hash did not"


def test_reporting_edits_do_not_move_it_and_new_imports_are_followed(tmp_path):
    root = _copy_tree(tmp_path)
    armnames = os.path.join(root, "ccvc", "bb", "armnames.py")
    shutil.copy(os.path.join(ROOT, "ccvc", "bb", "armnames.py"), armnames)
    before = S.code_fingerprint(root)
    assert "ccvc/bb/armnames.py" not in S.measurement_files(root)
    with open(armnames, "a") as fh:
        fh.write("\nX = 1\n")
    S.measurement_files.cache_clear()
    assert S.code_fingerprint(root) == before

    other = _copy_tree(tmp_path / "other")
    with open(os.path.join(other, "ccvc", "bb", "lossmodel.py"), "w") as fh:
        fh.write("P = 0.1\n")
    with open(os.path.join(other, "ccvc", "bb", "simnet.py"), "a") as fh:
        fh.write("\n\ndef _late():\n    from ccvc.bb import lossmodel\n")
    assert "ccvc/bb/lossmodel.py" in S.measurement_files(other)
