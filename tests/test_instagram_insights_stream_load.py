import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'instagram'
    / 'fetch_fb_insights.py'
)


def load_module():
    spec = importlib.util.spec_from_file_location('instagram_insights_fetcher', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_date_range_accepts_explicit_dates():
    module = load_module()

    start_date, end_date = module.parse_date_range('2024-01-01', '2024-02-29')

    assert start_date == date(2024, 1, 1)
    assert end_date == date(2024, 2, 29)


def test_parse_date_range_rejects_reversed_dates():
    module = load_module()

    with pytest.raises(ValueError, match='start-date'):
        module.parse_date_range('2024-02-01', '2024-01-01')


def test_parse_instagram_business_ids_defaults_to_two_configured_accounts():
    module = load_module()

    assert module.parse_instagram_business_ids(None) == [
        '17841406045865168',
        '17841414725872019',
    ]


def test_to_doris_row_maps_meta_fields_and_converts_metric_units():
    module = load_module()
    source_row = {
        'row_id': 'ig-post-1',
        'entity_type': 'IG_POST',
        'owner': 'Anycubic',
        'title': 'New printer',
        'created_at': 1704067200,
        'image_uri': 'https://example.com/image.jpg',
        'metrics': {
            'views': 100,
            'net_reactions': 20,
            'net_comments': 3,
            'video_play_time': 90000,
            'video_average_play_time': 2500,
            'instream_ads_estimated_earnings': 1234,
        },
    }

    row = module.to_doris_row(source_row, date(2026, 8, 25))

    assert row['date'] == '2026-08-25'
    assert row['etl_date'] == '2026-08-25'
    assert row['post_id'] == 'ig-post-1'
    assert row['post_type'] == 'IG Post'
    assert row['owner'] == 'Anycubic'
    assert row['publish_time'] == '2024-01-01 08:00:00'
    assert row['views'] == 100
    assert row['likes_reactions'] == 20
    assert row['comments'] == 3
    assert row['video_play_time_min'] == 1.5
    assert row['avg_play_time_sec'] == 2.5
    assert row['instream_ads_earnings'] == 12.34
    assert row['shares'] == 0


def test_stream_load_posts_ndjson_and_checks_loaded_rows(tmp_path):
    module = load_module()
    config_path = tmp_path / 'credentials.ini'
    config_path.write_text(
        '[doris]\nhost = doris.example\nbe_port = 8040\nuser = alice\npassword = secret\n',
        encoding='utf-8',
    )

    with patch.object(module, 'urlopen') as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"Status": "Success", "NumberLoadedRows": 1, "Label": "load-1"}'
        )
        result = module.stream_load_rows([{'post_id': 'ig-post-1'}], config_path)

        request = urlopen.call_args[0][0]
        assert result['Label'] == 'load-1'
        assert request.full_url == (
            'http://doris.example:8040/api/ods_social_media/'
            'ods_instagram_post_insights/_stream_load'
        )
        assert request.get_header('Content-type') == 'application/json'
        assert request.data == b'{"post_id": "ig-post-1"}'


def test_stream_load_rejects_failed_doris_response(tmp_path):
    module = load_module()
    config_path = tmp_path / 'credentials.ini'
    config_path.write_text(
        '[doris]\nhost = doris.example\nbe_port = 8040\nuser = alice\npassword = secret\n',
        encoding='utf-8',
    )

    with patch.object(module, 'urlopen') as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"Status": "Fail", "Message": "bad load"}'
        )
        with pytest.raises(RuntimeError, match='Doris Stream Load failed'):
            module.stream_load_rows([{'post_id': 'ig-post-1'}], config_path)
