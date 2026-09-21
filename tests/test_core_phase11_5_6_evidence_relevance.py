import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


import research.public_factual_research as public_research
from research.deep_research import research_quality_snapshot
from research.research_worker import (
    _run_public_research_pass,
    _source_index_from_research_result,
)


GARMIN_TOPIC = "the current Garmin smartwatch models"


def _search_result(*items):
    return {
        "success": True,
        "results": list(items),
    }


def _result(title, url, snippet=""):
    return {
        "title": title,
        "url": url,
        "content": snippet,
        "score": 1.0,
        "published_date": None,
    }


def _read(content):
    return {
        "success": True,
        "content": content,
    }


def _run_gather_with_tools(*, query, search_result, reads):
    original_execute_tool = public_research.execute_tool
    calls = []

    def fake_execute_tool(name, arguments):
        calls.append((name, dict(arguments)))

        if name == "web_search":
            return search_result

        if name == "web_read":
            return reads[arguments["url"]]

        raise AssertionError("Unexpected tool: " + str(name))

    public_research.execute_tool = fake_execute_tool

    try:
        result = public_research.gather_public_factual_research(
            query,
            max_reads=4,
            research_identity=GARMIN_TOPIC,
        )
    finally:
        public_research.execute_tool = original_execute_tool

    return result, calls


def run():
    # --------------------------------------------------
    # 1. site: constraints are enforced by Core even when search ignores them.
    # --------------------------------------------------

    site_query = "site:garmin.com press release smartwatch lineup 2026"

    site_result, site_calls = _run_gather_with_tools(
        query=site_query,
        search_result=_search_result(
            _result(
                "President Trump Holds a Press Conference, Jan. 3, 2026",
                "https://www.youtube.com/watch?v=bad1",
            ),
            _result(
                "National Press Club: Homepage",
                "https://www.press.org",
            ),
            _result(
                "How To: Overhead Press",
                "https://www.youtube.com/watch?v=bad2",
            ),
            _result(
                "Garmin announces the fenix 9 and fenix 9 Pro GPS smartwatch",
                "https://www.garmin.com/en-US/newsroom/fenix9",
                "Garmin introduced fenix 9 multisport GPS smartwatches.",
            ),
        ),
        reads={
            "https://www.garmin.com/en-US/newsroom/fenix9": _read(
                "Garmin introduced the fenix 9 and fenix 9 Pro multisport GPS smartwatches."
            ),
        },
    )

    assert site_result["success"] is True
    assert site_result["accepted_source_count"] == 1
    assert site_result["readable_source_count"] == 1
    assert site_result["rejected_source_count"] == 3
    assert len(site_result["sources"]) == 1
    assert site_result["sources"][0]["source_host"] == "garmin.com"

    read_urls = [
        arguments["url"]
        for name, arguments in site_calls
        if name == "web_read"
    ]

    assert read_urls == [
        "https://www.garmin.com/en-US/newsroom/fenix9"
    ]

    rejected_titles = {
        item.get("title")
        for item in site_result["rejected_sources"]
    }

    assert "President Trump Holds a Press Conference, Jan. 3, 2026" in rejected_titles
    assert "National Press Club: Homepage" in rejected_titles
    assert "How To: Overhead Press" in rejected_titles

    site_packet = public_research.build_internal_public_factual_packet(site_result)

    assert "fenix 9" in site_packet
    assert "President Trump" not in site_packet
    assert "Overhead Press" not in site_packet

    # --------------------------------------------------
    # 2. Query-token collisions do not bypass durable topic identity.
    #    "Venu" audio hardware is not Garmin evidence.
    # --------------------------------------------------

    venu_result, _ = _run_gather_with_tools(
        query="Garmin Venu 4 specifications availability",
        search_result=_search_result(
            _result(
                "Venu 208i | Active Dual 8-Inch Subwoofer | Void Acoustics",
                "https://voidacoustics.com/products/venu/venu208i",
                "Venu 208i active subwoofer.",
            ),
            _result(
                "Garmin Venu 4 review and specifications",
                "https://example.com/garmin-venu-4",
                "Garmin Venu 4 smartwatch specifications and availability.",
            ),
        ),
        reads={
            "https://voidacoustics.com/products/venu/venu208i": _read(
                "The Venu 208i is an active dual 8-inch subwoofer for installed audio systems."
            ),
            "https://example.com/garmin-venu-4": _read(
                "Garmin Venu 4 is a Garmin smartwatch with health and fitness features."
            ),
        },
    )

    assert venu_result["accepted_source_count"] == 1
    assert venu_result["rejected_source_count"] == 1

    accepted_urls = {
        source["url"]
        for source in venu_result["sources"]
        if source.get("accepted_as_evidence")
    }

    assert accepted_urls == {
        "https://example.com/garmin-venu-4"
    }

    venu_packet = public_research.build_internal_public_factual_packet(venu_result)

    assert "voidacoustics.com" not in venu_packet
    assert "subwoofer" not in venu_packet.lower()

    # --------------------------------------------------
    # 3. "Instinct" collision with AMD is rejected; Garmin evidence survives.
    # --------------------------------------------------

    instinct_result, _ = _run_gather_with_tools(
        query="Garmin Instinct 3 series all variants current models",
        search_result=_search_result(
            _result(
                "AMD Instinct MI350 Series GPUs",
                "https://www.amd.com/en/products/accelerators/instinct/mi350.html",
                "AMD Instinct accelerators for AI workloads.",
            ),
            _result(
                "Garmin Instinct 3 Series current models",
                "https://example.net/garmin-instinct-3",
                "Garmin Instinct 3 rugged smartwatch lineup.",
            ),
        ),
        reads={
            "https://www.amd.com/en/products/accelerators/instinct/mi350.html": _read(
                "AMD Instinct MI350 GPUs accelerate artificial intelligence and HPC workloads."
            ),
            "https://example.net/garmin-instinct-3": _read(
                "Garmin Instinct 3 is a rugged Garmin GPS smartwatch series."
            ),
        },
    )

    assert instinct_result["accepted_source_count"] == 1
    assert instinct_result["rejected_source_count"] == 1

    instinct_packet = public_research.build_internal_public_factual_packet(instinct_result)

    assert "AMD Instinct" not in instinct_packet
    assert "garmin-instinct-3" in instinct_packet

    # --------------------------------------------------
    # 4. Worker source index contains evidence only: unreadable/rejected pages
    #    cannot inflate source or unique-host quality floors.
    # --------------------------------------------------

    mixed_result = {
        "sources": [
            {
                "title": "Accepted Garmin source",
                "url": "https://accepted.example/garmin",
                "source_host": "accepted.example",
                "source_quality": "general_web",
                "published_date": None,
                "read_success": True,
                "accepted_as_evidence": True,
                "relevance_status": "accepted",
            },
            {
                "title": "Rejected collision",
                "url": "https://amd.com/instinct",
                "source_host": "amd.com",
                "source_quality": "general_web",
                "published_date": None,
                "read_success": True,
                "accepted_as_evidence": False,
                "relevance_status": "rejected",
            },
            {
                "title": "Unreadable page",
                "url": "https://unreadable.example/item",
                "source_host": "unreadable.example",
                "source_quality": "general_web",
                "published_date": None,
                "read_success": False,
            },
        ]
    }

    indexed = _source_index_from_research_result(mixed_result)

    assert len(indexed) == 1
    assert indexed[0]["url"] == "https://accepted.example/garmin"

    quality = research_quality_snapshot(
        {"depth": "deep"},
        {
            "rounds": [{}, {}, {}],
            "source_index": [
                indexed[0],
                {
                    "url": "https://amd.com/instinct",
                    "source_host": "amd.com",
                    "read_success": True,
                    "accepted_as_evidence": False,
                    "relevance_status": "rejected",
                },
                {
                    "url": "https://unreadable.example/item",
                    "source_host": "unreadable.example",
                    "read_success": False,
                },
            ],
            "rejected_source_count": 2,
        },
    )

    assert quality["source_count"] == 1
    assert quality["unique_host_count"] == 1
    assert quality["rejected_source_count"] == 2
    assert quality["minimum_floor_met"] is False

    # --------------------------------------------------
    # 5. Worker passes durable research identity when supported, while retaining
    #    compatibility with older injected research functions used by tests.
    # --------------------------------------------------

    captured = {}

    def context_aware_research(query, max_reads=2, research_identity=None):
        captured["identity"] = research_identity
        return {
            "success": True,
            "query": query,
            "readable_source_count": 1,
            "sources": [{
                "title": "Garmin evidence",
                "url": "https://example.org/garmin",
                "source_host": "example.org",
                "source_quality": "general_web",
                "published_date": None,
                "read_success": True,
                "read_result": _read(
                    "Garmin smartwatch evidence."
                ),
            }],
            "failure_reason": None,
        }

    research_result, _ = _run_public_research_pass(
        query="Garmin smartwatch lineup",
        job={
            "topic": GARMIN_TOPIC,
            "goal": "Research the current Garmin smartwatch models",
            "original_request": "Research the current Garmin smartwatch models",
            "depth": "deep",
        },
        research_fn=context_aware_research,
        packet_builder=lambda result: "packet",
    )

    assert captured["identity"] == GARMIN_TOPIC
    assert research_result["accepted_source_count"] == 1

    legacy_calls = []

    def legacy_research(query, max_reads=2):
        legacy_calls.append((query, max_reads))
        return {
            "success": True,
            "query": query,
            "readable_source_count": 1,
            "sources": [{
                "title": "Garmin evidence",
                "url": "https://legacy.example/garmin",
                "source_host": "legacy.example",
                "source_quality": "general_web",
                "published_date": None,
                "read_success": True,
                "read_result": _read(
                    "Garmin smartwatch evidence."
                ),
            }],
            "failure_reason": None,
        }

    legacy_result, _ = _run_public_research_pass(
        query="Garmin smartwatch lineup",
        job={
            "topic": GARMIN_TOPIC,
            "goal": "Research the current Garmin smartwatch models",
            "original_request": "Research the current Garmin smartwatch models",
            "depth": "deep",
        },
        research_fn=legacy_research,
        packet_builder=lambda result: "packet",
    )

    assert legacy_calls == [("Garmin smartwatch lineup", 4)]
    assert legacy_result["accepted_source_count"] == 1


    # --------------------------------------------------
    # 6. Foreground Phase 10 factual lookup keeps its established bounded-read
    #    contract when no durable background-research identity is supplied.
    # --------------------------------------------------

    original_execute_tool = public_research.execute_tool
    foreground_reads = []

    def foreground_execute_tool(name, arguments):
        if name == "web_search":
            return _search_result(
                _result(
                    "WidgetFlux operator",
                    "https://alpha.example/operator",
                    "WidgetFlux is operated by Example Alpha.",
                ),
                _result(
                    "WidgetFlux company profile",
                    "https://beta.example/profile",
                    "Company profile for WidgetFlux.",
                ),
                _result(
                    "Other page",
                    "https://alpha.example/other",
                    "Unrelated backfill candidate.",
                ),
            )

        if name == "web_read":
            foreground_reads.append(arguments["url"])

            if arguments["url"] == "https://alpha.example/operator":
                return _read("WidgetFlux is operated by Example Alpha.")

            if arguments["url"] == "https://beta.example/profile":
                return _read("WidgetFlux company profile.")

            raise AssertionError((name, arguments))

        raise AssertionError((name, arguments))

    public_research.execute_tool = foreground_execute_tool

    try:
        foreground_result = public_research.gather_public_factual_research(
            "Who operates WidgetFlux",
            max_reads=2,
        )
    finally:
        public_research.execute_tool = original_execute_tool

    assert foreground_result["success"] is True
    assert foreground_result["strict_relevance"] is False
    assert foreground_result["readable_source_count"] == 2
    assert foreground_reads == [
        "https://alpha.example/operator",
        "https://beta.example/profile",
    ]

    # --------------------------------------------------
    # 7. Relevant sources receive deterministic authority tiers. Official subject
    #    domains count as primary; social/video, retailer and rumor/wiki pages do
    #    not count toward the deterministic authority floor.
    # --------------------------------------------------

    official = public_research.classify_public_source_authority(
        {
            "url": "https://www.garmin.com/en-US/venu",
            "source_host": "garmin.com",
            "source_quality": "general_web",
        },
        research_identity="the current Garmin Venu smartwatch models",
    )
    assert official["authority_tier"] == "primary_official"
    assert official["quality_eligible"] is True

    video = public_research.classify_public_source_authority(
        {
            "url": "https://www.youtube.com/watch?v=123",
            "source_host": "youtube.com",
            "source_quality": "general_web",
        },
        research_identity="the current Garmin Venu smartwatch models",
    )
    assert video["authority_tier"] == "weak_community_or_social"
    assert video["quality_eligible"] is False

    retailer = public_research.classify_public_source_authority(
        {
            "url": "https://www.walmart.com/ip/garmin-venu",
            "source_host": "walmart.com",
            "source_quality": "general_web",
        },
        research_identity="the current Garmin Venu smartwatch models",
    )
    assert retailer["authority_tier"] == "secondary_retailer_or_marketplace"
    assert retailer["quality_eligible"] is False

    rumor_wiki = public_research.classify_public_source_authority(
        {
            "url": "https://wiki.garminrumors.com/wiki/Venu",
            "source_host": "wiki.garminrumors.com",
            "source_quality": "general_web",
        },
        research_identity="the current Garmin Venu smartwatch models",
    )
    assert rumor_wiki["authority_tier"] == "secondary_reference_or_aggregation"
    assert rumor_wiki["quality_eligible"] is False

    # --------------------------------------------------
    # 8. Narrow catalogue research gets a smaller cap but a stronger evidence
    #    composition floor: at least one primary source and independent support.
    #    Weak/retailler volume cannot satisfy the floor.
    # --------------------------------------------------

    catalogue_job = {
        "topic": "the current Garmin Venu smartwatch models",
        "goal": "Research the current Garmin Venu smartwatch models",
        "original_request": "Research the current Garmin Venu smartwatch models in the background.",
        "depth": "deep",
    }

    def quality_source(index, host, tier, eligible=True):
        return {
            "title": "Evidence " + str(index),
            "url": "https://" + host + "/item-" + str(index),
            "source_host": host,
            "read_success": True,
            "accepted_as_evidence": True,
            "relevance_status": "accepted",
            "authority_tier": tier,
            "quality_eligible": eligible,
        }

    no_primary = {
        "rounds": [{}, {}],
        "source_index": [
            quality_source(1, "review1.example", "independent_editorial"),
            quality_source(2, "review2.example", "independent_editorial"),
            quality_source(3, "review3.example", "independent_editorial"),
            quality_source(4, "review4.example", "independent_editorial"),
            quality_source(5, "review5.example", "independent_editorial"),
            quality_source(6, "review6.example", "independent_editorial"),
            quality_source(7, "youtube.com", "weak_community_or_social", False),
            quality_source(8, "walmart.com", "secondary_retailer_or_marketplace", False),
        ],
    }

    no_primary_quality = research_quality_snapshot(
        catalogue_job,
        no_primary,
    )

    assert no_primary_quality["maximum_rounds"] == 6
    assert no_primary_quality["accepted_relevant_source_count"] == 8
    assert no_primary_quality["source_count"] == 6
    assert no_primary_quality["weak_source_count"] == 1
    assert no_primary_quality["secondary_source_count"] == 1
    assert no_primary_quality["primary_source_count"] == 0
    assert no_primary_quality["authority_floor_met"] is False
    assert no_primary_quality["minimum_floor_met"] is False

    with_primary = dict(no_primary)
    with_primary["source_index"] = list(no_primary["source_index"])
    with_primary["source_index"][0] = quality_source(
        1,
        "garmin.com",
        "primary_official",
    )

    with_primary_quality = research_quality_snapshot(
        catalogue_job,
        with_primary,
    )

    assert with_primary_quality["primary_source_count"] == 1
    assert with_primary_quality["independent_source_count"] == 5
    assert with_primary_quality["authority_floor_met"] is True
    assert with_primary_quality["minimum_floor_met"] is True

    print("Mairon Phase 11.5.6 evidence relevance + source quality tests: PASS")


if __name__ == "__main__":
    run()
