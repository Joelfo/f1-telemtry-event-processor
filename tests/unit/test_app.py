from ep.app import build_parser, main


def test_parser_has_once_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["--once"])
    assert args.once is True


def test_main_once_exits_cleanly(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["ep.app", "--once"])
    assert main() == 0
