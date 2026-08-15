from scraper.play_by_play import has_pbp_table


def test_pbp_table_validation_uses_the_confirmed_table_id():
    assert has_pbp_table(b'<table id="pbp"><caption>Play-By-Play Table</caption></table>')
    assert not has_pbp_table(b'<h2>Play-By-Play</h2><table id="other"></table>')
