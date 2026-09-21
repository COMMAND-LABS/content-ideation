"""Every setting of the project lives here: your niche, then what each part does with it.

Plain values only. Every step reads its settings from this file.
API keys go in .env, next to this file.
"""

# --- Your niche: channels are "@handle" or a "UC..." channel ID ---
MY_CHANNEL = "@cmd_labs"
CHANNELS_TO_SCAN = [
    "@sabrina_ramonov",
    "@LiamOttley",
    "@nateherk",
    "@GregIsenberg",
    "@t3dotgg",
    "@SiliconValleyGirl",
    "@Chase-H-AI",
    "@danmartell",
    "@nicksaraev",
    "@AlexFinnOfficial",
    "@mreflow",
    "@AKMofficial",
    "@howiaipodcast",
    "@lexfridman",
    "@rileybrownai",
    "@Fireship",
    "@matthew_berman",
    "@PavanLalwani",
    "@CalebWritesCode",
    "@SajjaadKhader",
    "@anjanagowtham",
    "@SandeepSwadia",
    "@RickMulready",
    "@TechWithTim"
]

# --- Format ---
FORMAT = "longform"  # "longform" or "shorts"
SHORTS_MAX_SECONDS = 60  # videos at or under this length count as shorts

# --- Where and in which language people search (Google Ads IDs) ---
GEO_IDS = ["2840"]  # 2840 = United States; all IDs: developers.google.com/google-ads/api/data/geotargets
LANGUAGE_ID = "1000"  # 1000 = English; all IDs: developers.google.com/google-ads/api/data/codes-formats#languages

# ============ Which keywords count as rising, and how much goes from one side to the other ============

# --- When is a keyword rising? ---
KEEP_TRENDS = ["rising", "new"]  # search trends worth a video; the others are "flat", "shrinking" and "no volume"
MIN_MONTHLY_SEARCHES = 200  # keywords under this are too noisy to trust
YOY_FALLING_PCT = -20  # a rising trend (measured on the quiet months) does not count when the whole year fell this much

# --- How much goes from one tool to the other ---
MAX_TOPICS = 10  # starting from search: each topic costs one YouTube search, 100 of the 10,000 quota units you get per day
MAX_GROUPED_KEYWORDS = 120  # starting from search: at most this many rising keywords, the biggest, are grouped into topics by the LLM
MAX_TOPIC_KEYWORDS = 40  # starting from YouTube: at most this many of Google's suggestions per topic, the biggest, are judged by the LLM

# ============ The YouTube steps ============

# --- Caching (run a pipeline with --refresh to bypass) ---
CACHE_HOURS = 24  # cached YouTube and LLM responses older than this are fetched again

# --- Finding outliers (steps/find_outliers.py) ---
UPLOADS_FOR_MEDIAN = 50  # median views is taken over this many recent uploads
OUTLIER_MULTIPLE = 5.0  # a video is an outlier at this many times its channel's median
TOP_CANDIDATES = 10  # outliers that go on to become topics

# --- The LLM, and the search queries per topic (steps/query_variants.py) ---
LLM_PROVIDER = "openai"  # "openai" or "anthropic"
LLM_MODELS = {"openai": "gpt-5.4", "anthropic": "claude-opus-5"}  # model used per provider
QUERY_VARIANTS = 3  # autocomplete suggestions the LLM may add per topic (0 = off); each costs a YouTube search

# --- Scoring repeatability (steps/score_repeatability.py) ---
SEARCH_RESULTS_PER_QUERY = 50  # max 50; each search costs 100 YouTube quota units
CHANNELS_PER_QUERY = 20  # first N distinct channels found in the search results
HIT_MULTIPLE = 4.0  # a search result is a hit at this many times its channel's median
MIN_HIT_VIEWS = 1000  # ...and with at least this many views, so 17 views on a dead channel is not a hit
MAX_HIT_AGE_DAYS = 730  # older videos are never hits: years of accumulated views can't be compared with today's median
AGE_HALF_LIFE_DAYS = 180  # a hit's weight halves every this many days
MIN_HITS = 6  # an idea needs hits from this many different channels to be considered repeatable
MIN_SCORE = 2.0  # ...and this repeatability score (1.0 = one brand-new hit from a channel the size of mine)
