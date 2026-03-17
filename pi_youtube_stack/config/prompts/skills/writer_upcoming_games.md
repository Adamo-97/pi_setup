Adam, write a YouTube script covering the upcoming games listed below.

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
2. **Second:** Games with a release window (e.g., "Early 2026" or "2026"), ordered chronologically.
3. **Third:** Games with no set date (TBA), placed at the end.

### Game Sections
Use clear transitions between each game:
- "نبدأ مع..."
- "نروح بعدها لـ..."
- "وبعدها إلى..."
- "وبعدها نروح مباشرة لـ..."

For EACH game, you MUST cover ALL of these:
1. **Name & Release Date:** e.g., "نبدأ مع Eggspedition. موعدها حيكون ف 2025 وما في تاريخ نهائي للحين..."
2. **Concept & Genre:** e.g., "بس توجهها واضح من أول دقيقة: شوتر منظور أول بفكرة 'استخراج'"
3. **Gameplay Details:** e.g., "تدخل منشآت... تجمع البيض... اللعب فردي أو تعاوني..."
4. **Neutral Analysis/Opinion:** e.g., "كل راوند فيها سريع والسيناريوهات تشتغل على عنصر المفاجأة..."
5. **Extra Info:** e.g., "وبناء على الاسم اللي اختاروه..."
6. **Summary Box** — At the end of each game segment, add a clear summary:
   - "التاريخ: [date here]"
   - "المنصّات: [platforms here]"

### Rules:
- Do NOT skip any game from the provided data. Cover ALL of them.
- Stay neutral — describe features as they are, provide light analysis, no hype.
- English for game titles, studio names, platforms, genres. Arabic words for ALL numbers.
- Target duration: {target_duration} minutes (~{word_count} words). You MUST write at least {word_count} words.
