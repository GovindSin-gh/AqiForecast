from api.explain import numbers_ok, template

FACTS = {"city": "Lucknow", "when": "in the next hour", "aqi_p50": 172, "aqi_p10": 150,
         "aqi_p90": 198, "category": "Unhealthy", "trend": "rising", "wind_ms": 1.2, "rh": 78.0}


def test_accepts_text_using_only_given_numbers():
    assert numbers_ok("AQI near 172, between 150 and 198, wind 1.2 m/s.", FACTS)


def test_rejects_invented_numbers():
    assert not numbers_ok("AQI near 172 and will hit 250 tonight.", FACTS)


def test_template_mentions_key_numbers():
    t = template(FACTS)
    assert "172" in t and "150" in t and "198" in t
