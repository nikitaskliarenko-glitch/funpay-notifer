import pathlib

import pytest

from funpay_watch.single_instance import AlreadyRunning, single_instance


def test_lock_is_granted_when_nobody_holds_it(tmp_path):
    with single_instance(tmp_path / "funpay.db") as held:
        assert held is not None


def test_second_copy_is_refused_while_the_first_holds_the_lock(tmp_path):
    db = tmp_path / "funpay.db"

    with single_instance(db):
        with pytest.raises(AlreadyRunning, match="уже запущен"):
            with single_instance(db):
                pass


def test_lock_is_released_when_the_first_copy_finishes(tmp_path):
    db = tmp_path / "funpay.db"

    with single_instance(db):
        pass

    with single_instance(db):
        pass


def test_two_different_databases_do_not_block_each_other(tmp_path):
    with single_instance(tmp_path / "one.db"):
        with single_instance(tmp_path / "two.db"):
            pass


def test_refusal_names_the_database_so_the_cause_is_obvious(tmp_path):
    db = tmp_path / "funpay.db"

    with single_instance(db):
        with pytest.raises(AlreadyRunning, match="funpay.db"):
            with single_instance(db):
                pass


def test_a_separate_process_cannot_take_the_same_lock(tmp_path):
    """Настоящий случай из жизни: служба и запущенная руками копия."""
    import subprocess
    import sys
    import textwrap

    db = tmp_path / "funpay.db"
    probe = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, sys.argv[2])
        from funpay_watch.single_instance import AlreadyRunning, single_instance
        try:
            with single_instance(sys.argv[1]):
                print("ЗАХВАТИЛ")
        except AlreadyRunning:
            print("ОТКАЗАНО")
        """
    )
    root = str(pathlib.Path(__file__).resolve().parent.parent)

    def run_probe() -> str:
        done = subprocess.run(
            [sys.executable, "-c", probe, str(db), root],
            capture_output=True, text=True, timeout=60,
        )
        return done.stdout.strip()

    assert run_probe() == "ЗАХВАТИЛ", "без соперника замок обязан браться"

    with single_instance(db):
        assert run_probe() == "ОТКАЗАНО", "вторая копия обязана получить отказ"

    assert run_probe() == "ЗАХВАТИЛ", "после освобождения замок снова свободен"
