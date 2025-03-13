from data_model.func import bs_filename_to_date

def test_bs_filename_to_date():
    assert 2==2
    test_data = "boxscores_202105160TOR.html"
    assert "20210516" == bs_filename_to_date(test_data)
