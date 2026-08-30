import os

from dotenv import load_dotenv
from tavily import TavilyClient


load_dotenv()


TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

VALID_TOPICS = {
    "general",
    "news",
    "finance",
}

VALID_TIME_RANGES = {
    "day",
    "week",
    "month",
    "year",
}


def create_client():
    if not TAVILY_API_KEY:
        return None

    return TavilyClient(
        api_key=TAVILY_API_KEY
    )


def web_search(
    query,
    topic="general",
    time_range=None,
    max_results=5
):
    """
    Search the live public web using Tavily.

    Returns search evidence for Mairon's AI provider
    to reason over. Tavily does not generate the final answer.
    """

    client = create_client()

    if client is None:
        return {
            "success": False,
            "message": "Tavily API key is not configured."
        }

    query = query.strip()

    if not query:
        return {
            "success": False,
            "message": "Search query cannot be empty."
        }

    topic = topic.lower().strip()

    if topic not in VALID_TOPICS:
        return {
            "success": False,
            "message": f"Unsupported search topic '{topic}'."
        }

    if time_range is not None:
        time_range = time_range.lower().strip()

        if time_range not in VALID_TIME_RANGES:
            return {
                "success": False,
                "message": (
                    f"Unsupported time range '{time_range}'."
                )
            }

    max_results = max(
        1,
        min(int(max_results), 8)
    )

    try:
        search_arguments = {
            "query": query,
            "search_depth": "basic",
            "topic": topic,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        if time_range is not None:
            search_arguments["time_range"] = time_range

        response = client.search(
            **search_arguments
        )

        raw_results = response.get(
            "results",
            []
        )

        results = []

        for result in raw_results:
            cleaned_result = {
                "title": result.get("title"),
                "url": result.get("url"),
                "content": result.get("content"),
                "score": result.get("score"),
            }

            if result.get("published_date"):
                cleaned_result["published_date"] = (
                    result["published_date"]
                )

            results.append(cleaned_result)

        if not results:
            return {
                "success": False,
                "message": "The web search returned no results."
            }

        return {
            "success": True,
            "query": query,
            "topic": topic,
            "time_range": time_range,
            "results": results
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Web search failed: {error}"
        }


def web_read(
    url,
    focus=None
):
    """
    Read content from one public webpage.

    If a focus/question is supplied, Tavily returns
    the sections most relevant to that topic rather
    than unnecessarily retrieving the whole page.
    """

    client = create_client()

    if client is None:
        return {
            "success": False,
            "message": "Tavily API key is not configured."
        }

    url = url.strip()

    if not url:
        return {
            "success": False,
            "message": "A URL is required."
        }

    if not (
        url.startswith("https://")
        or url.startswith("http://")
    ):
        return {
            "success": False,
            "message": "Only HTTP or HTTPS URLs can be read."
        }

    try:
        extract_arguments = {
            "urls": url,
            "extract_depth": "basic",
            "format": "markdown",
            "include_images": False,
        }

        if focus:
            focus = focus.strip()

            if focus:
                extract_arguments["query"] = focus
                extract_arguments["chunks_per_source"] = 3

        response = client.extract(
            **extract_arguments
        )

        results = response.get(
            "results",
            []
        )

        if not results:
            failed_results = response.get(
                "failed_results",
                []
            )

            if failed_results:
                return {
                    "success": False,
                    "message": (
                        "The webpage could not be extracted."
                    ),
                    "details": failed_results
                }

            return {
                "success": False,
                "message": "No webpage content was returned."
            }

        result = results[0]

        content = result.get(
            "raw_content",
            ""
        )

        if not content:
            return {
                "success": False,
                "message": "The webpage contained no readable content."
            }

        # Hard context-size safety limit.
        # Query-focused extraction should normally be much smaller,
        # but this prevents huge pages from overwhelming the model.
        MAX_CONTENT_CHARACTERS = 15000

        if len(content) > MAX_CONTENT_CHARACTERS:
            content = content[
                :MAX_CONTENT_CHARACTERS
            ]

        return {
            "success": True,
            "url": result.get("url", url),
            "focus": focus,
            "content": content
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Webpage extraction failed: {error}"
        }


if __name__ == "__main__":
    result = web_read(
        url="https://docs.tavily.com/sdk/python/quick-start",
        focus="What functionality does the Tavily Python SDK provide?"
    )

    print(result)