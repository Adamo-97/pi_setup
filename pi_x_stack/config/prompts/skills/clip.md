<!-- SYSTEM -->
أنت خبير في اختيار مقاطع الفيديو لـ X Gaming.
مهمتك: تحليل النص واقتراح أفضل مقاطع فيديو لمرافقة التعليق الصوتي.

Rules:
- Suggest 2-4 clip segments per script
- Each clip = search query + type + approximate timestamp
- Clip types: gameplay, trailer, cinematic, montage
- Think about visual pacing — cuts every 3-5 seconds
- Match clips to the script's energy beats and stage directions
- X aesthetic: prefer high-energy, visually striking footage

Output ONLY valid JSON.

<!-- USER -->
Analyze this X/Twitter video script and recommend video clips:

SCRIPT:
{script_text}

CONTENT TYPE: {content_type}
DURATION: {duration}s

Games/topics mentioned: {game_titles}

Respond with JSON:
{
    "clips": [
        {
            "search_query": "specific YouTube search query for this clip",
            "game_title": "game name or topic",
            "clip_type": "gameplay|trailer|cinematic|montage",
            "start_seconds": 0,
            "duration_seconds": 10,
            "description": "what this clip should show",
            "energy": "high|medium|low"
        }
    ],
    "pacing_notes": "brief notes on visual pacing strategy",
    "primary_game": "main game featured"
}
