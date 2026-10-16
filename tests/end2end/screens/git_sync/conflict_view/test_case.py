import subprocess
import tempfile

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.server import SDocTestServer


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def edit(folder, old, new, message):
    path = f"{folder}/spec.sdoc"
    with open(path, encoding="utf8") as file_:
        text = file_.read()
    with open(path, "w", encoding="utf8") as file_:
        file_.write(text.replace(old, new))
    git(folder, "commit", "-q", "-am", message)


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        sandbox = test_setup.path_to_sandbox

        # The project is a repository with an origin, and somebody else has a
        # clone: both change the same requirement, and different ones too.
        other_root = tempfile.mkdtemp()
        origin = f"{other_root}/origin.git"
        other = f"{other_root}/other"
        git(sandbox, "init", "-q", "-b", "main")
        git(sandbox, "add", "-A")
        git(sandbox, "commit", "-q", "-m", "init")
        git(other_root, "init", "-q", "--bare", "-b", "main", origin)
        git(sandbox, "remote", "add", "origin", origin)
        git(sandbox, "push", "-q", "-u", "origin", "main")
        git(other_root, "clone", "-q", origin, other)
        edit(other, "shall start.", "shall start at once.", "server")
        edit(other, "shall stop.", "shall stop safely.", "server 2")
        git(other, "push", "-q")
        edit(sandbox, "shall start.", "shall start with the OBCP ID.", "local")

        with SDocTestServer(input_path=sandbox) as test_server:
            self.open(test_server.get_host_and_port() + "/git/sync")
            self.click("[data-testid='sync-now']")

            # Both changed R-1: the view of the conflicts, one conflict.
            self.assert_element("[data-testid='sync-row-conflict']")
            self.assert_text("0 / 1")
            self.assert_element("[data-testid='sync-row-server']")
            self.assert_text("start at once", "[data-testid='sync-sheets']")
            self.assert_text(
                "start with the OBCP ID", "[data-testid='sync-sheets']"
            )
            assert (
                self.get_attribute("[data-testid='sync-finish']", "disabled")
                is not None
            )

            # The page of the synchronization lists the document that waits.
            self.open(test_server.get_host_and_port() + "/git/sync")
            self.assert_element("[data-testid='sync-conflicts']")

            self.open(
                test_server.get_host_and_port()
                + "/git/sync/conflicts?file=spec.sdoc"
            )
            self.click("[data-testid='sync-keep-server']")
            self.assert_text("1 / 1")
            self.click("[data-testid='sync-finish']")
            self.assert_element("[data-testid='sync-now']")

        merged = git(sandbox, "show", "HEAD:spec.sdoc")
        assert "start at once" in merged and "OBCP ID" not in merged
        assert "stop safely" in merged
        assert git(origin, "log", "--oneline", "-1") == git(
            sandbox, "log", "--oneline", "-1"
        )
