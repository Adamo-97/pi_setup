Adam, write a YouTube script covering ALL the games releasing this month ({month_name} {year}).

## Game Data:
{games_data}

## RAG Context (avoid repeating recent content):
{rag_context}

## Previous Feedback (learn from past mistakes):
{previous_feedback}

## Instructions:

### Sorting Rule (MANDATORY)
You MUST sort the games in this exact order before writing:
1. **First:** Games with a specific release date (Day/Month/Year), ordered chronologically (nearest to furthest).
2. **Second:** Games with a release window (e.g., "Early {year}" or "{year}"), ordered chronologically.
3. **Third:** Games with no set date (TBA), placed at the end.

### Game Sections
Use clear transitions between each game:
- "نبدأ مع..."
- "نروح بعدها لـ..."
- "وبعدها إلى..."
- "وبعدها نروح مباشرة لـ..."

For EACH game, you MUST cover ALL of these:
1. **Name & Release Date:** e.g., "نبدأ مع Star Wars Outlaws. هاي اللعبه موعدها تحدد رسمياً على ثلاثين أغسطس..."
2. **Concept & Genre:** What kind of game is it? What's the core idea?
3. **Gameplay Details:** Key mechanics, modes, what makes it unique.
4. **Neutral Analysis/Opinion:** Your honest take — no hype, no bashing.
5. **Extra Info — Monthly Specifics:** For each game, also mention:
   - Is it on Game Pass? ("متوفرة على Game Pass من اليوم الأول" or "لا")
   - Arabic language support? ("تدعم العربية ترجمة/دبلجة" or "لا تدعم العربية")
   - Price if available.
6. **Summary Box** — At the end of each game segment:
   - "التاريخ: [date here]"
   - "المنصّات: [platforms here]"

### Intro Variation for Monthly:
The intro should mention the month: "فيديو اليوم حنغطي فيه أبرز إصدارات شهر {month_name} {year}، وهاي المرة جبتلكم تشكيله..."

### Outro Variation for Monthly:
Before the standard outro, ask: "أي لعبة من إصدارات هالشهر انتو متحمسين لها أكثر؟"

### Rules:
- Do NOT skip any game from the provided data. Cover ALL of them.
- Stay neutral — describe features as they are, provide light analysis, no hype.
- English for game titles, studio names, platforms, genres. Arabic words for ALL numbers.
- Target duration: {target_duration} minutes (~{word_count} words). You MUST write at least {word_count} words.
