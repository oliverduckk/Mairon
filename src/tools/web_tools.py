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


def web_search(
    query,
    topic="general",
    time_range=None,
    max_results=5
):
    """
    Search the live web using Tavily.

    Supported topics:
        general
        news
        finance

    Supported time ranges:
        None
        day
        week
        month
        year

    The function deliberately returns search evidence rather than
    asking Tavily to generate an answer. Mairon's AI provider should
    reason over the returned sources itself.
    """

    if not TAVILY_API_KEY:
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

    # Prevent the AI from requesting a ridiculous number
    # of results and dumping half the internet into context.
    max_results = max(1, min(int(max_results), 8))

    try:
        client = TavilyClient(
            api_key=TAVILY_API_KEY
        )

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

            # Tavily includes this for news results
            # when the publication date is available.
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


if __name__ == "__main__":
    result = web_search(
        query="latest NVIDIA news",
        topic="news",
        time_range="week"
    )

    print(result)