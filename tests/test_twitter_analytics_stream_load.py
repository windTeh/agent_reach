import importlib.util
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'twitter'
    / 'fetch_anycubic3dprint_analytics.py'
)


def load_module():
    spec = importlib.util.spec_from_file_location('twitter_analytics_fetcher', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_date_range_accepts_explicit_inclusive_dates():
    module = load_module()

    start_date, end_date = module.parse_date_range('2024-01-01', '2024-06-30')

    assert start_date == date(2024, 1, 1)
    assert end_date == date(2024, 6, 30)


def test_parse_date_range_rejects_reversed_dates():
    module = load_module()

    with pytest.raises(ValueError, match='start-date'):
        module.parse_date_range('2024-06-30', '2024-01-01')


def test_build_date_windows_stays_within_requested_dates():
    module = load_module()

    windows = list(module.build_date_windows(date(2024, 1, 1), date(2024, 1, 10), 4))

    assert windows == [
        (date(2024, 1, 7), date(2024, 1, 10)),
        (date(2024, 1, 3), date(2024, 1, 6)),
        (date(2024, 1, 1), date(2024, 1, 2)),
    ]


def test_doris_row_uses_execution_date_for_date_and_etl_date():
    module = load_module()
    source_row = {column: '' for column in module.COLUMNS}
    source_row.update({
        'Post id': '123',
        'Date': '2024-03-04 05:06',
        'Post text': 'A post',
        'Post Link': 'https://x.com/anycubic3dprint/status/123',
        'Impressions': 100,
        'Likes': 5,
    })

    row = module.to_doris_row(source_row, 'anycubic3dprint', date(2026, 8, 25))

    assert row['date'] == '2026-08-25'
    assert row['etl_date'] == '2026-08-25'
    assert row['page_name'] == 'anycubic3dprint'
    assert row['post_id'] == '123'
    assert row['post_date'] == '2024-03-04 05:06:00'
    assert row['impressions'] == 100
    assert row['likes'] == 5
    assert row['bookmarks'] == 0


def test_stream_load_posts_ndjson_and_rejects_non_success_status(tmp_path):
    module = load_module()
    config_path = tmp_path / 'credentials.ini'
    config_path.write_text(
        '[doris]\nhost = doris.example\nbe_port = 8040\nuser = alice\npassword = secret\n',
        encoding='utf-8',
    )
    response = Mock(status_code=200, text='bad load')
    response.json.return_value = {'Status': 'Fail', 'Message': 'bad load'}

    with patch.object(module, 'urlopen') as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = b'{"Status": "Fail", "Message": "bad load"}'
        with pytest.raises(RuntimeError, match='Doris Stream Load failed'):
            module.stream_load_rows([{'post_id': '123'}], config_path)

        request = urlopen.call_args[0][0]
        assert request.full_url == (
            'http://doris.example:8040/api/ods_social_media/'
            'ods_twitter_posts_analytics/_stream_load'
        )
        assert request.get_header('Content-type') == 'application/json'
        assert request.data == b'{"post_id": "123"}'


def test_stream_load_rejects_success_response_with_wrong_loaded_row_count(tmp_path):
    module = load_module()
    config_path = tmp_path / 'credentials.ini'
    config_path.write_text(
        '[doris]\nhost = doris.example\nbe_port = 8040\nuser = alice\npassword = secret\n',
        encoding='utf-8',
    )

    with patch.object(module, 'urlopen') as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"Status": "Success", "NumberLoadedRows": 0}'
        )
        with pytest.raises(RuntimeError, match='loaded 0 of 1 rows'):
            module.stream_load_rows([{'post_id': '123'}], config_path)
