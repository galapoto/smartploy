import httpx
import pytest

from smartploy.service import SmartployService
from smartploy.sources.kuntarekry import (
    KuntarekryFeedAdapter,
    KuntarekryFeedError,
    KuntarekryFeedSettings,
    parse_kuntarekry_feed,
    validate_feed_url,
)
from smartploy.sources.polling import poll_feed
from smartploy.storage import MemoryJobRepository


SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example City</title>
    <item>
      <title>Data Analyst</title>
      <link>https://www.kuntarekry.fi/fi/tyopaikat/data-analyst-42/</link>
      <guid>42</guid>
      <description><![CDATA[Python and SQL <b>analytics</b>]]></description>
      <pubDate>Fri, 09 Oct 2026 12:00:00 +0300</pubDate>
      <location>Helsinki</location>
      <applicationDeadline>2026-10-20</applicationDeadline>
    </item>
  </channel>
</rss>
"""


def test_parse_kuntarekry_rss_into_source_observation():
    items = parse_kuntarekry_feed(
        SAMPLE,
        feed_url="https://feeds.kuntarekry.fi/example.xml?token=secret",
        observed_at="2026-10-10T01:00:00+00:00",
    )
    assert len(items) == 1
    item = items[0]
    assert item.source_id == "kuntarekry"
    assert item.source_mode == "feed"
    assert item.payload["company"] == "Example City"
    assert item.payload["role_title"] == "Data Analyst"
    assert item.payload["location"] == "Helsinki"
    assert item.payload["application_url"].startswith("https://www.kuntarekry.fi/")
    assert "token=secret" not in item.source_url
    assert item.source_external_id == "42"
    assert item.posted_at.startswith("2026-10-09T12:00:00")


@pytest.mark.parametrize(
    "url",
    [
        "http://kuntarekry.fi/feed.xml",
        "https://127.0.0.1/feed.xml",
        "https://evil.example/feed.xml",
        "https://user:pass@kuntarekry.fi/feed.xml",
        "https://kuntarekry.fi:8443/feed.xml",
    ],
)
def test_feed_url_ssrf_guards_fail_closed(url):
    with pytest.raises(KuntarekryFeedError):
        validate_feed_url(url)


def test_dtd_and_entity_declarations_are_rejected():
    content = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe "bad">]><rss></rss>'
    with pytest.raises(KuntarekryFeedError, match="DTD/entity"):
        parse_kuntarekry_feed(content, feed_url="https://kuntarekry.fi/feed.xml")


def test_adapter_fetches_allowed_feed_without_following_redirects():
    def handler(request):
        assert request.url.host == "feeds.kuntarekry.fi"
        return httpx.Response(200, content=SAMPLE, headers={"content-type": "application/rss+xml"})

    settings = KuntarekryFeedSettings(
        feed_url="https://feeds.kuntarekry.fi/example.xml?token=secret",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    adapter = KuntarekryFeedAdapter(settings, http_client=client)
    items = adapter.fetch(observed_at="2026-10-10T01:00:00+00:00")
    assert len(items) == 1


def test_successful_zero_result_poll_is_healthy_not_failure():
    class EmptyAdapter:
        source_id = "kuntarekry"
        parser_version = "fixture-v1"

        def policy(self):
            return KuntarekryFeedAdapter(
                KuntarekryFeedSettings(feed_url="https://kuntarekry.fi/feed.xml"),
                http_client=httpx.Client(
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"<rss/>"))
                ),
            ).policy()

        def fetch(self, *, observed_at=None):
            return []

    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)
    summary = poll_feed(
        service,
        EmptyAdapter(),
        attempted_at="2026-10-10T02:00:00+00:00",
    )
    assert summary.status == "healthy"
    assert summary.item_count == 0
    health = repository.get_source_health("kuntarekry")
    assert health is not None
    assert health.status == "healthy"
    assert health.last_item_count == 0


def test_failed_poll_records_failure_without_deleting_existing_state():
    class FailingAdapter:
        source_id = "kuntarekry"
        parser_version = "fixture-v1"

        def policy(self):
            return KuntarekryFeedAdapter(
                KuntarekryFeedSettings(feed_url="https://kuntarekry.fi/feed.xml"),
                http_client=httpx.Client(
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"<rss/>"))
                ),
            ).policy()

        def fetch(self, *, observed_at=None):
            raise KuntarekryFeedError("boom")

    repository = MemoryJobRepository()
    service = SmartployService(repository=repository)
    summary = poll_feed(
        service,
        FailingAdapter(),
        attempted_at="2026-10-10T03:00:00+00:00",
    )
    assert summary.status == "failed"
    health = repository.get_source_health("kuntarekry")
    assert health is not None
    assert health.status == "failed"
    assert health.consecutive_failures == 1
    assert "boom" in health.last_error
