from unittest import mock

from strictdoc.features.html2pdf import pdf_print_driver
from strictdoc.features.html2pdf.pdf_print_driver import PDFPrintDriver


def _print_command(monkeypatch, *, chromedriver, env):
    config = mock.Mock()
    config.get_path_to_cache_dir.return_value = "/tmp/cache"
    config.chromedriver = chromedriver
    config.chrome_binary = None
    config.html2pdf_disable_ssl_check = False
    config.html2pdf_strict = False
    if env is None:
        monkeypatch.delenv("STRICTDOC_CHROMEDRIVER", raising=False)
    else:
        monkeypatch.setenv("STRICTDOC_CHROMEDRIVER", env)
    monkeypatch.setattr(pdf_print_driver, "PDFPostprocessor", mock.Mock())
    run_ = mock.Mock()
    monkeypatch.setattr(pdf_print_driver, "run", run_)
    PDFPrintDriver.get_pdf_from_html(
        config, [("in.html", "out.pdf")], "/tmp/root"
    )
    return run_.call_args.args[0]


def test_001_no_driver_is_given_by_default(monkeypatch):
    cmd = _print_command(monkeypatch, chromedriver=None, env=None)
    assert "--chromedriver" not in cmd


def test_002_the_driver_of_the_environment_is_used(monkeypatch):
    cmd = _print_command(
        monkeypatch, chromedriver=None, env="/usr/bin/chromedriver"
    )
    assert cmd[cmd.index("--chromedriver") + 1] == "/usr/bin/chromedriver"


def test_003_the_driver_of_the_project_config_wins(monkeypatch):
    cmd = _print_command(
        monkeypatch, chromedriver="/opt/driver", env="/usr/bin/chromedriver"
    )
    assert cmd[cmd.index("--chromedriver") + 1] == "/opt/driver"
