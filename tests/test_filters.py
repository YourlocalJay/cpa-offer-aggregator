from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
from filters import filter_offers


def test_geo_filtering():
    offers = [
        {
            "name": "US Offer",
            "geo": ["US"],
            "device": "Android",
            "payout": 2,
            "category": "Giveaways",
            "tags": ["safe"],
        },
        {
            "name": "CA Offer",
            "geo": ["CA"],
            "device": "Android",
            "payout": 2,
            "category": "Giveaways",
            "tags": ["safe"],
        },
    ]

    result = filter_offers(
        offers,
        geo="US",
        categories=["Giveaways"],
        required_tags=["safe"],
    )

    assert len(result) == 1
    assert result[0]["name"] == "US Offer"


def test_device_filtering():
    offers = [
        {
            "name": "Android Offer",
            "geo": ["US"],
            "device": "Android",
            "payout": 2,
            "category": "Giveaways",
            "tags": ["safe"],
        },
        {
            "name": "iOS Offer",
            "geo": ["US"],
            "device": "iOS",
            "payout": 2,
            "category": "Giveaways",
            "tags": ["safe"],
        },
    ]

    result = filter_offers(
        offers,
        device="Android",
        categories=["Giveaways"],
        required_tags=["safe"],
    )

    assert len(result) == 1
    assert result[0]["name"] == "Android Offer"


def test_payout_filtering():
    offers = [
        {
            "name": "Low",
            "geo": ["US"],
            "device": "Android",
            "payout": 0.5,
            "category": "Giveaways",
            "tags": ["safe"],
        },
        {
            "name": "Mid",
            "geo": ["US"],
            "device": "Android",
            "payout": 2,
            "category": "Giveaways",
            "tags": ["safe"],
        },
        {
            "name": "High",
            "geo": ["US"],
            "device": "Android",
            "payout": 10,
            "category": "Giveaways",
            "tags": ["safe"],
        },
    ]

    result = filter_offers(
        offers,
        min_payout=1,
        max_payout=5,
        categories=["Giveaways"],
        required_tags=["safe"],
    )

    assert [o["name"] for o in result] == ["Mid"]


def test_category_filtering():
    offers = [
        {
            "name": "Give",
            "geo": ["US"],
            "device": "Android",
            "payout": 2,
            "category": "Giveaways",
            "tags": ["safe"],
        },
        {
            "name": "Mobile",
            "geo": ["US"],
            "device": "Android",
            "payout": 2,
            "category": "Mobile Submits",
            "tags": ["safe"],
        },
    ]

    result = filter_offers(
        offers,
        categories=["Giveaways"],
        required_tags=["safe"],
    )

    assert [o["name"] for o in result] == ["Give"]


def test_tag_filtering():
    offers = [
        {
            "name": "Required",
            "geo": ["US"],
            "device": "Android",
            "payout": 2,
            "category": "Giveaways",
            "tags": ["needed"],
        },
        {
            "name": "Missing",
            "geo": ["US"],
            "device": "Android",
            "payout": 2,
            "category": "Giveaways",
            "tags": [],
        },
        {
            "name": "Excluded",
            "geo": ["US"],
            "device": "Android",
            "payout": 2,
            "category": "Giveaways",
            "tags": ["avoid"],
        },
    ]

    result = filter_offers(
        offers,
        categories=["Giveaways"],
        required_tags=["needed"],
        excluded_tags=["avoid"],
    )

    assert [o["name"] for o in result] == ["Required"]

