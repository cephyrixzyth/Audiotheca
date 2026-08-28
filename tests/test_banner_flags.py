from scan_options import format_banner_flag


def test_format_banner_flag_on_off():
    assert format_banner_flag(True) == "on"
    assert format_banner_flag(False) == "off"


def test_format_banner_flag_skipped_wins_over_config_true():
    assert format_banner_flag(True, skipped=True) == "skipped"
    assert format_banner_flag(False, skipped=True) == "skipped"
