"""
LeetCode question sourcing helper.

Tries the public (unofficial) LeetCode GraphQL endpoint to pick a random,
non-premium question of the requested difficulty. If the network call
fails for any reason (offline environment, LeetCode blocking, timeout,
schema change, etc.) it falls back to a small curated static pool so the
OA feature keeps working even without internet access.
"""
import random
import requests

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

_QUERY = """
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList: questionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total: totalNum
    questions: data {
      title
      titleSlug
      difficulty
      isPaidOnly
    }
  }
}
"""

# Curated offline fallback pool (used if the LeetCode API can't be reached)
_FALLBACK_POOL = {
    "easy": [
        ("Two Sum", "two-sum"),
        ("Reverse Integer", "reverse-integer"),
        ("Valid Parentheses", "valid-parentheses"),
        ("Merge Two Sorted Lists", "merge-two-sorted-lists"),
        ("Best Time to Buy and Sell Stock", "best-time-to-buy-and-sell-stock"),
        ("Maximum Subarray", "maximum-subarray"),
        ("Climbing Stairs", "climbing-stairs"),
        ("Palindrome Number", "palindrome-number"),
        ("Valid Anagram", "valid-anagram"),
        ("Contains Duplicate", "contains-duplicate"),
    ],
    "medium": [
        ("Add Two Numbers", "add-two-numbers"),
        ("Longest Substring Without Repeating Characters", "longest-substring-without-repeating-characters"),
        ("Longest Palindromic Substring", "longest-palindromic-substring"),
        ("3Sum", "3sum"),
        ("Group Anagrams", "group-anagrams"),
        ("Rotate Image", "rotate-image"),
        ("Product of Array Except Self", "product-of-array-except-self"),
        ("Course Schedule", "course-schedule"),
        ("Search in Rotated Sorted Array", "search-in-rotated-sorted-array"),
        ("Top K Frequent Elements", "top-k-frequent-elements"),
    ],
    "hard": [
        ("Median of Two Sorted Arrays", "median-of-two-sorted-arrays"),
        ("Merge k Sorted Lists", "merge-k-sorted-lists"),
        ("Trapping Rain Water", "trapping-rain-water"),
        ("N-Queens", "n-queens"),
        ("Regular Expression Matching", "regular-expression-matching"),
        ("First Missing Positive", "first-missing-positive"),
        ("Word Ladder II", "word-ladder-ii"),
        ("Longest Valid Parentheses", "longest-valid-parentheses"),
    ],
}


def _fallback_question(difficulty):
    key = difficulty.lower()
    pool = _FALLBACK_POOL.get(key, _FALLBACK_POOL["easy"])
    title, slug = random.choice(pool)
    return {
        "title": title,
        "difficulty": key.capitalize(),
        "link": f"https://leetcode.com/problems/{slug}/",
        "source": "leetcode",
    }


def fetch_random_question(difficulty, pool_size=50, timeout=6):
    """Return a random free (non-premium) LeetCode question dict for the
    given difficulty ('easy' | 'medium' | 'hard'). Always returns a usable
    dict - falls back to a static curated pool on any failure."""
    difficulty = (difficulty or "easy").lower()
    try:
        variables = {
            "categorySlug": "",
            "skip": 0,
            "limit": pool_size,
            "filters": {"difficulty": difficulty.upper()},
        }
        resp = requests.post(
            LEETCODE_GRAPHQL_URL,
            json={"query": _QUERY, "variables": variables},
            headers={
                "Content-Type": "application/json",
                "Referer": "https://leetcode.com",
                "User-Agent": "Mozilla/5.0 (PlacementPortal OA Bot)",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        questions = data["data"]["problemsetQuestionList"]["questions"]
        free_qs = [q for q in questions if not q.get("isPaidOnly")]
        pool = free_qs or questions
        if not pool:
            return _fallback_question(difficulty)
        q = random.choice(pool)
        return {
            "title": q["title"],
            "difficulty": difficulty.capitalize(),
            "link": f"https://leetcode.com/problems/{q['titleSlug']}/",
            "source": "leetcode",
        }
    except Exception:
        return _fallback_question(difficulty)


def fetch_oa_question_set():
    """Convenience: returns one easy, one medium, one hard question."""
    return [
        fetch_random_question("easy"),
        fetch_random_question("medium"),
        fetch_random_question("hard"),
    ]
