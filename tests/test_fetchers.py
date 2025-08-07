from pathlib import Path
import sys
from unittest.mock import MagicMock

sys.path.append(str(Path(__file__).resolve().parent.parent))
from fetchers.ogads_fetcher import _parse_offer_row
from fetchers.cpagrip_fetcher import _parse_payout, _validate_offer


def make_element(text=None, href=None):
    element = MagicMock()
    element.inner_text.return_value = text
    element.get_attribute.side_effect = lambda name: href if name == "href" else None
    return element


def test_parse_offer_row():
    row = MagicMock()
    row.query_selector.side_effect = lambda selector: {
        '.offer-name': make_element('Test Offer'),
        '.offer-payout': make_element('$5.00'),
        '.offer-device': make_element('Mobile'),
        '.offer-category': make_element('Games'),
        '.offer-link a': make_element(href='/offer/1'),
        '.offer-restrictions': make_element('No login, Reddit allowed'),
    }[selector]
    row.query_selector_all.side_effect = lambda selector: {
        '.offer-geo .geo-tag': [make_element('US'), make_element('CA')],
    }[selector]

    offer = _parse_offer_row(row)
    assert offer['name'] == 'Test Offer'
    assert offer['payout'] == 5.0
    assert offer['geo'] == ['US', 'CA']
    assert offer['url'] == 'https://ogads.com/offer/1'
    assert 'no-login' in offer['tags']
    assert 'Reddit-safe' in offer['tags']
    assert 'mobile' in offer['tags']


def test_parse_payout():
    assert _parse_payout('$1,234.56') == 1234.56
    assert _parse_payout('invalid') is None


def test_validate_offer():
    valid = {'name': 'A', 'url': 'http://a', 'geo': ['US'], 'payout': 1.0}
    invalid = {'name': 'B', 'url': '', 'geo': ['US'], 'payout': 1.0}
    assert _validate_offer(valid)
    assert not _validate_offer(invalid)
