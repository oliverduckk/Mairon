import os

from dotenv import load_dotenv
from tavily import TavilyClient
from core.external_data_admission import (
    admit_external, dispatch_external, safe_external_errors, ExternalDataDenied, public_service_result, canonical_external_text,
)
from tools.public_url_policy import public_http_url


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


@safe_external_errors
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
    query = canonical_external_text(query, 'query')

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

        admission = admit_external('tavily.search', search_arguments)
        response = dispatch_external(admission, search_arguments, client.search)

        raw_results = response.get(
            "results",
            []
        )

        results = []

        for result in raw_results:
            checked_result_url = public_http_url(result.get("url")) if isinstance(result, dict) else None
            if checked_result_url is None:
                continue
            cleaned_result = {
                "title": result.get("title"),
                "url": checked_result_url,
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

        return public_service_result(admission, {
            "success": True,
            "query": query,
            "topic": topic,
            "time_range": time_range,
            "results": results
        })

    except ExternalDataDenied:
        raise
    except Exception as error:
        error = "The external service was unavailable."
        return {
            "success": False,
            "message": f"Web search failed: {error}"
        }


@safe_external_errors
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
    checked_url = public_http_url(url)
    if checked_url is None:
        raise ExternalDataDenied("A public, non-credential-bearing URL is required.")
    url = checked_url

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
                focus = canonical_external_text(focus, 'query')
                extract_arguments["query"] = focus
                extract_arguments["chunks_per_source"] = 3

        admission = admit_external('tavily.extract', extract_arguments)
        response = dispatch_external(admission, extract_arguments, client.extract)

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
                    "details": []
                }

            return {
                "success": False,
                "message": "No webpage content was returned."
            }

        result = results[0]
        if public_http_url(result.get("url", url)) is None:
            raise ExternalDataDenied("The extracted source is not eligible public evidence.")

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

        return public_service_result(admission, {
            "success": True,
            "url": result.get("url", url),
            "focus": focus,
            "content": content
        })

    except ExternalDataDenied:
        raise
    except Exception as error:
        error = "The external service was unavailable."
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
